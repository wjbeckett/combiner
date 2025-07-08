import os
import shutil
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

logger = logging.getLogger(__name__)


class FileManager:
    def __init__(self, config):
        self.config = config

        # Common video file extensions
        self.video_extensions = {
            ".mkv",
            ".mp4",
            ".avi",
            ".m4v",
            ".mov",
            ".wmv",
            ".flv",
            ".webm",
            ".ts",
            ".m2ts",
        }

        # Quality mapping from Radarr quality names to Plex-friendly names
        self.quality_mapping = {
            # 4K/UHD variants
            "WEBDL-2160p": "2160p",
            "WEBRip-2160p": "2160p",
            "Bluray-2160p": "2160p",
            "Remux-2160p": "2160p",
            "HDTV-2160p": "2160p",
            # 1080p variants
            "WEBDL-1080p": "1080p",
            "WEBRip-1080p": "1080p",
            "Bluray-1080p": "1080p",
            "Remux-1080p": "1080p",
            "HDTV-1080p": "1080p",
            # 720p variants
            "WEBDL-720p": "720p",
            "WEBRip-720p": "720p",
            "Bluray-720p": "720p",
            "HDTV-720p": "720p",
            # SD variants
            "WEBDL-480p": "SD",
            "WEBRip-480p": "SD",
            "DVD": "SD",
            "SDTV": "SD",
            # Fallback patterns
            "2160p": "2160p",
            "1080p": "1080p",
            "720p": "720p",
            "480p": "SD",
        }

    def create_hardlink_to_main_library(
        self,
        source_path: str,
        movie_title: str,
        movie_year: str,
        quality_title: str,
        k4_root_folders: List[Dict],
        main_root_folders: List[Dict],
    ) -> Dict:
        """Create hardlink from 4K library to main library with optional Plex naming and existing file renaming"""
        try:
            source_file = Path(source_path)

            if not source_file.exists():
                return {
                    "success": False,
                    "error": f"Source file does not exist: {source_path}",
                }

            # Find which 4K root folder contains this file
            k4_root = self._find_root_folder_for_path(source_path, k4_root_folders)
            if not k4_root:
                return {"success": False, "error": "Could not determine 4K root folder"}

            # Get the first main root folder (assuming single main library)
            if not main_root_folders:
                return {"success": False, "error": "No main library root folders found"}

            main_root = main_root_folders[0]["path"]

            # Calculate relative path from 4K root
            k4_root_path = Path(k4_root["path"])
            relative_path = source_file.relative_to(k4_root_path)

            # Determine final filename based on configuration
            if self.config.enable_plex_naming and self.config.plex_quality_suffix:
                final_filename = self._add_quality_suffix(
                    source_file.name, quality_title
                )
                naming_mode = "Plex quality suffix"

                # MAGIC HAPPENS HERE: Rename existing files for Plex merging!
                destination_folder = Path(main_root) / relative_path.parent
                existing_files_result = self._rename_existing_files_for_plex(
                    destination_folder
                )

            else:
                final_filename = source_file.name
                naming_mode = "Original Radarr naming"
                existing_files_result = {"renamed_files": [], "errors": []}

            # Create destination path in main library
            destination_folder = Path(main_root) / relative_path.parent
            destination_path = destination_folder / final_filename

            # Create destination directory if it doesn't exist
            destination_folder.mkdir(parents=True, exist_ok=True)

            # Check if destination already exists
            if destination_path.exists():
                logger.warning(f"Destination already exists: {destination_path}")
                return {
                    "success": True,
                    "destination_path": str(destination_path),
                    "final_filename": final_filename,
                    "naming_mode": naming_mode,
                    "existing_files_renamed": existing_files_result["renamed_files"],
                    "existing_files_errors": existing_files_result["errors"],
                    "note": "File already exists at destination",
                }

            # Create hardlink
            os.link(str(source_file), str(destination_path))

            logger.info(f"Created hardlink using {naming_mode}:")
            logger.info(f"  Source: {source_path}")
            logger.info(f"  Destination: {destination_path}")
            if final_filename != source_file.name:
                logger.info(f"  Renamed: {source_file.name} → {final_filename}")

            # Log existing file renames
            if existing_files_result["renamed_files"]:
                logger.info(
                    f"🎯 Renamed {len(existing_files_result['renamed_files'])} existing files for Plex merging:"
                )
                for old_name, new_name in existing_files_result["renamed_files"]:
                    logger.info(f"    {old_name} → {new_name}")

            return {
                "success": True,
                "source_path": str(source_file),
                "destination_path": str(destination_path),
                "final_filename": final_filename,
                "original_filename": source_file.name,
                "naming_mode": naming_mode,
                "renamed": final_filename != source_file.name,
                "existing_files_renamed": existing_files_result["renamed_files"],
                "existing_files_errors": existing_files_result["errors"],
            }

        except Exception as e:
            logger.error(f"Failed to create hardlink: {e}")
            return {"success": False, "error": str(e)}

    def _rename_existing_files_for_plex(self, destination_folder: Path) -> Dict:
        """Rename existing movie files in destination folder to add quality suffix for Plex merging"""
        renamed_files = []
        errors = []

        if not destination_folder.exists():
            return {"renamed_files": renamed_files, "errors": errors}

        logger.info(
            f"🔍 Scanning for existing files to rename in: {destination_folder}"
        )

        # Find all video files in the destination folder
        video_files = [
            f
            for f in destination_folder.iterdir()
            if f.is_file() and f.suffix.lower() in self.video_extensions
        ]

        for video_file in video_files:
            try:
                # Check if file already has quality suffix
                if self._has_quality_suffix(video_file.name):
                    logger.info(f"  ✅ Already has quality suffix: {video_file.name}")
                    continue

                # Detect quality from filename
                detected_quality = self._detect_quality_from_filename(video_file.name)

                if detected_quality:
                    # Add quality suffix
                    new_filename = self._add_quality_suffix(
                        video_file.name, detected_quality
                    )
                    new_path = video_file.parent / new_filename

                    # Rename the file
                    video_file.rename(new_path)
                    renamed_files.append((video_file.name, new_filename))
                    logger.info(f"  🏷️ Renamed: {video_file.name} → {new_filename}")

                else:
                    # Default to 1080p if we can't detect (most likely scenario for main library)
                    default_quality = "1080p"
                    new_filename = self._add_quality_suffix(
                        video_file.name, default_quality
                    )
                    new_path = video_file.parent / new_filename

                    video_file.rename(new_path)
                    renamed_files.append((video_file.name, new_filename))
                    logger.info(
                        f"  🎯 Renamed (default 1080p): {video_file.name} → {new_filename}"
                    )

            except Exception as e:
                error_msg = f"Failed to rename {video_file.name}: {str(e)}"
                errors.append(error_msg)
                logger.error(f"  ❌ {error_msg}")

        return {"renamed_files": renamed_files, "errors": errors}

    def _has_quality_suffix(self, filename: str) -> bool:
        """Check if filename already has a quality suffix"""
        name_without_ext = Path(filename).stem
        quality_pattern = r"\\s*-\\s*(2160p|1080p|720p|SD|4K)\\s*$"
        return bool(re.search(quality_pattern, name_without_ext, re.IGNORECASE))

    def _detect_quality_from_filename(self, filename: str) -> Optional[str]:
        """Try to detect quality from filename patterns"""
        filename_lower = filename.lower()

        # Look for quality indicators in filename
        quality_patterns = [
            (r"2160p|4k|uhd", "2160p"),
            (r"1080p", "1080p"),
            (r"720p", "720p"),
            (r"480p|dvd", "SD"),
            (r"bluray.*2160p", "2160p"),
            (r"bluray.*1080p", "1080p"),
            (r"webdl.*2160p", "2160p"),
            (r"webdl.*1080p", "1080p"),
            (r"webrip.*2160p", "2160p"),
            (r"webrip.*1080p", "1080p"),
        ]

        for pattern, quality in quality_patterns:
            if re.search(pattern, filename_lower):
                logger.info(
                    f"    🔍 Detected quality '{quality}' from pattern '{pattern}' in: {filename}"
                )
                return quality

        logger.info(f"    ❓ Could not detect quality from filename: {filename}")
        return None

    def _add_quality_suffix(self, original_filename: str, quality_title: str) -> str:
        """Add quality suffix to filename for Plex merging"""

        # Get file extension
        file_path = Path(original_filename)
        name_without_ext = file_path.stem
        extension = file_path.suffix

        # Map quality to Plex-friendly format
        plex_quality = self._map_quality_to_plex(quality_title)

        # Check if quality suffix already exists
        if self._has_quality_suffix(original_filename):
            logger.info(f"Quality suffix already exists in: {original_filename}")
            return original_filename

        # Add quality suffix
        new_filename = f"{name_without_ext} - {plex_quality}{extension}"

        logger.info(f"Quality mapping: '{quality_title}' → '{plex_quality}'")

        return new_filename

    def _map_quality_to_plex(self, radarr_quality: str) -> str:
        """Map Radarr quality title to Plex-friendly quality name"""

        # Direct mapping first
        if radarr_quality in self.quality_mapping:
            return self.quality_mapping[radarr_quality]

        # Pattern matching for complex quality strings
        radarr_lower = radarr_quality.lower()

        # Check for 4K/2160p
        if any(pattern in radarr_lower for pattern in ["2160p", "4k", "uhd"]):
            return "2160p"

        # Check for 1080p
        if "1080p" in radarr_lower:
            return "1080p"

        # Check for 720p
        if "720p" in radarr_lower:
            return "720p"

        # Check for SD/480p
        if any(pattern in radarr_lower for pattern in ["480p", "dvd", "sd"]):
            return "SD"

        # Fallback: try to extract resolution pattern
        resolution_match = re.search(r"(\\d{3,4}p)", radarr_lower)
        if resolution_match:
            resolution = resolution_match.group(1)
            if resolution in ["2160p", "1080p", "720p"]:
                return resolution
            elif resolution == "480p":
                return "SD"

        # Ultimate fallback - use original but clean it up
        logger.warning(
            f"Could not map quality '{radarr_quality}', using cleaned version"
        )
        return self._clean_quality_name(radarr_quality)

    def _clean_quality_name(self, quality: str) -> str:
        """Clean up quality name for Plex compatibility"""
        # Remove common prefixes/suffixes and clean up
        cleaned = (
            quality.replace("Bluray-", "").replace("WEBDL-", "").replace("WEBRip-", "")
        )
        cleaned = cleaned.replace("HDTV-", "").replace("Remux-", "")

        # If it's still complex, try to extract just the resolution
        if len(cleaned) > 10:  # Arbitrary length check
            resolution_match = re.search(r"(\\d{3,4}p)", cleaned)
            if resolution_match:
                return resolution_match.group(1)

        return cleaned

    def _find_root_folder_for_path(
        self, file_path: str, root_folders: List[Dict]
    ) -> Optional[Dict]:
        """Find which root folder contains the given file path"""
        file_path_obj = Path(file_path)

        for root_folder in root_folders:
            root_path = Path(root_folder["path"])
            try:
                # Check if file_path is under this root
                file_path_obj.relative_to(root_path)
                return root_folder
            except ValueError:
                # Path is not under this root
                continue

        return None

    def get_quality_mapping_info(self) -> Dict:
        """Return current quality mapping for debugging/info"""
        return {
            "mappings": self.quality_mapping,
            "total_mappings": len(self.quality_mapping),
            "plex_naming_enabled": self.config.enable_plex_naming,
            "quality_suffix_enabled": self.config.plex_quality_suffix,
            "supported_video_extensions": list(self.video_extensions),
        }
