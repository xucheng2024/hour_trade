#!/usr/bin/env python3
"""
Run hourly strategy optimization for all cryptocurrencies
Based on existing daily strategy parameters, test optimal sell timing
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
import time

def test_hourly_strategy_for_crypto(crypto, params, lookahead_hours=24):
    """
    Test hourly strategy for a single cryptocurrency
    
    Args:
        crypto: Cryptocurrency name
        params: Optimization parameters (including high_open_ratio_threshold and volume_ratio_threshold)
        lookahead_hours: Number of hours to look ahead
    """
    p_threshold = params['high_open_ratio_threshold']
    v_threshold = params['volume_ratio_threshold']
    
    try:
        # Get hourly data
        data_file = f"data/{crypto}_1H.npz"
        if not os.path.exists(data_file):
            return None
        
        # Load data
        data = np.load(data_file)
        raw_data = data['data']
        
        # Convert to DataFrame (hourly data has 9 columns)
        if raw_data.shape[1] == 9:
            # Hourly data format: timestamp, open, high, low, close, volume, volume_ccy, volume_ccy, confirm
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volume_ccy', 'volume_ccy2', 'confirm'])
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]  # Keep only needed columns
        else:
            # Daily data format: timestamp, open, high, low, close, volume
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        
        # Convert numeric columns to float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        # Get last 3 months of data
        end_date = df['timestamp'].max()
        start_date = end_date - timedelta(days=90)
        
        recent_data = df[df['timestamp'] >= start_date].copy()
        
        if len(recent_data) < 100:  # Need at least 100 hours of data
            return None
        
        # Find buy signals
        buy_signals = []
        
        for i in range(len(recent_data) - lookahead_hours):
            current_open = recent_data.iloc[i]['open']
            current_high = recent_data.iloc[i]['high']
            current_volume = recent_data.iloc[i]['volume']
            previous_volume = recent_data.iloc[i-1]['volume'] if i > 0 else current_volume
            
            # Calculate price ratio and volume ratio
            price_ratio = (current_high - current_open) / current_open
            volume_ratio = current_volume / previous_volume if previous_volume > 0 else 1
            
            # Check if buy conditions are met
            if price_ratio >= p_threshold and volume_ratio >= v_threshold:
                buy_signals.append({
                    'buy_hour': i,
                    'buy_price': current_open,
                    'price_ratio': price_ratio,
                    'volume_ratio': volume_ratio,
                    'timestamp': recent_data.iloc[i]['timestamp']
                })
        
        if len(buy_signals) == 0:
            return None
        
        # Test different sell timings
        sell_timing_results = {}
        
        for sell_hours in range(1, 25):  # 1-24 hours
            profits = []
            
            for signal in buy_signals:
                buy_time_idx = signal['buy_hour']
                buy_price = signal['buy_price']
                
                # Calculate sell price (including fees)
                sell_time_idx = buy_time_idx + sell_hours
                if sell_time_idx < len(recent_data):
                    sell_price = recent_data.iloc[sell_time_idx]['close']
                    
                    # Calculate profit (including fees)
                    buy_price_with_fee = buy_price * 1.001  # Buy fee
                    sell_price_with_fee = sell_price * 0.999  # Sell fee
                    profit = (sell_price_with_fee / buy_price_with_fee) - 1
                    profits.append(profit)
            
            if profits:
                compound_return = np.prod([1 + p for p in profits])
                win_rate = sum(1 for p in profits if p > 0) / len(profits)
                mean_return = np.mean(profits)
                median_return = np.median(profits)
                
                sell_timing_results[sell_hours] = {
                    'compound_return': compound_return,
                    'win_rate': win_rate,
                    'mean_return': mean_return,
                    'median_return': median_return,
                    'total_trades': len(profits)
                }
        
        if not sell_timing_results:
            return None
        
        # Find best sell timing
        best_hours = max(sell_timing_results.keys(), 
                        key=lambda h: sell_timing_results[h]['compound_return'])
        best_result = sell_timing_results[best_hours]
        
        # Calculate sell price ratio
        compound_return = best_result['compound_return']
        avg_return = best_result['mean_return']
        sell_price_ratio = 1.0 + avg_return + 0.002  # Compensate for fees
        sell_price_ratio = min(max(sell_price_ratio, 1.01), 1.15)  # Limit to 1%-15%
        
        # Determine risk level
        win_rate = best_result['win_rate']
        if win_rate >= 0.8:
            risk_level = "low"
        elif win_rate >= 0.6:
            risk_level = "medium"
        else:
            risk_level = "high"
        
        return {
            'crypto': crypto,
            'p_threshold': p_threshold,
            'v_threshold': v_threshold,
            'buy_signals': len(buy_signals),
            'best_timing': best_hours,
            'sell_price_ratio': sell_price_ratio,
            'performance': {
                'compound_return': compound_return,
                'win_rate': win_rate,
                'mean_return': best_result['mean_return'],
                'median_return': best_result['median_return'],
                'total_trades': best_result['total_trades']
            },
            'risk_level': risk_level,
            'recommended': win_rate >= 0.5 and compound_return > 1.0
        }
        
    except Exception as e:
        print(f"  ❌ {crypto} test failed: {e}")
        return None

def run_full_hourly_optimization():
    """Run hourly strategy optimization for all cryptocurrencies"""
    
    print("🚀 Starting hourly strategy optimization for all cryptocurrencies")
    print("=" * 80)
    
    # Load daily strategy optimization parameters
    try:
        with open('crypto_trading_triggers.json', 'r') as f:
            config = json.load(f)
            triggers = config.get('triggers', {})
        print(f"✅ Loaded daily strategy parameters for {len(triggers)} cryptocurrencies")
    except Exception as e:
        print(f"❌ Failed to load configuration: {e}")
        return
    
    results = {}
    success_count = 0
    total_count = len(triggers)
    
    print(f"📊 Starting to process {total_count} cryptocurrencies...")
    print("-" * 80)
    
    start_time = time.time()
    
    for i, (crypto, params) in enumerate(triggers.items(), 1):
        print(f"[{i:3d}/{total_count}] Processing {crypto}...", end=" ")
        
        result = test_hourly_strategy_for_crypto(crypto, params)
        
        if result:
            results[crypto] = result
            success_count += 1
            print(f"✅ Success - Best {result['best_timing']} hours, return {result['performance']['compound_return']:.3f}×, win rate {result['performance']['win_rate']:.1%}")
        else:
            print("❌ Failed")
        
        # Show progress every 10
        if i % 10 == 0:
            elapsed = time.time() - start_time
            avg_time = elapsed / i
            remaining = (total_count - i) * avg_time
            print(f"    Progress: {i}/{total_count} ({i/total_count:.1%}), estimated remaining: {remaining/60:.1f} minutes")
    
    print("\n" + "=" * 80)
    print("📊 Hourly strategy optimization completed!")
    print(f"Successfully processed: {success_count}/{total_count} ({success_count/total_count:.1%})")
    
    if success_count == 0:
        print("❌ No cryptocurrencies were successfully processed")
        return
    
    # Generate configuration
    hourly_config = {
        "strategy_type": "hourly_sell_timing",
        "description": "Hourly data sell timing configuration based on optimized parameters - full optimization",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "data_period": "Last 3 months hourly data",
        "fees": {
            "buy_fee": 0.001,
            "sell_fee": 0.001
        },
        "crypto_configs": {}
    }
    
    # Convert result format
    for crypto, result in results.items():
        hourly_config["crypto_configs"][crypto] = {
            "buy_conditions": {
                "high_open_ratio_threshold": result['p_threshold'],
                "volume_ratio_threshold": result['v_threshold']
            },
            "sell_timing": {
                "best_hours": result['best_timing'],
                "sell_price_ratio": result['sell_price_ratio'],
                "description": f"Sell {result['best_timing']} hours after buying, sell price is {result['sell_price_ratio']:.1%} of target open price"
            },
            "performance": result['performance'],
            "risk_level": result['risk_level'],
            "recommended": bool(result['recommended'])
        }
    
    # Add statistics
    all_compound_returns = [r['performance']['compound_return'] for r in results.values()]
    all_win_rates = [r['performance']['win_rate'] for r in results.values()]
    all_best_hours = [r['best_timing'] for r in results.values()]
    
    hourly_config["statistics"] = {
        "total_cryptos": success_count,
        "success_rate": f"{success_count/total_count:.1%}",
        "compound_returns": {
            "min": float(np.min(all_compound_returns)),
            "max": float(np.max(all_compound_returns)),
            "mean": float(np.mean(all_compound_returns)),
            "median": float(np.median(all_compound_returns))
        },
        "win_rates": {
            "min": float(np.min(all_win_rates)),
            "max": float(np.max(all_win_rates)),
            "mean": float(np.mean(all_win_rates)),
            "median": float(np.median(all_win_rates))
        },
        "best_hours_distribution": {
            "min": int(np.min(all_best_hours)),
            "max": int(np.max(all_best_hours)),
            "mean": float(np.mean(all_best_hours)),
            "median": float(np.median(all_best_hours))
        }
    }
    
    # Save configuration
    try:
        with open('crypto_hourly_sell_config_full.json', 'w', encoding='utf-8') as f:
            json.dump(hourly_config, f, indent=2, ensure_ascii=False)
        print(f"✅ Complete configuration saved to: crypto_hourly_sell_config_full.json")
    except Exception as e:
        print(f"❌ Failed to save configuration: {e}")
    
    # Display statistics summary
    print(f"\n📈 Statistics Summary:")
    print(f"  Compound return range: {np.min(all_compound_returns):.3f}× - {np.max(all_compound_returns):.3f}×")
    print(f"  Average compound return: {np.mean(all_compound_returns):.3f}×")
    print(f"  Win rate range: {np.min(all_win_rates):.1%} - {np.max(all_win_rates):.1%}")
    print(f"  Average win rate: {np.mean(all_win_rates):.1%}")
    print(f"  Best sell timing range: {np.min(all_best_hours)} - {np.max(all_best_hours)} hours")
    print(f"  Average best sell timing: {np.mean(all_best_hours):.1f} hours")
    
    # Display top 10
    sorted_results = sorted(results.items(), 
                          key=lambda x: x[1]['performance']['compound_return'], 
                          reverse=True)[:10]
    
    print(f"\n🏆 Top 10 Best Performance:")
    for i, (crypto, result) in enumerate(sorted_results, 1):
        perf = result['performance']
        print(f"  {i:2d}. {crypto:12s}: {perf['compound_return']:.3f}×, {perf['win_rate']:.1%}, {result['best_timing']:2d} hours")

if __name__ == "__main__":
    run_full_hourly_optimization()
