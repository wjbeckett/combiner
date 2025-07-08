import os
import yaml
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Config:
    def __init__(self):
        self.config_dir = Path("/config")
        self.load_config()

    def load_config(self):
        """Load configuration from environment variables or config file"""

        # Try to load from config file first
        config_file = self.config_dir / "config.yml"
        config_data = {}

        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    config_data = yaml.safe_load(f)
                logger.info(f"Loaded configuration from {config_file}")
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}")
                config_data = {}
        else:
            logger.info(f"Config file not found at {config_file}, using environment variables only")

        # Radarr configuration
        radarr_config = config_data.get("radarr", {})
        radarr_main = radarr_config.get("main", {})
        radarr_4k = radarr_config.get("4k", {})

        self.radarr_main_url = radarr_main.get("url")
        self.radarr_main_api_key = radarr_main.get("api_key")
        self.radarr_4k_url = radarr_4k.get("url")
        self.radarr_4k_api_key = radarr_4k.get("api_key")

        # Plex naming configuration
        plex_config = config_data.get("plex_naming", {})
        self.enable_plex_naming = plex_config.get("enabled", False)
        self.plex_quality_suffix = plex_config.get("add_quality_suffix", True)

        # Override with environment variables
        self.radarr_main_url = os.getenv("RADARR_MAIN_URL", self.radarr_main_url)
        self.radarr_main_api_key = os.getenv(
            "RADARR_MAIN_API_KEY", self.radarr_main_api_key
        )
        self.radarr_4k_url = os.getenv("RADARR_4K_URL", self.radarr_4k_url)
        self.radarr_4k_api_key = os.getenv("RADARR_4K_API_KEY", self.radarr_4k_api_key)

        # Plex naming environment variables
        self.enable_plex_naming = (
            os.getenv("ENABLE_PLEX_NAMING", str(self.enable_plex_naming)).lower()
            == "true"
        )
        self.plex_quality_suffix = (
            os.getenv("PLEX_QUALITY_SUFFIX", str(self.plex_quality_suffix)).lower()
            == "true"
        )

        # Validate required config
        required_configs = [
            ("RADARR_MAIN_URL", self.radarr_main_url),
            ("RADARR_MAIN_API_KEY", self.radarr_main_api_key),
            ("RADARR_4K_URL", self.radarr_4k_url),
            ("RADARR_4K_API_KEY", self.radarr_4k_api_key),
        ]

        missing_configs = [name for name, value in required_configs if not value]

        if missing_configs:
            raise ValueError(
                f"Missing required configuration: {', '.join(missing_configs)}"
            )

        logger.info("Configuration loaded successfully")
        logger.info(f"Plex naming enabled: {self.enable_plex_naming}")
        if self.enable_plex_naming:
            logger.info(f"Quality suffix enabled: {self.plex_quality_suffix}")

    def get_log_file_path(self) -> Path:
        """Get path for log file in config directory"""
        return self.config_dir / "combiner.log"

    def ensure_config_dir(self):
        """Ensure config directory exists"""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Config directory ready: {self.config_dir}")