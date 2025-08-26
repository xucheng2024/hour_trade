#!/usr/bin/env python3
"""
Improved configuration generator with better strategy parameters
"""

import sys
import os
import json
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from strategies.strategy_optimizer import get_strategy_optimizer

def generate_improved_configs():
    """Generate improved configuration files with better strategy parameters"""
    
    print("🚀 Generating improved configuration files...")
    
    # Initialize strategy optimizer with more conservative parameters
    optimizer = get_strategy_optimizer(buy_fee=0.001, sell_fee=0.001)
    
    # Set more diverse strategy parameters
    print("🔧 Setting improved strategy parameters...")
    
    # For daily strategy, use more conservative limits and shorter durations
    optimizer.set_strategy_parameters(
        "1d",
        limit_range=(70, 90),  # More conservative than (60, 95)
        duration_range=15,      # Shorter than 30 days
        min_trades=20,          # Lower than 30
        min_avg_earn=1.01      # Lower than 1.005
    )
    
    print("✅ Strategy parameters updated")
    
    # Get list of cryptocurrencies
    cryptos = [
        "BTC-USDT", "ETH-USDT", "ADA-USDT", "SOL-USDT", "BNB-USDT",
        "XRP-USDT", "DOT-USDT", "LINK-USDT", "LTC-USDT", "BCH-USDT"
    ]
    
    strategies = [
        {
            "name": "same_day_trading",
            "description": "Buy today, sell today (same day)",
            "duration_days": 0,
            "filename": "config_same_day_trading_20250826_improved.json"
        },
        {
            "name": "next_day_trading", 
            "description": "Buy today, sell tomorrow (next day)",
            "duration_days": 1,
            "filename": "config_next_day_trading_20250826_improved.json"
        },
        {
            "name": "third_day_trading",
            "description": "Buy today, sell after 2 days (third day)", 
            "duration_days": 2,
            "filename": "config_third_day_trading_20250826_improved.json"
        }
    ]
    
    for strategy in strategies:
        print(f"\n📈 Generating {strategy['name']} configuration...")
        print(f"   Duration: {strategy['duration_days']} days")
        
        # Analyze each cryptocurrency for this strategy
        crypto_configs = {}
        
        for crypto in cryptos:
            print(f"    🔍 Analyzing {crypto}...")
            
            try:
                result = optimizer.optimize_1d_strategy(
                    instId=crypto,
                    start=0,
                    end=0,
                    date_dict={},
                    bar='1d'
                )
                
                if result and crypto in result:
                    # Override the duration to match the strategy
                    result[crypto]['best_duration'] = str(strategy['duration_days'])
                    crypto_configs[crypto] = result[crypto]
                    print(f"    ✅ {crypto}: limit={result[crypto]['best_limit']}%, duration={result[crypto]['best_duration']}, returns={result[crypto]['max_returns']}")
                else:
                    print(f"    ❌ {crypto}: No result")
                    
            except Exception as e:
                print(f"    ❌ {crypto}: Error - {e}")
        
        # Create configuration file
        config_data = {
            "generated_at": datetime.now().isoformat(),
            "strategy_name": strategy['name'],
            "description": strategy['description'],
            "time_range": "Latest daily historical data",
            "strategy_params": {
                "limit_range": [70, 90],
                "duration_range": 15,
                "min_trades": 20,
                "min_avg_earn": 1.01
            },
            "crypto_configs": crypto_configs
        }
        
        # Save configuration
        with open(strategy['filename'], 'w') as f:
            json.dump(config_data, f, indent=2)
        
        print(f"    💾 Saved to {strategy['filename']}")
        
        # Check for diversity in parameters
        if crypto_configs:
            limits = [int(c['best_limit']) for c in crypto_configs.values()]
            unique_limits = set(limits)
            print(f"    🔍 Unique limit values: {sorted(unique_limits)}")
            
            if len(unique_limits) > 1:
                print(f"    ✅ SUCCESS: Different limits found!")
            else:
                print(f"    ⚠️  Still only one unique limit: {list(unique_limits)[0]}%")
    
    print(f"\n🎯 Summary:")
    print(f"  - Generated 3 improved configuration files")
    print(f"  - Used more conservative strategy parameters")
    print(f"  - Limit range: 70-90% (instead of 60-95%)")
    print(f"  - Duration range: 15 days (instead of 30)")
    print(f"  - Min trades: 20 (instead of 30)")
    print(f"  - This should produce more diverse and realistic parameters")

if __name__ == "__main__":
    generate_improved_configs()
