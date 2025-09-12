#!/usr/bin/env python3
"""
Generate config_d0_baseline.json configuration with strict trade_count requirements
"""

import sys
import os
import json
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from strategies.strategy_optimizer import get_strategy_optimizer
from config import load_config

def load_crypto_list():
    """Load cryptocurrency list from config"""
    try:
        # Try to load from src/config/cryptos_selected.json
        import json
        config_path = os.path.join('src', 'config', 'cryptos_selected.json')
        with open(config_path, 'r') as f:
            cryptos_config = json.load(f)
        
        if isinstance(cryptos_config, list):
            # Direct list of cryptos
            return cryptos_config
        elif isinstance(cryptos_config, dict):
            if 'cryptos' in cryptos_config:
                return cryptos_config['cryptos']
            else:
                # If it's a dict with crypto symbols as keys, return the keys
                return list(cryptos_config.keys())
        else:
            return []
    except Exception as e:
        print(f"⚠️  Could not load crypto list from config: {e}")
        print("    Using fallback crypto list...")
        # Fallback to a comprehensive list based on the current config
        return [
            "BTC-USDT", "ETH-USDT", "ADA-USDT", "SOL-USDT", "BNB-USDT",
            "XRP-USDT", "DOT-USDT", "LINK-USDT", "LTC-USDT", "BCH-USDT",
            "UNI-USDT", "AVAX-USDT", "AAVE-USDT", "NEAR-USDT", "DOGE-USDT",
            "SHIB-USDT", "TON-USDT", "PEPE-USDT", "TRX-USDT", "HBAR-USDT"
        ]

def generate_d0_baseline_config():
    """Generate Duration 0 baseline configuration with strict trade requirements"""
    
    print("🚀 Generating config_d0_baseline.json with strict trade_count requirements...")
    
    # Initialize strategy optimizer with realistic fees
    optimizer = get_strategy_optimizer(buy_fee=0.001, sell_fee=0.001)
    
    # Set strict strategy parameters for D0 (same-day trading)
    print("🔧 Setting strict D0 strategy parameters...")
    
    optimizer.set_strategy_parameters(
        "1d",
        limit_range=(60, 99),   # Original limit range from previous config
        duration_range=1,       # Only test duration 0 (same-day)
        min_trades=30,          # Stricter than original (was 5), but you want >=30
        min_avg_earn=1.01       # 1% return requirement
    )
    
    print("✅ Strategy parameters updated")
    
    # Get list of cryptocurrencies
    cryptos = load_crypto_list()
    print(f"📋 Found {len(cryptos)} cryptocurrencies to analyze")
    
    # Analyze each cryptocurrency for Duration 0 strategy
    crypto_configs = {}
    skipped_cryptos = []
    
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
                trade_count = int(result[crypto]['trade_count'])
                
                # Apply filtering: Only include cryptos with at least 30 trades  
                if trade_count >= 30:
                    # Force duration to 0 for D0 strategy
                    result[crypto]['best_duration'] = "0"
                    crypto_configs[crypto] = result[crypto]
                    print(f"    ✅ {crypto}: limit={result[crypto]['best_limit']}%, "
                          f"duration={result[crypto]['best_duration']}, "
                          f"returns={result[crypto]['max_returns']}, "
                          f"trades={trade_count}")
                else:
                    skipped_cryptos.append((crypto, trade_count))
                    print(f"    ❌ {crypto}: SKIPPED - Only {trade_count} trades (minimum: 30)")
            else:
                skipped_cryptos.append((crypto, 0))
                print(f"    ❌ {crypto}: No optimization result")
                
        except Exception as e:
            skipped_cryptos.append((crypto, 0))
            print(f"    ❌ {crypto}: Error - {e}")
    
    # Calculate average return for each crypto and filter out low performers
    # Average return = (total_returns)^(1/trade_count) - this gives the geometric mean per trade
    filtered_crypto_configs = {}
    low_performers = []
    
    for crypto, config in crypto_configs.items():
        total_returns = float(config['max_returns'])
        trade_count = int(config['trade_count'])
        # Calculate average return per trade (geometric mean)
        if trade_count > 0 and total_returns > 0:
            avg_return_per_trade = (total_returns ** (1/trade_count)) - 1
            config['avg_return_per_trade'] = f"{avg_return_per_trade:.4f}"
            
            # Filter out cryptos with avg_return_per_trade < 0.009 (0.9%)
            if avg_return_per_trade >= 0.009:
                filtered_crypto_configs[crypto] = config
            else:
                low_performers.append((crypto, avg_return_per_trade))
                print(f"    ❌ {crypto}: FILTERED - avg_return_per_trade={avg_return_per_trade:.4f} < 0.009")
        else:
            config['avg_return_per_trade'] = "0.0000"
            low_performers.append((crypto, 0.0))
            print(f"    ❌ {crypto}: FILTERED - invalid returns")
    
    # Sort filtered crypto_configs by average return per trade (descending order)
    sorted_crypto_configs = dict(sorted(
        filtered_crypto_configs.items(), 
        key=lambda item: float(item[1]['avg_return_per_trade']), 
        reverse=True
    ))
    
    # Create configuration file
    config_data = {
        "generated_at": datetime.now().isoformat(),
        "strategy_name": "duration_0_baseline",
        "description": "Duration 0 baseline configuration - same day trading strategy with min_trades=30",
        "strategy_type": "same_day",
        "duration": 0,
        "strategy_params": {
            "limit_range": [60, 99],
            "min_trades": 30,  # Stricter minimum requirement
            "min_avg_earn": 1.01,
            "buy_fee": 0.001,
            "sell_fee": 0.001
        },
        "crypto_configs": sorted_crypto_configs
    }
    
    # Save configuration
    filename = "config_d0_baseline.json"
    with open(filename, 'w') as f:
        json.dump(config_data, f, indent=2)
    
    print(f"\n💾 Saved to {filename}")
    
    # Summary statistics
    print(f"\n🎯 Summary:")
    print(f"  - Total cryptocurrencies analyzed: {len(cryptos)}")
    print(f"  - Cryptocurrencies meeting requirements (≥30 trades): {len(crypto_configs)}")
    print(f"  - Cryptocurrencies filtered out (insufficient trades): {len(skipped_cryptos)}")
    print(f"  - Cryptocurrencies filtered out (low performance < 0.9%): {len(low_performers)}")
    print(f"  - Final qualified cryptocurrencies: {len(filtered_crypto_configs)}")
    
    if filtered_crypto_configs:
        # Get statistics about the selected cryptos
        trade_counts = [int(c['trade_count']) for c in filtered_crypto_configs.values()]
        limits = [int(c['best_limit']) for c in filtered_crypto_configs.values()]
        
        print(f"  - Trade count range: {min(trade_counts)} - {max(trade_counts)}")
        print(f"  - Average trade count: {sum(trade_counts) / len(trade_counts):.1f}")
        print(f"  - Limit range: {min(limits)}% - {max(limits)}%")
        print(f"  - Unique limit values: {len(set(limits))}")
        
        # Show top performers (already sorted by average return per trade)
        print(f"\n🏆 Top 5 performers (by average return per trade):")
        for i, (crypto, config) in enumerate(list(sorted_crypto_configs.items())[:5]):
            avg_return_pct = float(config['avg_return_per_trade']) * 100
            print(f"    {i+1}. {crypto}: {avg_return_pct:.2f}% avg per trade, "
                  f"{config['max_returns']} total returns, {config['trade_count']} trades")
    
    if skipped_cryptos:
        print(f"\n⚠️  Skipped cryptocurrencies (insufficient trades):")
        for crypto, trade_count in skipped_cryptos[:10]:  # Show first 10
            print(f"    - {crypto}: {trade_count} trades")
        if len(skipped_cryptos) > 10:
            print(f"    ... and {len(skipped_cryptos) - 10} more")
    
    if low_performers:
        print(f"\n⚠️  Filtered cryptocurrencies (low performance < 0.9%):")
        for crypto, avg_return in low_performers:
            avg_return_pct = avg_return * 100
            print(f"    - {crypto}: {avg_return_pct:.2f}% avg per trade")

if __name__ == "__main__":
    generate_d0_baseline_config()
