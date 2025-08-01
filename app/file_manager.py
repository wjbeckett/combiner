import os
import shutil
import logging
import re
import stat
import time
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class FileManager:
    def __init__(self, config):
        self.config = config

        # Video file extensions
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

        # Enhanced quality mappings (Radarr → Plex friendly)
        self.quality_mappings = {
            # Standard definitions
            "SDTV": "480p",
            "DVD": "480p",
            "WEBDL-480p": "480p",
            "WEBRip-480p": "480p",
            "Bluray-480p": "480p",
            # High definitions
            "HDTV-720p": "720p",
            "WEBDL-720p": "720p",
            "WEBRip-720p": "720p",
            "Bluray-720p": "720p",
            # Full HD
            "HDTV-1080p": "1080p",
            "WEBDL-1080p": "1080p",
            "WEBRip-1080p": "1080p",
            "Bluray-1080p": "1080p",
            "Remux-1080p": "1080p",
            # 4K/UHD
            "HDTV-2160p": "2160p",
            "WEBDL-2160p": "2160p",
            "WEBRip-2160p": "2160p",
            "Bluray-2160p": "2160p",
            "Remux-2160p": "2160p",
            # Common variations
            "Web-DL": "1080p",  # Default assumption
            "WEB-DL": "1080p",
            "WebRip": "1080p",
            "WEB": "1080p",
            "HDTV": "1080p",
            "BluRay": "1080p",
            "Blu-ray": "1080p",
            "Remux": "1080p",
        }

    def get_quality_from_payload(self, movie_file: dict) -> str:
        """Extract quality from Radarr webhook payload with multiple fallback methods"""
        try:
            # Method 1: Direct quality object
            quality_info = movie_file.get("quality", {})
            if isinstance(quality_info, dict):
                quality_obj = quality_info.get("quality", {})
                if isinstance(quality_obj, dict):
                    quality_name = quality_obj.get("name")
                    if quality_name and quality_name != "Unknown":
                        logger.info(
                            f"Quality from payload.quality.quality.name: {quality_name}"
                        )
                        return quality_name

            # Method 2: Check file path for quality indicators
            file_path = movie_file.get("path", "")
            if file_path:
                logger.info(f"Analyzing file path for quality: {file_path}")

                # Look for resolution patterns
                resolution_patterns = [
                    r"2160p|4K|UHD",  # 4K patterns
                    r"1080p|FHD",  # 1080p patterns
                    r"720p|HD",  # 720p patterns
                    r"480p|SD",  # 480p patterns
                ]

                for pattern in resolution_patterns:
                    if re.search(pattern, file_path, re.IGNORECASE):
                        resolution = re.search(
                            pattern, file_path, re.IGNORECASE
                        ).group()
                        logger.info(f"Found resolution in path: {resolution}")

                        # Normalize to standard format
                        if re.search(r"2160p|4K|UHD", resolution, re.IGNORECASE):
                            return "WEBDL-2160p"  # Assume WEBDL for 4K
                        elif re.search(r"1080p|FHD", resolution, re.IGNORECASE):
                            return "WEBDL-1080p"
                        elif re.search(r"720p|HD", resolution, re.IGNORECASE):
                            return "WEBDL-720p"
                        elif re.search(r"480p|SD", resolution, re.IGNORECASE):
                            return "WEBDL-480p"

                # Look for source patterns
                source_patterns = [
                    (r"WEBDL|WEB-DL", "WEBDL"),
                    (r"WEBRip|WEB-Rip", "WEBRip"),
                    (r"BluRay|Blu-ray|BLURAY", "Bluray"),
                    (r"Remux|REMUX", "Remux"),
                    (r"HDTV", "HDTV"),
                ]

                source = "WEBDL"  # Default
                for pattern, source_name in source_patterns:
                    if re.search(pattern, file_path, re.IGNORECASE):
                        source = source_name
                        break

                # If we found a source but no resolution, assume 2160p for 4K folder
                if "/uhd-movies/" in file_path.lower() or "/4k" in file_path.lower():
                    return f"{source}-2160p"
                else:
                    return f"{source}-1080p"  # Default assumption

            # Method 3: Check relative path
            relative_path = movie_file.get("relativePath", "")
            if relative_path:
                logger.info(f"Checking relative path: {relative_path}")
                # Apply same logic as above
                if re.search(r"2160p|4K|UHD", relative_path, re.IGNORECASE):
                    return "WEBDL-2160p"
                elif re.search(r"1080p", relative_path, re.IGNORECASE):
                    return "WEBDL-1080p"

            # Method 4: Default based on folder structure
            if file_path and (
                "/uhd-movies/" in file_path.lower() or "/4k" in file_path.lower()
            ):
                logger.info("File in 4K folder, assuming 2160p quality")
                return "WEBDL-2160p"

            logger.warning(
                "Could not determine quality from payload, defaulting to WEBDL-1080p"
            )
            return "WEBDL-1080p"

        except Exception as e:
            logger.error(f"Error extracting quality from payload: {e}")
            return "WEBDL-1080p"

    def move_to_main_library(
        self,
        source_path: str,
        movie_title: str,
        movie_year: int,
        quality_title: str,
        k4_root_folders: List[Dict],
        main_root_folders: List[Dict],
    ) -> Dict:
        """Move file from 4K library to main library with optional Plex naming"""

        try:
            source_file = Path(source_path)
            if not source_file.exists():
                return {
                    "success": False,
                    "error": f"Source file not found: {source_path}",
                }

            # Get better quality from file analysis
            quality_title = self.get_quality_from_payload({"path": source_path})
            logger.info(f"Detected quality: {quality_title}")

            # Find root folder mappings
            source_root = self._find_matching_root_folder(source_path, k4_root_folders)
            target_root = self._get_target_root_folder(main_root_folders)

            if not source_root or not target_root:
                return {
                    "success": False,
                    "error": "Could not determine root folder mappings",
                }

            # Create destination directory using ORIGINAL movie title from file path, not Radarr API
            # Extract the actual folder name from the source path
            source_movie_folder = source_file.parent.name
            logger.info(f"📁 Using original folder name: {source_movie_folder}")

            destination_dir = Path(target_root) / source_movie_folder
            destination_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename based on configuration
            if self.config.enable_plex_naming and self.config.plex_quality_suffix:
                # Map quality to Plex-friendly format
                plex_quality = self._map_quality_to_plex(quality_title)

                # APPEND quality suffix to original filename (preserve everything)
                original_stem = source_file.stem  # filename without extension
                original_extension = source_file.suffix

                # Check if quality suffix already exists to avoid duplicates
                if self._has_quality_suffix(original_stem):
                    logger.info(
                        f"File already has quality suffix, keeping as-is: {source_file.name}"
                    )
                    new_filename = source_file.name
                else:
                    # Append the Plex quality to the original filename
                    new_filename = (
                        f"{original_stem} - {plex_quality}{original_extension}"
                    )
                    logger.info(
                        f"🏷️ Appending quality: {source_file.name} → {new_filename}"
                    )

                naming_mode = "Plex with quality suffix (appended)"
            else:
                # Keep the original filename exactly as Radarr named it
                new_filename = source_file.name
                naming_mode = "Original Radarr naming"

            destination_path = destination_dir / new_filename

            # Check if destination already exists
            if destination_path.exists():
                logger.warning(f"Destination file already exists: {destination_path}")
                # Generate unique filename
                counter = 1
                base_name = destination_path.stem
                extension = destination_path.suffix
                while destination_path.exists():
                    new_name = f"{base_name} ({counter}){extension}"
                    destination_path = destination_dir / new_name
                    counter += 1
                logger.info(f"Using unique filename: {destination_path.name}")

            # Rename existing files if Plex naming is enabled
            existing_files_renamed = []
            existing_files_errors = []

            if self.config.enable_plex_naming and self.config.plex_quality_suffix:
                # Extract title from folder name (remove year part)
                folder_title = (
                    source_movie_folder.split(" (")[0]
                    if " (" in source_movie_folder
                    else source_movie_folder
                )
                renamed, errors = self._rename_existing_files_for_plex_append(
                    destination_dir, folder_title, movie_year
                )
                existing_files_renamed = renamed
                existing_files_errors = errors

            # MOVE the file with detailed logging and permission handling
            move_result = self._move_file_with_logging(source_file, destination_path)

            # Clean up empty source directory if it's empty
            source_dir = source_file.parent
            try:
                if source_dir.exists() and not any(source_dir.iterdir()):
                    source_dir.rmdir()
                    logger.info(f"🗑️ Removed empty source directory: {source_dir}")
            except Exception as e:
                logger.warning(f"Could not remove source directory: {e}")

            return {
                "success": True,
                "destination_path": str(destination_path),
                "original_filename": source_file.name,
                "final_filename": destination_path.name,
                "naming_mode": naming_mode,
                "renamed": source_file.name != destination_path.name,
                "existing_files_renamed": existing_files_renamed,
                "existing_files_errors": existing_files_errors,
                "operation": move_result,
            }

        except Exception as e:
            logger.error(f"Error moving file to main library: {e}")
            return {"success": False, "error": str(e)}

    def _move_file_with_logging(self, source_file: Path, destination_path: Path) -> str:
        """Move file with detailed logging and permission handling"""
        try:
            start_time = time.time()
            source_stat = source_file.stat()
            source_size_mb = source_stat.st_size / (1024 * 1024)

            logger.info(f"🚚 Starting move operation...")
            logger.info(f"📊 File size: {source_size_mb:.1f} MB")
            logger.info(f"📁 Source: {source_file}")
            logger.info(f"📁 Destination: {destination_path}")

            # Check permissions on source file
            source_perms = oct(source_stat.st_mode)[-3:]
            logger.info(f"🔒 Source permissions: {source_perms}")
            logger.info(f"👤 Source owner: {source_stat.st_uid}:{source_stat.st_gid}")

            # Check if source and destination are on same filesystem
            source_dev = source_stat.st_dev
            dest_parent = destination_path.parent
            dest_parent.mkdir(parents=True, exist_ok=True)
            dest_stat = dest_parent.stat()
            dest_dev = dest_stat.st_dev

            same_filesystem = source_dev == dest_dev
            logger.info(f"🔍 Same filesystem: {same_filesystem}")
            logger.info(f"📊 Source device: {source_dev}, Dest device: {dest_dev}")

            if same_filesystem:
                logger.info("⚡ Same filesystem detected - should be instant rename!")
            else:
                logger.warning("🐌 Cross-filesystem move - will copy data")

            # Try to make source file writable before move (in case it's read-only)
            try:
                current_mode = source_file.stat().st_mode
                source_file.chmod(current_mode | stat.S_IWUSR | stat.S_IWGRP)
                logger.info("🔓 Made source file writable")
            except Exception as e:
                logger.warning(f"Could not modify source permissions: {e}")

            # Perform the move
            logger.info("🚚 Executing shutil.move()...")
            shutil.move(str(source_file), str(destination_path))

            end_time = time.time()
            duration = end_time - start_time

            if same_filesystem and duration > 2.0:
                logger.warning(
                    f"⚠️ Move took {duration:.2f}s - unexpectedly slow for same filesystem!"
                )
                logger.warning("💡 This might indicate:")
                logger.warning("   - Docker volume performance issues")
                logger.warning("   - File system doing unnecessary copying")
                logger.warning("   - Permission/ownership changes during move")
            elif same_filesystem:
                logger.info(
                    f"⚡ Move completed in {duration:.3f}s - filesystem operation!"
                )
            else:
                speed_mbps = source_size_mb / duration if duration > 0 else 0
                logger.info(
                    f"📊 Move completed in {duration:.2f}s ({speed_mbps:.1f} MB/s)"
                )

            # Check final file permissions
            final_stat = destination_path.stat()
            final_perms = oct(final_stat.st_mode)[-3:]
            logger.info(f"🔒 Final permissions: {final_perms}")
            logger.info(f"👤 Final owner: {final_stat.st_uid}:{final_stat.st_gid}")

            return "moved"

        except PermissionError as e:
            logger.error(f"❌ Permission denied during move: {e}")
            logger.error("💡 Possible solutions:")
            logger.error("   - Check Docker container user permissions")
            logger.error("   - Verify volume mount permissions")
            logger.error("   - Check file/directory ownership")
            raise
        except Exception as e:
            logger.error(f"❌ Move operation failed: {e}")
            raise

    def _find_matching_root_folder(
        self, file_path: str, root_folders: List[Dict]
    ) -> Optional[str]:
        """Find which root folder contains the file"""
        for folder in root_folders:
            root_path = folder.get("path", "")
            if file_path.startswith(root_path):
                return root_path
        return None

    def _get_target_root_folder(self, root_folders: List[Dict]) -> Optional[str]:
        """Get the first available root folder for main library"""
        if root_folders:
            return root_folders[0].get("path")
        return None

    def _map_quality_to_plex(self, radarr_quality: str) -> str:
        """Map Radarr quality to Plex-friendly format"""
        # Direct mapping
        if radarr_quality in self.quality_mappings:
            mapped = self.quality_mappings[radarr_quality]
            logger.info(f"Quality mapping: '{radarr_quality}' → '{mapped}'")
            return mapped

        # Pattern-based mapping for complex quality strings
        quality_lower = radarr_quality.lower()

        if "2160p" in quality_lower or "4k" in quality_lower or "uhd" in quality_lower:
            return "2160p"
        elif "1080p" in quality_lower or "fhd" in quality_lower:
            return "1080p"
        elif "720p" in quality_lower or "hd" in quality_lower:
            return "720p"
        elif "480p" in quality_lower or "sd" in quality_lower:
            return "480p"

        # Clean up the quality string and use as-is
        cleaned = re.sub(r"[^a-zA-Z0-9-]", "", radarr_quality)
        logger.warning(
            f"Could not map quality '{radarr_quality}', using cleaned version"
        )
        logger.info(f"Quality mapping: '{radarr_quality}' → '{cleaned}'")
        return cleaned or "1080p"

    def _rename_existing_files_for_plex_append(
        self, directory: Path, movie_title: str, movie_year: int
    ) -> Tuple[List[Tuple[str, str]], List[str]]:
        """Rename existing movie files to APPEND quality suffix for Plex merging"""
        renamed_files = []
        errors = []

        if not directory.exists():
            return renamed_files, errors

        for file_path in directory.iterdir():
            if (
                file_path.is_file()
                and file_path.suffix.lower() in self.video_extensions
            ):
                try:
                    original_name = file_path.name

                    # Check if file already has a quality suffix
                    if self._has_quality_suffix(file_path.stem):
                        logger.info(
                            f"File already has quality suffix, skipping: {original_name}"
                        )
                        continue

                    # Detect quality from filename
                    detected_quality = self._detect_quality_from_filename(
                        file_path.name
                    )

                    # APPEND quality suffix to existing filename (preserve everything)
                    original_stem = file_path.stem
                    original_extension = file_path.suffix
                    new_name = (
                        f"{original_stem} - {detected_quality}{original_extension}"
                    )
                    new_path = file_path.parent / new_name

                    if new_path.exists():
                        logger.warning(
                            f"Target filename already exists, skipping: {new_name}"
                        )
                        continue

                    file_path.rename(new_path)
                    renamed_files.append((original_name, new_name))
                    logger.info(
                        f"Renamed for Plex (appended): {original_name} → {new_name}"
                    )

                except Exception as e:
                    error_msg = f"Failed to rename {file_path.name}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)

        return renamed_files, errors

    def _has_quality_suffix(self, filename_stem: str) -> bool:
        """Check if filename already has a quality suffix at the end"""
        # Pattern matches: " - 1080p", " - 720p", " - 2160p", etc. at the END
        pattern = r" - \d{3,4}p$"
        return bool(re.search(pattern, filename_stem))

    def _detect_quality_from_filename(self, filename: str) -> str:
        """Detect quality from existing filename"""
        filename_lower = filename.lower()

        # Check for resolution indicators
        if re.search(r"2160p|4k|uhd", filename_lower):
            return "2160p"
        elif re.search(r"1080p|fhd", filename_lower):
            return "1080p"
        elif re.search(r"720p|hd", filename_lower):
            return "720p"
        elif re.search(r"480p|sd", filename_lower):
            return "480p"

        # Default assumption for existing files
        return "1080p"

    def get_quality_mapping_info(self) -> Dict:
        """Get information about quality mappings for debugging"""
        return {
            "total_mappings": len(self.quality_mappings),
            "supported_video_extensions": list(self.video_extensions),
            "quality_mappings": self.quality_mappings,
        }
