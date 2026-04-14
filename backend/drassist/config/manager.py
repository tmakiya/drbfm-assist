"""Generic configuration manager for YAML and environment variables"""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


class ConfigManager:
    """Generic configuration manager for YAML and environment variables"""

    def __init__(self, config_path: str = "config.yaml", load_env: bool = True):
        """Initialize configuration manager

        Args:
            config_path: Path to YAML configuration file
            load_env: Whether to load environment variables from .env file

        """
        if load_env:
            load_dotenv()

        self.config_path = Path(config_path)
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.yaml_config = yaml.safe_load(f)

    def get(self, key_path: str, default: Any = None) -> Any:
        """Get configuration value using dot notation

        Args:
            key_path: Dot-separated path to the configuration key (e.g., 'data.filepath')
            default: Default value if key is not found

        Returns:
            Configuration value or default

        """
        keys = key_path.split(".")
        value = self.yaml_config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any) -> None:
        """Set configuration value using dot notation

        Args:
            key_path: Dot-separated path to the configuration key
            value: Value to set

        """
        keys = key_path.split(".")
        config = self.yaml_config

        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            config = config[key]

        config[keys[-1]] = value

    def get_env(self, key: str, default: str = "") -> str:
        """Get environment variable value"""
        return os.getenv(key, default)

    def __getattr__(self, name: str) -> Any:
        """Enable property access to configuration values using underscore notation

        Converts underscore-separated attribute names to dot-separated key paths
        Example: config.data_filepath -> config.get("data.filepath")

        Args:
            name: Attribute name with underscores

        Returns:
            Configuration value

        Raises:
            AttributeError: If the configuration key is not found

        """
        # Convert underscores to dots for YAML key path
        key_path = name.replace("_", ".")

        # Try to get the value using existing get method
        value = self.get(key_path)

        if value is None:
            raise AttributeError(
                f"'{self.__class__.__name__}' object has no attribute '{name}' (config key '{key_path}' not found)"  # noqa: E501
            )

        return value
