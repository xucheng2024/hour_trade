#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Configuration Module
Centralized configuration for all OKX-related operations
"""

import json
import os
from pathlib import Path
from typing import Any, Dict


class OKXConfig:
    """Centralized configuration for OKX operations"""

    def __init__(self, config_file: str = None):
        """
        Initialize configuration

        Args:
            config_file: Path to configuration file (optional)
        """
        self.config_file = config_file
        self.config = self._load_config()
        self._setup_paths()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file or use defaults"""
        default_config = {
            # API Configuration
            "trading_flag": "0",  # 0=production, 1=demo
            "api_retry_attempts": 5,
            "api_retry_delay": 10,
            "rate_limit_delay": 0.15,
            # Paths
            "project_root": None,  # Will be auto-detected
            "data_directory": "data",
            "crypto_list_file": "src/config/cryptos_selected.json",
            "log_file": "data_fetch.log",
            # Data Configuration
            "default_timeframes": ["1H"],
            "max_workers": 1,
            # File Extensions
            "data_file_extension": ".npz",
            # Logging
            "log_level": "INFO",
            "log_format": "%(asctime)s - %(levelname)s - %(message)s",
        }

        # Try to load from config file
        if self.config_file and os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    file_config = json.load(f)
                default_config.update(file_config)
                print(f"✅ Loaded configuration from {self.config_file}")
            except Exception as e:
                print(
                    f"⚠️  Warning: Could not load config file "
                    f"{self.config_file}: {e}"
                )
                print("   Using default configuration")

        # Try to load from environment variables
        env_config = self._load_from_env()
        default_config.update(env_config)

        return default_config

    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables"""
        env_config = {}

        # API Configuration
        if os.getenv("OKX_TRADING_FLAG"):
            env_config["trading_flag"] = os.getenv("OKX_TRADING_FLAG")

        if os.getenv("OKX_API_RETRY_ATTEMPTS"):
            env_config["api_retry_attempts"] = int(os.getenv("OKX_API_RETRY_ATTEMPTS"))

        if os.getenv("OKX_API_RETRY_DELAY"):
            env_config["api_retry_delay"] = int(os.getenv("OKX_API_RETRY_DELAY"))

        if os.getenv("OKX_RATE_LIMIT_DELAY"):
            env_config["rate_limit_delay"] = float(os.getenv("OKX_RATE_LIMIT_DELAY"))

        # Paths
        if os.getenv("OKX_PROJECT_ROOT"):
            env_config["project_root"] = os.getenv("OKX_PROJECT_ROOT")

        if os.getenv("OKX_DATA_DIRECTORY"):
            env_config["data_directory"] = os.getenv("OKX_DATA_DIRECTORY")

        if os.getenv("OKX_CRYPTO_LIST_FILE"):
            env_config["crypto_list_file"] = os.getenv("OKX_CRYPTO_LIST_FILE")

        if os.getenv("OKX_LOG_FILE"):
            env_config["log_file"] = os.getenv("OKX_LOG_FILE")

        # Logging
        if os.getenv("OKX_LOG_LEVEL"):
            env_config["log_level"] = os.getenv("OKX_LOG_LEVEL")

        return env_config

    def _setup_paths(self) -> None:
        """Setup and validate all paths"""
        # Auto-detect project root if not specified
        if not self.config["project_root"]:
            # Try to find project root by looking for common files
            current_dir = Path(__file__).parent
            while current_dir.parent != current_dir:
                if (
                    (current_dir / "requirements.txt").exists()
                    or (current_dir / "main.py").exists()
                    or (current_dir / "src").exists()
                ):
                    self.config["project_root"] = str(current_dir)
                    break
                current_dir = current_dir.parent

            if not self.config["project_root"]:
                # Fallback to current working directory
                self.config["project_root"] = os.getcwd()

        # Convert relative paths to absolute paths
        project_root = Path(self.config["project_root"])

        if not os.path.isabs(self.config["data_directory"]):
            self.config["data_directory"] = str(
                project_root / self.config["data_directory"]
            )

        if not os.path.isabs(self.config["crypto_list_file"]):
            self.config["crypto_list_file"] = str(
                project_root / self.config["crypto_list_file"]
            )

        if not os.path.isabs(self.config["log_file"]):
            self.config["log_file"] = str(project_root / self.config["log_file"])

        # Ensure directories exist
        os.makedirs(self.config["data_directory"], exist_ok=True)
        os.makedirs(Path(self.config["log_file"]).parent, exist_ok=True)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value"""
        return self.config.get(key, default)

    def get_path(self, key: str) -> str:
        """Get configuration path value"""
        return self.config.get(key, "")

    def get_int(self, key: str, default: int = 0) -> int:
        """Get configuration integer value"""
        try:
            return int(self.config.get(key, default))
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get configuration float value"""
        try:
            return float(self.config.get(key, default))
        except (ValueError, TypeError):
            return default

    def get_list(self, key: str, default: list = None) -> list:
        """Get configuration list value"""
        if default is None:
            default = []
        value = self.config.get(key, default)
        if isinstance(value, list):
            return value
        return default

    def update(self, key: str, value: Any) -> None:
        """Update configuration value"""
        self.config[key] = value

    def save_config(self, file_path: str = None) -> None:
        """Save current configuration to file"""
        if not file_path:
            file_path = self.config_file or "trading_config.json"

        try:
            with open(file_path, "w") as f:
                json.dump(self.config, f, indent=2)
            print(f"✅ Configuration saved to {file_path}")
        except Exception as e:
            print(f"❌ Error saving configuration: {e}")

    def print_config(self) -> None:
        """Print current configuration"""
        print("🔧 Current OKX Configuration:")
        print("=" * 50)
        for key, value in self.config.items():
            print(f"  {key}: {value}")
        print("=" * 50)


# Global configuration instance
config = OKXConfig()


# Convenience functions
def get_config() -> OKXConfig:
    """Get global configuration instance"""
    return config


def get_project_root() -> str:
    """Get project root directory"""
    return config.get_path("project_root")


def get_data_directory() -> str:
    """Get data directory path"""
    return config.get_path("data_directory")


def get_crypto_list_file() -> str:
    """Get cryptocurrency list file path"""
    return config.get_path("crypto_list_file")


def get_log_file() -> str:
    """Get log file path"""
    return config.get_path("log_file")
