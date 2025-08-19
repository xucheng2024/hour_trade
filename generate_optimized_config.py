#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Optimized Trading Configuration
Run strategy_optimizer to generate trading configuration with latest improvements
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

def generate_optimized_config():
    """Generate optimized trading configuration using strategy_optimizer"""
    
    try:
        from src.strategies.strategy_optimizer import get_strategy_optimizer
        from src.data.data_manager import SELECTED_CRYPTOS
        
        print("🚀 Generating Optimized Trading Configuration")
        print("=" * 50)
        
        # Get strategy optimizer
        optimizer = get_strategy_optimizer(buy_fee=0.001, sell_fee=0.001)
        print("✅ Strategy optimizer initialized")
        
        # Get cryptocurrency list
        crypto_list = SELECTED_CRYPTOS
        print(f"📊 Found {len(crypto_list)} cryptocurrencies")
        
        # Configuration structure
        config = {
            'generated_at': datetime.now().isoformat(),
            'description': 'Optimized trading configuration with latest strategy improvements',
            'improvements': [
                'Returns rounded to 2 decimal places for consistent comparison',
                'When returns are equal, prefer shorter duration strategies',
                'When returns and duration are equal, prefer lower limit (more conservative)',
                'No profit correction - pure market performance',
                'Vectorized operations for optimal performance',
                'Overlap prevention for realistic trading frequency'
            ],
            'strategy_type': '1d',  # Daily strategy
            'timeframe': '1D',
            'start_timestamp': 0,  # Use all available data
            'end_timestamp': 0,    # Use all available data
            'cryptocurrencies': {}
        }
        
        # Process each cryptocurrency
        successful_count = 0
        failed_count = 0
        
        for crypto in crypto_list:
            print(f"\n🔍 Processing {crypto}...")
            
            try:
                # Optimize strategy for this cryptocurrency
                result = optimizer.optimize_1d_strategy(
                    instId=crypto,
                    start=0,  # Use all available data
                    end=0,    # Use all available data
                    date_dict={},
                    bar="1D"
                )
                
                if result and crypto in result:
                    crypto_data = result[crypto]
                    
                    # Extract parameters
                    limit = crypto_data.get('best_limit', '0')
                    duration = crypto_data.get('best_duration', '0')
                    max_returns = crypto_data.get('max_returns', '1.0')
                    trade_count = crypto_data.get('trade_count', '0')
                    trades_per_month = crypto_data.get('trades_per_month', '0.0')
                    
                    # Add to configuration
                    config['cryptocurrencies'][crypto] = {
                        'limit': limit,
                        'duration': duration,
                        'expected_return': float(max_returns),
                        'trade_count': int(trade_count),
                        'trade_frequency': float(trades_per_month),
                        'notes': f"Based on {trade_count} trades with latest optimization strategy"
                    }
                    
                    successful_count += 1
                    print(f"✅ {crypto}: limit={limit}%, duration={duration}, returns={max_returns}")
                else:
                    failed_count += 1
                    print(f"❌ {crypto}: No valid strategy found")
                    
            except Exception as e:
                failed_count += 1
                print(f"❌ {crypto}: Error - {e}")
                continue
        
        # Summary
        print(f"\n📊 Summary:")
        print(f"✅ Successful: {successful_count}")
        print(f"❌ Failed: {failed_count}")
        print(f"📁 Total: {len(crypto_list)}")
        
        # Save configuration
        config_file = Path(__file__).parent / 'trading_config_optimized_2025.json'
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"\n💾 Configuration saved to: {config_file}")
        print(f"📊 Generated config for {successful_count} cryptocurrencies")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    if generate_optimized_config():
        print("\n✅ Optimized configuration generation completed!")
    else:
        print("\n❌ Configuration generation failed!")
        sys.exit(1)
