#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Trading Configuration
Generate trading configuration file based on historical data analysis
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def generate_trading_config():
    """Generate trading configuration from historical analysis"""
    
    # Look for the most recent analysis file
    analysis_dir = Path(__file__).parent / 'src' / 'analysis'
    data_dir = Path(__file__).parent / 'data'
    
    # Search in both directories
    analysis_files = []
    for search_dir in [analysis_dir, data_dir]:
        if search_dir.exists():
            files = list(search_dir.glob("daily_strategy_*days_*.json"))
            analysis_files.extend(files)
    
    if not analysis_files:
        print("❌ No analysis files found")
        return False
    
    # Get the most recent file
    latest_file = max(analysis_files, key=lambda x: x.stat().st_mtime)
    print(f"📁 Using analysis file: {latest_file.name}")
    
    # Load analysis data
    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            analysis_data = json.load(f)
    except Exception as e:
        print(f"❌ Error loading analysis file: {e}")
        return False
    
    # Generate configuration
    config = {
        'generated_at': datetime.now().isoformat(),
        'source_analysis': str(latest_file),
        'description': 'Trading configuration based on historical analysis',
        'cryptocurrencies': {}
    }
    
    # Extract trading parameters for each cryptocurrency
    cryptos_data = analysis_data.get('cryptocurrencies', {})
    
    for crypto, data in cryptos_data.items():
        if data.get('analysis_success', False):
            config['cryptocurrencies'][crypto] = {
                'limit': data.get('best_limit', '0'),
                'duration': data.get('best_duration', '0'),
                'expected_return': data.get('max_returns', 1.0),
                'trade_frequency': data.get('trades_per_month', 0.0),
                'notes': f"Based on {data.get('trade_count', 0)} trades"
            }
    
    # Save configuration to config directory
    config_dir = Path(__file__).parent / 'src' / 'config'
    config_file = config_dir / 'trading_config.json'
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False, default=str)
        print(f"✅ Configuration saved to: {config_file}")
        print(f"📊 Generated config for {len(config['cryptocurrencies'])} cryptocurrencies")
        return True
    except Exception as e:
        print(f"❌ Error saving configuration: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Generating Trading Configuration")
    print("=" * 40)
    
    if generate_trading_config():
        print("\n✅ Configuration generation completed!")
    else:
        print("\n❌ Configuration generation failed!")
        sys.exit(1)
