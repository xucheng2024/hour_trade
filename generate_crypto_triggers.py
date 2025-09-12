#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate Crypto Trading Triggers Configuration
Extract optimal parameters from optimization results and create JSON config
"""

import json
import os
from datetime import datetime
from typing import Dict, Any

def generate_crypto_triggers():
    """Generate JSON configuration for crypto trading triggers"""
    
    # Load optimization results
    results_file = "data/vectorized_optimization_20250912_203704.json"
    if not os.path.exists(results_file):
        print(f"❌ Results file not found: {results_file}")
        return
    
    print("📊 Loading optimization results...")
    with open(results_file, 'r', encoding='utf-8') as f:
        results = json.load(f)
    
    # Extract optimal parameters
    optimal_params = results.get('optimal_parameters', {})
    
    if not optimal_params:
        print("❌ No optimal parameters found in results")
        return
    
    print(f"✅ Found {len(optimal_params)} optimized cryptocurrencies")
    
    # Generate trigger configuration
    triggers_config = {
        "metadata": {
            "description": "Crypto Trading Triggers - Optimal Parameters for Maximum Compound Return",
            "strategy": "Buy when (High-Open)/Open >= p AND Volume/PreviousVolume >= v, Sell at Close",
            "requirements": "Median return >= 1.01 (1% minimum)",
            "generated_date": datetime.now().isoformat(),
            "total_cryptos": len(optimal_params),
            "success_rate": f"{len(optimal_params)}/192 ({len(optimal_params)/192*100:.1f}%)"
        },
        "triggers": {}
    }
    
    # Process each cryptocurrency
    for crypto, params in optimal_params.items():
        p = params['p']
        v = params['v']
        compound_return = params['compound_return']
        median_return = params['median_return']
        total_trades = params['total_trades']
        win_rate = params['win_rate']
        
        # Create trigger configuration for this crypto
        trigger = {
            "high_open_ratio_threshold": p,  # (High - Open) / Open >= p
            "volume_ratio_threshold": v,     # Volume / PreviousVolume >= v
            "expected_performance": {
                "compound_return": compound_return,
                "median_return": median_return,
                "total_trades": total_trades,
                "win_rate": win_rate
            },
            "risk_level": get_risk_level(p),
            "strategy_type": get_strategy_type(p)
        }
        
        triggers_config["triggers"][crypto] = trigger
    
    # Add summary statistics
    triggers_config["summary"] = generate_summary_stats(optimal_params)
    
    # Save configuration
    output_file = "crypto_trading_triggers.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(triggers_config, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Generated triggers configuration: {output_file}")
    
    # Print sample triggers
    print("\n📋 Sample Triggers:")
    sample_cryptos = list(optimal_params.keys())[:10]
    for crypto in sample_cryptos:
        params = optimal_params[crypto]
        print(f"  {crypto}: p={params['p']:.1%}, v={params['v']:.1f}x, "
              f"compound={params['compound_return']:.0f}, median={params['median_return']:.3f}")
    
    return output_file

def get_risk_level(p: float) -> str:
    """Determine risk level based on p parameter"""
    if p <= 0.03:
        return "conservative"
    elif p <= 0.05:
        return "moderate"
    elif p <= 0.07:
        return "aggressive"
    else:
        return "high_risk"

def get_strategy_type(p: float) -> str:
    """Determine strategy type based on p parameter"""
    if p <= 0.03:
        return "stable_coin"
    elif p <= 0.05:
        return "standard"
    elif p <= 0.07:
        return "high_volatility"
    else:
        return "extreme_volatility"

def generate_summary_stats(optimal_params: Dict[str, Any]) -> Dict[str, Any]:
    """Generate summary statistics"""
    
    # Extract all parameters
    p_values = [params['p'] for params in optimal_params.values()]
    v_values = [params['v'] for params in optimal_params.values()]
    compound_returns = [params['compound_return'] for params in optimal_params.values()]
    median_returns = [params['median_return'] for params in optimal_params.values()]
    total_trades = [params['total_trades'] for params in optimal_params.values()]
    win_rates = [params['win_rate'] for params in optimal_params.values()]
    
    # Count by risk level
    risk_levels = [get_risk_level(p) for p in p_values]
    risk_counts = {}
    for risk in risk_levels:
        risk_counts[risk] = risk_counts.get(risk, 0) + 1
    
    # Count by strategy type
    strategy_types = [get_strategy_type(p) for p in p_values]
    strategy_counts = {}
    for strategy in strategy_types:
        strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
    
    return {
        "parameter_statistics": {
            "p_values": {
                "min": min(p_values),
                "max": max(p_values),
                "mean": sum(p_values) / len(p_values),
                "median": sorted(p_values)[len(p_values)//2]
            },
            "v_values": {
                "min": min(v_values),
                "max": max(v_values),
                "mean": sum(v_values) / len(v_values),
                "median": sorted(v_values)[len(v_values)//2]
            }
        },
        "performance_statistics": {
            "compound_returns": {
                "min": min(compound_returns),
                "max": max(compound_returns),
                "mean": sum(compound_returns) / len(compound_returns),
                "median": sorted(compound_returns)[len(compound_returns)//2]
            },
            "median_returns": {
                "min": min(median_returns),
                "max": max(median_returns),
                "mean": sum(median_returns) / len(median_returns),
                "median": sorted(median_returns)[len(median_returns)//2]
            },
            "total_trades": {
                "min": min(total_trades),
                "max": max(total_trades),
                "mean": sum(total_trades) / len(total_trades),
                "median": sorted(total_trades)[len(total_trades)//2]
            },
            "win_rates": {
                "min": min(win_rates),
                "max": max(win_rates),
                "mean": sum(win_rates) / len(win_rates),
                "median": sorted(win_rates)[len(win_rates)//2]
            }
        },
        "risk_distribution": risk_counts,
        "strategy_distribution": strategy_counts
    }

def generate_usage_example():
    """Generate usage example for the triggers configuration"""
    
    example = {
        "usage_example": {
            "description": "How to use this configuration for trading",
            "python_example": """
# Example usage in Python
import json

# Load triggers configuration
with open('crypto_trading_triggers.json', 'r') as f:
    config = json.load(f)

def check_buy_signal(crypto, high, open_price, current_volume, previous_volume):
    '''Check if buy signal is triggered for a cryptocurrency'''
    
    if crypto not in config['triggers']:
        return False, "Crypto not in configuration"
    
    trigger = config['triggers'][crypto]
    
    # Calculate ratios
    high_open_ratio = (high - open_price) / open_price
    volume_ratio = current_volume / previous_volume if previous_volume > 0 else 0
    
    # Check thresholds
    p_threshold = trigger['high_open_ratio_threshold']
    v_threshold = trigger['volume_ratio_threshold']
    
    if high_open_ratio >= p_threshold and volume_ratio >= v_threshold:
        return True, {
            'crypto': crypto,
            'high_open_ratio': high_open_ratio,
            'volume_ratio': volume_ratio,
            'expected_median_return': trigger['expected_performance']['median_return'],
            'risk_level': trigger['risk_level'],
            'strategy_type': trigger['strategy_type']
        }
    
    return False, f"Thresholds not met: p={high_open_ratio:.3f} >= {p_threshold:.3f}, v={volume_ratio:.2f} >= {v_threshold:.2f}"

# Example usage
crypto = 'BTC-USDT'
high = 50000
open_price = 48000
current_volume = 1000000
previous_volume = 800000

signal, info = check_buy_signal(crypto, high, open_price, current_volume, previous_volume)
if signal:
    print(f"Buy signal for {crypto}: {info}")
else:
    print(f"No buy signal: {info}")
            """,
            "trading_logic": {
                "buy_condition": "(High - Open) / Open >= p_threshold AND Volume / PreviousVolume >= v_threshold",
                "sell_condition": "Close price (same day)",
                "fees": "0.1% buy fee + 0.1% sell fee (included in calculations)",
                "minimum_median_return": "1.01 (1% minimum expected return)"
            }
        }
    }
    
    return example

def main():
    """Main function"""
    print("🚀 Generating Crypto Trading Triggers Configuration")
    print("=" * 60)
    
    # Generate triggers configuration
    output_file = generate_crypto_triggers()
    
    if not output_file:
        return
    
    # Load the generated config to add usage example
    with open(output_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Add usage example
    config["usage_example"] = generate_usage_example()["usage_example"]
    
    # Save updated configuration
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print(f"\n📄 Configuration saved to: {output_file}")
    print("\n📊 Configuration Summary:")
    
    # Print summary
    summary = config["summary"]
    print(f"  Total cryptos: {config['metadata']['total_cryptos']}")
    print(f"  P parameter range: {summary['parameter_statistics']['p_values']['min']:.1%} - {summary['parameter_statistics']['p_values']['max']:.1%}")
    print(f"  V parameter range: {summary['parameter_statistics']['v_values']['min']:.1f} - {summary['parameter_statistics']['v_values']['max']:.1f}")
    print(f"  Median return range: {summary['performance_statistics']['median_returns']['min']:.3f} - {summary['performance_statistics']['median_returns']['max']:.3f}")
    
    print(f"\n📊 Risk Distribution:")
    for risk, count in summary['risk_distribution'].items():
        print(f"  {risk}: {count} cryptos")
    
    print(f"\n📊 Strategy Distribution:")
    for strategy, count in summary['strategy_distribution'].items():
        print(f"  {strategy}: {count} cryptos")
    
    print("\n✅ Crypto trading triggers configuration generated successfully!")
    print(f"📖 See {output_file} for complete configuration and usage examples")

if __name__ == "__main__":
    main()
