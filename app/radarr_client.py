import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RadarrClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update({"X-Api-Key": api_key})

    def test_connection(self) -> bool:
        """Test connection to Radarr API"""
        try:
            response = self.session.get(f"{self.base_url}/api/v3/system/status")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Failed to connect to Radarr: {e}")
            return False

    def get_root_folders(self) -> List[Dict]:
        """Get all root folders from Radarr"""
        try:
            response = self.session.get(f"{self.base_url}/api/v3/rootfolder")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get root folders: {e}")
            return []

    def remove_movie(
        self, movie_id: int, add_exclusion: bool = True, delete_files: bool = False
    ) -> Dict:
        """
        Remove movie from Radarr with optional list exclusion

        Args:
            movie_id: The Radarr movie ID
            add_exclusion: Whether to add the movie to import list exclusions
            delete_files: Whether to delete movie files (we don't want this)
        """
        try:
            # First, get movie details to extract TMDB ID for exclusion
            movie_details = self.get_movie_details(movie_id)
            if not movie_details:
                return {"success": False, "error": "Could not get movie details"}

            tmdb_id = movie_details.get("tmdbId")
            movie_title = movie_details.get("title", "Unknown")

            logger.info(
                f"🎬 Removing movie: {movie_title} (ID: {movie_id}, TMDB: {tmdb_id})"
            )
            logger.info(f"🚫 Add import exclusion: {add_exclusion}")

            # Remove the movie with exclusion parameter
            params = {
                "deleteFiles": str(delete_files).lower(),
                "addImportExclusion": str(add_exclusion).lower(),
            }

            response = self.session.delete(
                f"{self.base_url}/api/v3/movie/{movie_id}", params=params
            )
            response.raise_for_status()

            logger.info(f"✅ Movie '{movie_title}' removed from Radarr")

            if add_exclusion and tmdb_id:
                # Verify the exclusion was added (optional verification step)
                exclusion_added = self.verify_exclusion_added(tmdb_id)
                if exclusion_added:
                    logger.info(
                        f"🚫 Import list exclusion confirmed for TMDB ID {tmdb_id}"
                    )
                    logger.info(f"🔒 Movie will not be re-imported by import lists!")
                else:
                    logger.warning(
                        f"⚠️ Could not verify exclusion for TMDB ID {tmdb_id}"
                    )
                    logger.warning(f"💡 Movie might be re-imported on next sync")
            else:
                logger.info(f"📝 Movie removed without import exclusion")

            return {
                "success": True,
                "movie_id": movie_id,
                "tmdb_id": tmdb_id,
                "title": movie_title,
                "exclusion_added": add_exclusion,
                "exclusion_verified": add_exclusion
                and tmdb_id
                and self.verify_exclusion_added(tmdb_id),
            }

        except Exception as e:
            logger.error(f"❌ Failed to remove movie {movie_id}: {e}")
            return {"success": False, "error": str(e)}

    def get_movie_details(self, movie_id: int) -> Optional[Dict]:
        """Get detailed information about a movie"""
        try:
            response = self.session.get(f"{self.base_url}/api/v3/movie/{movie_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get movie details for ID {movie_id}: {e}")
            return None

    def verify_exclusion_added(self, tmdb_id: int) -> bool:
        """Verify that a movie was added to import list exclusions"""
        try:
            # Use the correct API endpoint for exclusions
            response = self.session.get(
                f"{self.base_url}/api/v3/exclusions/paged",
                params={"page": 1, "pageSize": 1000},
            )
            response.raise_for_status()
            exclusions_data = response.json()

            # Handle paged response format
            exclusions = (
                exclusions_data.get("records", [])
                if isinstance(exclusions_data, dict)
                else exclusions_data
            )

            # Check if our TMDB ID is in the exclusions
            for exclusion in exclusions:
                if exclusion.get("tmdbId") == tmdb_id:
                    logger.debug(
                        f"Found exclusion for TMDB {tmdb_id}: {exclusion.get('movieTitle', 'Unknown')}"
                    )
                    return True

            logger.debug(f"No exclusion found for TMDB {tmdb_id}")
            return False

        except Exception as e:
            logger.warning(f"Could not verify exclusion for TMDB ID {tmdb_id}: {e}")
            # Fallback to deprecated endpoint if paged fails
            try:
                response = self.session.get(f"{self.base_url}/api/v3/exclusions")
                response.raise_for_status()
                exclusions = response.json()

                for exclusion in exclusions:
                    if exclusion.get("tmdbId") == tmdb_id:
                        logger.debug(f"Found exclusion for TMDB {tmdb_id} (fallback)")
                        return True
                return False
            except Exception as fallback_e:
                logger.warning(f"Fallback exclusion check also failed: {fallback_e}")
                return False

    def get_import_list_exclusions(self) -> List[Dict]:
        """Get all import list exclusions"""
        try:
            # Try the preferred paged endpoint first
            response = self.session.get(
                f"{self.base_url}/api/v3/exclusions/paged",
                params={"page": 1, "pageSize": 1000},
            )
            response.raise_for_status()
            exclusions_data = response.json()

            # Handle paged response format
            if isinstance(exclusions_data, dict) and "records" in exclusions_data:
                exclusions = exclusions_data["records"]
            else:
                exclusions = exclusions_data

            logger.info(f"📋 Found {len(exclusions)} import list exclusions")
            return exclusions

        except Exception as e:
            logger.warning(f"Paged exclusions endpoint failed: {e}")
            # Fallback to deprecated endpoint
            try:
                response = self.session.get(f"{self.base_url}/api/v3/exclusions")
                response.raise_for_status()
                exclusions = response.json()
                logger.info(
                    f"📋 Found {len(exclusions)} import list exclusions (fallback)"
                )
                return exclusions
            except Exception as fallback_e:
                logger.error(f"Failed to get import list exclusions: {fallback_e}")
                return []

    def add_import_list_exclusion(
        self, tmdb_id: int, title: str, year: int = None
    ) -> Dict:
        """Manually add a movie to import list exclusions"""
        try:
            # Check if exclusion already exists
            existing_exclusions = self.get_import_list_exclusions()
            for exclusion in existing_exclusions:
                if exclusion.get("tmdbId") == tmdb_id:
                    logger.info(
                        f"Movie '{title}' (TMDB: {tmdb_id}) is already in exclusion list"
                    )
                    return {
                        "success": True,
                        "tmdb_id": tmdb_id,
                        "title": title,
                        "already_exists": True,
                    }

            # Create exclusion data
            data = {"tmdbId": tmdb_id, "movieTitle": title}

            # Add year if provided
            if year:
                data["movieYear"] = year

            response = self.session.post(
                f"{self.base_url}/api/v3/exclusions", json=data
            )
            response.raise_for_status()

            logger.info(
                f"✅ Manually added import list exclusion for '{title}' (TMDB: {tmdb_id})"
            )

            # Verify the exclusion was added
            if self.verify_exclusion_added(tmdb_id):
                logger.info(f"🔒 Exclusion verified for '{title}'")
                return {
                    "success": True,
                    "tmdb_id": tmdb_id,
                    "title": title,
                    "verified": True,
                }
            else:
                logger.warning(f"⚠️ Could not verify exclusion for '{title}'")
                return {
                    "success": True,
                    "tmdb_id": tmdb_id,
                    "title": title,
                    "verified": False,
                }

        except Exception as e:
            logger.error(f"Failed to add import list exclusion for TMDB {tmdb_id}: {e}")
            return {"success": False, "error": str(e)}

    def remove_import_list_exclusion(self, exclusion_id: int) -> Dict:
        """Remove a movie from import list exclusions"""
        try:
            response = self.session.delete(
                f"{self.base_url}/api/v3/exclusions/{exclusion_id}"
            )
            response.raise_for_status()

            logger.info(f"✅ Removed import list exclusion ID {exclusion_id}")
            return {"success": True, "exclusion_id": exclusion_id}

        except Exception as e:
            logger.error(f"Failed to remove import list exclusion {exclusion_id}: {e}")
            return {"success": False, "error": str(e)}

    def get_movie_by_tmdb_id(self, tmdb_id: int) -> Optional[Dict]:
        """Find a movie in Radarr by TMDB ID"""
        try:
            response = self.session.get(f"{self.base_url}/api/v3/movie")
            response.raise_for_status()
            movies = response.json()

            for movie in movies:
                if movie.get("tmdbId") == tmdb_id:
                    return movie

            return None

        except Exception as e:
            logger.error(f"Failed to search for movie with TMDB ID {tmdb_id}: {e}")
            return None
