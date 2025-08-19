#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crypto Configuration Loader
Utility to load and access cryptocurrency trading configuration
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path

class CryptoConfigLoader:
    """Load and access cryptocurrency trading configuration"""
    
    def __init__(self, config_file: str = None):
        """
        Initialize the loader
        
        Args:
            config_file: Path to configuration file
        """
        if config_file is None:
            # Default to the main config file
            config_file = os.path.join(os.path.dirname(__file__), 'crypto_trading_config.json')
        
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"❌ Error loading configuration: {e}")
            return {}
    
    def get_crypto_config(self, crypto: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a specific cryptocurrency
        
        Args:
            crypto: Cryptocurrency symbol (e.g., 'BTC-USDT')
            
        Returns:
            Configuration dictionary or None if not found
        """
        return self.config.get('cryptocurrencies', {}).get(crypto)
    
    def get_limit(self, crypto: str) -> Optional[str]:
        """Get optimal limit for a cryptocurrency"""
        config = self.get_crypto_config(crypto)
        return config.get('limit') if config else None
    
    def get_duration(self, crypto: str) -> Optional[str]:
        """Get optimal duration for a cryptocurrency"""
        config = self.get_crypto_config(crypto)
        return config.get('duration') if config else None
    
    def get_expected_return(self, crypto: str) -> Optional[float]:
        """Get expected return for a cryptocurrency"""
        config = self.get_crypto_config(crypto)
        return config.get('expected_return') if config else None
    
    def get_trade_frequency(self, crypto: str) -> Optional[float]:
        """Get trade frequency for a cryptocurrency"""
        config = self.get_crypto_config(crypto)
        return config.get('trade_frequency') if config else None
    
    def list_cryptos(self) -> list:
        """Get list of all configured cryptocurrencies"""
        return list(self.config.get('cryptocurrencies', {}).keys())
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary"""
        cryptos = self.config.get('cryptocurrencies', {})
        return {
            'total_cryptos': len(cryptos),
            'generated_at': self.config.get('generated_at'),
            'source_analysis': self.config.get('source_analysis'),
            'description': self.config.get('description')
        }
    
    def reload_config(self):
        """Reload configuration from file"""
        self.config = self._load_config()

def main():
    """Test the configuration loader"""
    print("🧪 Testing Crypto Configuration Loader")
    print("=" * 40)
    
    loader = CryptoConfigLoader()
    
    # Get summary
    summary = loader.get_config_summary()
    print(f"📊 Configuration Summary:")
    print(f"   Total cryptocurrencies: {summary['total_cryptos']}")
    print(f"   Generated at: {summary['generated_at']}")
    print(f"   Description: {summary['description']}")
    
    # Test with a few cryptocurrencies
    test_cryptos = ['BTC-USDT', 'ETH-USDT', 'ADA-USDT']
    
    print(f"\n🔍 Sample Configurations:")
    for crypto in test_cryptos:
        config = loader.get_crypto_config(crypto)
        if config:
            print(f"   {crypto}:")
            print(f"     Limit: {config['limit']}%")
            print(f"     Duration: {config['duration']} days")
            print(f"     Expected Return: {config['expected_return']:.2f}x")
            print(f"     Trade Frequency: {config['trade_frequency']:.2f}/month")
        else:
            print(f"   {crypto}: Not found")

if __name__ == "__main__":
    main()
