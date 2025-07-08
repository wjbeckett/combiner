from flask import Flask, request, jsonify
import logging
import os
import json
from datetime import datetime
from pathlib import Path
from .radarr_client import RadarrClient
from .file_manager import FileManager
from .config import Config

# Initialize config first
config = Config()
config.ensure_config_dir()

# Setup logging with file output
log_file = config.get_log_file_path()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(),  # Also log to console
    ],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

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

        # Log the webhook event and full payload for debugging
        event_type = payload.get("eventType", "unknown")
        logger.info(f"Received webhook: {event_type}")

        # Debug: Log the full payload structure (be careful with sensitive data)
        logger.debug(f"Full webhook payload: {json.dumps(payload, indent=2)}")

        # Log payload keys to understand structure
        logger.info(f"Payload keys: {list(payload.keys())}")

        # Only process 'Download' events (when import completes)
        if event_type != "Download":
            logger.info(f"Ignoring event type: {event_type}")
            return jsonify({"message": "Event ignored"}), 200

        # Extract movie and file information with better error handling
        movie = payload.get("movie")
        movie_file = payload.get("movieFile")

        # Debug logging for movie and movieFile
        if movie:
            logger.info(f"Movie data type: {type(movie)}")
            if isinstance(movie, dict):
                logger.info(f"Movie keys: {list(movie.keys())}")
            else:
                logger.warning(f"Movie is not a dict, it's: {movie}")
        else:
            logger.error("No 'movie' key in payload")

        if movie_file:
            logger.info(f"MovieFile data type: {type(movie_file)}")
            if isinstance(movie_file, dict):
                logger.info(f"MovieFile keys: {list(movie_file.keys())}")
            else:
                logger.warning(f"MovieFile is not a dict, it's: {movie_file}")
        else:
            logger.error("No 'movieFile' key in payload")

        # Validate that we have the required data structures
        if not movie or not isinstance(movie, dict):
            logger.error("Missing or invalid movie data in payload")
            return jsonify({"error": "Invalid movie data structure"}), 400

        if not movie_file or not isinstance(movie_file, dict):
            logger.error("Missing or invalid movieFile data in payload")
            return jsonify({"error": "Invalid movieFile data structure"}), 400

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
        logger.error(f"Exception type: {type(e)}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route("/config", methods=["GET"])
def get_config():
    """Get current configuration for debugging"""
    try:
        config_info = {
            "plex_naming_enabled": config.enable_plex_naming,
            "quality_suffix_enabled": config.plex_quality_suffix,
            "radarr_main_url": config.radarr_main_url,
            "radarr_4k_url": config.radarr_4k_url,
            "config_directory": str(config.config_dir),
            "log_file": str(config.get_log_file_path()),
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


@app.route("/logs", methods=["GET"])
def get_logs():
    """Get recent log entries"""
    try:
        log_file = config.get_log_file_path()
        if not log_file.exists():
            return jsonify({"logs": [], "message": "No log file found"}), 200

        # Get last 100 lines
        with open(log_file, "r") as f:
            lines = f.readlines()
            recent_lines = lines[-100:] if len(lines) > 100 else lines

        return (
            jsonify(
                {
                    "logs": [line.strip() for line in recent_lines],
                    "total_lines": len(lines),
                    "showing_lines": len(recent_lines),
                }
            ),
            200,
        )
    except Exception as e:
        logger.error(f"Error getting logs: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500


@app.route("/test-webhook", methods=["POST"])
def test_webhook():
    """Test endpoint to debug webhook payloads"""
    try:
        payload = request.get_json()
        logger.info("=== TEST WEBHOOK RECEIVED ===")
        logger.info(f"Payload type: {type(payload)}")
        logger.info(f"Payload: {json.dumps(payload, indent=2)}")

        if isinstance(payload, dict):
            logger.info(f"Keys: {list(payload.keys())}")

        return (
            jsonify(
                {
                    "message": "Test webhook received",
                    "payload_type": str(type(payload)),
                    "payload": payload,
                }
            ),
            200,
        )

    except Exception as e:
        logger.error(f"Error in test webhook: {str(e)}")
        return jsonify({"error": str(e)}), 500


def process_4k_movie(movie, movie_file):
    """Process a 4K movie: move file with optional Plex naming and remove from 4K Radarr"""
    try:
        # Safely extract movie information
        movie_title = (
            movie.get("title", "Unknown") if isinstance(movie, dict) else "Unknown"
        )
        movie_year = (
            movie.get("year", "Unknown") if isinstance(movie, dict) else "Unknown"
        )
        movie_id = movie.get("id") if isinstance(movie, dict) else None

        # Safely extract file information
        file_path = movie_file.get("path") if isinstance(movie_file, dict) else None

        if not file_path:
            logger.error("No file path found in movieFile data")
            return {"success": False, "error": "No file path in movieFile"}

        # Extract quality information from the webhook payload
        quality_info = (
            movie_file.get("quality", {}) if isinstance(movie_file, dict) else {}
        )
        if isinstance(quality_info, dict):
            quality_title = quality_info.get("quality", {}).get("name", "Unknown")
        else:
            quality_title = "Unknown"

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

        # Move file to main library
        move_result = file_manager.move_to_main_library(
            source_path=file_path,
            movie_title=movie_title,
            movie_year=movie_year,
            quality_title=quality_title,
            k4_root_folders=k4_root_folders,
            main_root_folders=main_root_folders,
        )

        if not move_result["success"]:
            return move_result

        # Remove movie from 4K Radarr (only if we have a valid movie_id)
        if movie_id:
            removal_result = radarr_4k.remove_movie(movie_id)
        else:
            logger.warning("No movie ID found, skipping removal from 4K Radarr")
            removal_result = {"success": False, "error": "No movie ID"}

        # Log results
        existing_renamed = move_result.get("existing_files_renamed", [])
        existing_errors = move_result.get("existing_files_errors", [])

        if removal_result["success"]:
            logger.info(f"✅ Successfully processed {movie_title} ({movie_year})")
            logger.info(f"📂 Final filename: {move_result.get('final_filename')}")
            logger.info(f"🔗 Naming mode: {move_result.get('naming_mode')}")
            logger.info(f"🚚 Operation: {move_result.get('operation')}")

            if move_result.get("renamed"):
                logger.info(
                    f"🏷️ Renamed file: {move_result.get('original_filename')} → {move_result.get('final_filename')}"
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
                "destination_path": move_result.get("destination_path"),
                "final_filename": move_result.get("final_filename"),
                "original_filename": move_result.get("original_filename"),
                "naming_mode": move_result.get("naming_mode"),
                "renamed": move_result.get("renamed"),
                "operation": move_result.get("operation"),
                "existing_files_renamed": existing_renamed,
                "existing_files_errors": existing_errors,
                "removed_from_4k_radarr": True,
            }
        else:
            logger.warning(
                f"⚠️ File moved but failed to remove from 4K Radarr: {removal_result.get('error')}"
            )

            # Still log existing file renames even if Radarr removal failed
            if existing_renamed:
                logger.info(
                    f"🎯 Renamed {len(existing_renamed)} existing files for Plex merging!"
                )

            return {
                "success": True,  # Partial success
                "movie": f"{movie_title} ({movie_year})",
                "destination_path": move_result.get("destination_path"),
                "final_filename": move_result.get("final_filename"),
                "naming_mode": move_result.get("naming_mode"),
                "operation": move_result.get("operation"),
                "existing_files_renamed": existing_renamed,
                "existing_files_errors": existing_errors,
                "removed_from_4k_radarr": False,
                "warning": removal_result.get("error"),
            }

    except Exception as e:
        logger.error(f"❌ Error processing 4K movie: {str(e)}")
        import traceback

        logger.error(f"Full traceback: {traceback.format_exc()}")
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    # Test connections on startup
    logger.info("🚀 Starting Combiner...")

    # Log configuration
    logger.info(f"📁 Config directory: {config.config_dir}")
    logger.info(f"📝 Log file: {config.get_log_file_path()}")
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

    logger.info("🎬 Combiner ready to seamlessly move your 4K collection!")
    app.run(host="0.0.0.0", port=5465, debug=False)
