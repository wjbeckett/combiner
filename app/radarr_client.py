import requests
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class RadarrClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.session = requests.Session()
        self.session.headers.update(
            {"X-Api-Key": api_key, "Content-Type": "application/json"}
        )

    def get_root_folders(self) -> List[Dict]:
        """Get root folder configurations from Radarr"""
        try:
            response = self.session.get(f"{self.base_url}/api/v3/rootfolder")
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"Failed to get root folders: {e}")
            return []

    def remove_movie(self, movie_id: int, delete_files: bool = False) -> Dict:
        """Remove a movie from Radarr"""
        try:
            params = {
                "deleteFiles": "true" if delete_files else "false",
                "addImportExclusion": "false",
            }

            response = self.session.delete(
                f"{self.base_url}/api/v3/movie/{movie_id}", params=params
            )
            response.raise_for_status()

            logger.info(f"Successfully removed movie ID {movie_id} from Radarr")
            return {"success": True}

        except requests.RequestException as e:
            logger.error(f"Failed to remove movie ID {movie_id}: {e}")
            return {"success": False, "error": str(e)}

    def test_connection(self) -> bool:
        """Test connection to Radarr API"""
        try:
            response = self.session.get(f"{self.base_url}/api/v3/system/status")
            response.raise_for_status()
            logger.info(f"Successfully connected to Radarr at {self.base_url}")
            return True
        except requests.RequestException as e:
            logger.error(f"Failed to connect to Radarr at {self.base_url}: {e}")
            return False
