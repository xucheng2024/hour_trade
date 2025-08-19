"""
Configuration module.
Contains configuration files and settings for the trading bot.
"""

import os
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).parent

def load_config(filename):
    """Load configuration from JSON file."""
    config_path = CONFIG_DIR / filename
    if config_path.exists():
        with open(config_path, 'r') as f:
            return json.load(f)
    return {}

def get_cryptos_selected():
    """Get selected cryptocurrencies configuration."""
    return load_config('cryptos_selected.json')

def get_limits(timeframe):
    """Get limits configuration for specific timeframe."""
    return load_config(f'limits_{timeframe}.json')

__all__ = [
    'load_config',
    'get_cryptos_selected',
    'get_limits'
]
