from flask import Flask, request, jsonify
import logging
import os
from datetime import datetime
from .radarr_client import RadarrClient
from .file_manager import FileManager
from .config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
config = Config()

# Initialize clients
radarr_main = RadarrClient(config.radarr_main_url, config.radarr_main_api_key)
radarr_4k = RadarrClient(config.radarr_4k_url, config.radarr_4k_api_key)
file_manager = FileManager(config)  # Pass config to FileManager


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


@app.route("/webhook/radarr-4k", methods=["POST"])
def handle_radarr_4k_webhook():
    """Handle webhook from 4K Radarr instance"""
    try:
        payload = request.get_json()

        if not payload:
            logger.error("No JSON payload received")
            return jsonify({"error": "No JSON payload"}), 400

        # Log the webhook event
        event_type = payload.get("eventType", "unknown")
        logger.info(f"Received webhook: {event_type}")

        # Only process 'Download' events (when import completes)
        if event_type != "Download":
            logger.info(f"Ignoring event type: {event_type}")
            return jsonify({"message": "Event ignored"}), 200

        # Extract movie and file information
        movie = payload.get("movie", {})
        movie_file = payload.get("movieFile", {})

        if not movie or not movie_file:
            logger.error("Missing movie or movieFile data in payload")
            return jsonify({"error": "Invalid payload structure"}), 400

        # Process the 4K movie
        result = process_4k_movie(movie, movie_file)

        if result["success"]:
            return (
                jsonify(
                    {"message": "Successfully processed 4K movie", "details": result}
                ),
                200,
            )
        else:
            return jsonify({"error": "Failed to process movie", "details": result}), 500

    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/config", methods=["GET"])
def get_config():
    """Get current configuration for debugging"""
    try:
        config_info = {
            "plex_naming_enabled": config.enable_plex_naming,
            "quality_suffix_enabled": config.plex_quality_suffix,
            "radarr_main_url": config.radarr_main_url,
            "radarr_4k_url": config.radarr_4k_url,
        }
        return jsonify(config_info), 200
    except Exception as e:
        logger.error(f"Error getting config: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/quality-mappings", methods=["GET"])
def get_quality_mappings():
    """Get current quality mappings for debugging"""
    try:
        mappings = file_manager.get_quality_mapping_info()
        return jsonify(mappings), 200
    except Exception as e:
        logger.error(f"Error getting quality mappings: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


def process_4k_movie(movie, movie_file):
    """Process a 4K movie: create hardlink with optional Plex naming and remove from 4K Radarr"""
    try:
        movie_title = movie.get("title", "Unknown")
        movie_year = movie.get("year", "Unknown")
        movie_id = movie.get("id")
        file_path = movie_file.get("path")

        # Extract quality information from the webhook payload
        quality_info = movie_file.get("quality", {})
        quality_title = quality_info.get("quality", {}).get("name", "Unknown")

        logger.info(f"🎬 Processing: {movie_title} ({movie_year})")
        logger.info(f"📁 Source file: {file_path}")
        logger.info(f"🏷️ Radarr Quality: {quality_title}")

        # Log naming configuration
        if config.enable_plex_naming and config.plex_quality_suffix:
            logger.info(
                "🎯 Plex naming: Adding quality suffix + renaming existing files"
            )
        else:
            logger.info("📝 Using original Radarr naming")

        # Get root folder mappings
        main_root_folders = radarr_main.get_root_folders()
        k4_root_folders = radarr_4k.get_root_folders()

        # Create hardlink to main library
        hardlink_result = file_manager.create_hardlink_to_main_library(
            source_path=file_path,
            movie_title=movie_title,
            movie_year=movie_year,
            quality_title=quality_title,
            k4_root_folders=k4_root_folders,
            main_root_folders=main_root_folders,
        )

        if not hardlink_result["success"]:
            return hardlink_result

        # Remove movie from 4K Radarr
        removal_result = radarr_4k.remove_movie(movie_id)

        # Log results
        existing_renamed = hardlink_result.get("existing_files_renamed", [])
        existing_errors = hardlink_result.get("existing_files_errors", [])

        if removal_result["success"]:
            logger.info(f"✅ Successfully processed {movie_title} ({movie_year})")
            logger.info(f"📂 Final filename: {hardlink_result.get('final_filename')}")
            logger.info(f"🔗 Naming mode: {hardlink_result.get('naming_mode')}")

            if hardlink_result.get("renamed"):
                logger.info(
                    f"🏷️ Renamed new file: {hardlink_result.get('original_filename')} → {hardlink_result.get('final_filename')}"
                )

            if existing_renamed:
                logger.info(
                    f"🎯 Renamed {len(existing_renamed)} existing files for Plex merging!"
                )
                for old_name, new_name in existing_renamed:
                    logger.info(f"    📝 {old_name} → {new_name}")

            if existing_errors:
                logger.warning(
                    f"⚠️ {len(existing_errors)} errors renaming existing files:"
                )
                for error in existing_errors:
                    logger.warning(f"    ❌ {error}")

            return {
                "success": True,
                "movie": f"{movie_title} ({movie_year})",
                "hardlink_path": hardlink_result.get("destination_path"),
                "final_filename": hardlink_result.get("final_filename"),
                "original_filename": hardlink_result.get("original_filename"),
                "naming_mode": hardlink_result.get("naming_mode"),
                "renamed": hardlink_result.get("renamed"),
                "existing_files_renamed": existing_renamed,
                "existing_files_errors": existing_errors,
                "removed_from_4k_radarr": True,
            }
        else:
            logger.warning(
                f"⚠️ Hardlink created but failed to remove from 4K Radarr: {removal_result.get('error')}"
            )

            # Still log existing file renames even if Radarr removal failed
            if existing_renamed:
                logger.info(
                    f"🎯 Renamed {len(existing_renamed)} existing files for Plex merging!"
                )

            return {
                "success": True,  # Partial success
                "movie": f"{movie_title} ({movie_year})",
                "hardlink_path": hardlink_result.get("destination_path"),
                "final_filename": hardlink_result.get("final_filename"),
                "naming_mode": hardlink_result.get("naming_mode"),
                "existing_files_renamed": existing_renamed,
                "existing_files_errors": existing_errors,
                "removed_from_4k_radarr": False,
                "warning": removal_result.get("error"),
            }

    except Exception as e:
        logger.error(f"❌ Error processing 4K movie: {str(e)}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Test connections on startup
    logger.info("🚀 Starting Combiner...")

    # Log configuration
    logger.info(f"⚙️ Plex naming enabled: {config.enable_plex_naming}")
    if config.enable_plex_naming:
        logger.info(f"🏷️ Quality suffix enabled: {config.plex_quality_suffix}")
        logger.info("🎯 Will automatically rename existing files for Plex merging!")

    logger.info("🔗 Testing Radarr connections...")
    if radarr_main.test_connection():
        logger.info("✅ Main Radarr connection successful")
    else:
        logger.error("❌ Main Radarr connection failed")

    if radarr_4k.test_connection():
        logger.info("✅ 4K Radarr connection successful")
    else:
        logger.error("❌ 4K Radarr connection failed")

    # Log quality mappings info
    mappings_info = file_manager.get_quality_mapping_info()
    logger.info(f"📋 Loaded {mappings_info['total_mappings']} quality mappings")
    logger.info(
        f"🎬 Supporting {len(mappings_info['supported_video_extensions'])} video formats"
    )

    logger.info("🎬 Combiner ready to seamlessly combine your 4K collection!")
    app.run(host="0.0.0.0", port=5465, debug=False)
