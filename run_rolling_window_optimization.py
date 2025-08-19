#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rolling Window Optimization Runner
Test the new rolling window strategy optimizer
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from strategies.rolling_window_optimizer import RollingWindowOptimizer
from data.data_manager import load_crypto_list

def main():
    """Main function to test rolling window optimization"""
    print("🔄 Rolling Window Strategy Optimization")
    print("=" * 50)
    print("Forward-looking trading: Use past data to optimize future parameters")
    print()
    print("📋 How it works:")
    print("  1. First 3 months: Data collection and parameter optimization")
    print("  2. 4th month onwards: Start trading with optimized parameters")
    print("  3. Each month: Re-optimize using past 3 months data")
    print("  4. Result: Parameters that adapt to changing market conditions")
    print()
    
    # Get user input
    try:
        strategy = input("Choose strategy (daily/hourly) [daily]: ").strip().lower() or "daily"
        if strategy not in ['daily', 'hourly']:
            print("❌ Invalid strategy. Using daily.")
            strategy = "daily"
        
        window_size = input("Choose optimization window size (1m/3m/6m/1y) [3m]: ").strip().lower() or "3m"
        if window_size not in ['1m', '3m', '6m', '1y']:
            print("❌ Invalid window size. Using 3m.")
            window_size = "3m"
        
        step_size = input("Choose re-optimization frequency (1m/3m/6m/1y) [1m]: ").strip().lower() or "1m"
        if step_size not in ['1m', '3m', '6m', '1y']:
            print("❌ Invalid step size. Using 1m.")
            step_size = "1m"
        
        crypto_limit = input("Number of cryptocurrencies to test (max 29) [5]: ").strip() or "5"
        try:
            crypto_limit = min(int(crypto_limit), 29)
        except ValueError:
            print("❌ Invalid number. Using 5.")
            crypto_limit = 5
        
        print(f"\n📊 Analysis Parameters:")
        print(f"  Strategy: {strategy}")
        print(f"  Optimization Window: {window_size} (past data used for parameter optimization)")
        print(f"  Re-optimization Frequency: {step_size} (how often to update parameters)")
        print(f"  Cryptocurrencies: {crypto_limit}")
        print()
        print(f"📈 Trading Timeline:")
        print(f"  Month 1-{window_size}: Collect data and optimize parameters")
        print(f"  Month {window_size}+1: Start trading with optimized parameters")
        print(f"  Every {step_size}: Re-optimize using past {window_size} data")
        print()
        
        # Confirm analysis
        confirm = input("Start forward-looking rolling window optimization? (y/n) [y]: ").strip().lower() or "y"
        if confirm not in ['y', 'yes']:
            print("❌ Analysis cancelled.")
            return
        
        print("\n" + "=" * 50)
        
        # Initialize rolling window optimizer
        optimizer = RollingWindowOptimizer(buy_fee=0.001, sell_fee=0.001)
        
        # Load cryptocurrency list
        cryptos = load_crypto_list()[:crypto_limit]
        print(f"🔍 Testing with {len(cryptos)} cryptocurrencies: {', '.join(cryptos)}")
        print()
        
        # Results storage
        results = {
            'strategy_type': strategy,
            'window_size': window_size,
            'step_size': step_size,
            'cryptocurrencies': {},
            'summary': {
                'total_analyzed': 0,
                'successful_analysis': 0,
                'failed_analysis': 0,
                'high_stability': 0,
                'medium_stability': 0,
                'low_stability': 0
            }
        }
        
        # Analyze each cryptocurrency
        for i, crypto in enumerate(cryptos, 1):
            print(f"\n📈 Analyzing {i}/{len(cryptos)}: {crypto}")
            
            try:
                # Run rolling window optimization
                date_dict = {}
                result = optimizer.optimize_with_rolling_windows(
                    instId=crypto,
                    start=0,  # Use all available data
                    end=0,
                    date_dict=date_dict,
                    bar="1d" if strategy == "daily" else "1h",
                    strategy_type="1d" if strategy == "daily" else "1h",
                    window_size=window_size,
                    step_size=step_size
                )
                
                if result and crypto in result:
                    crypto_result = result[crypto]
                    results['cryptocurrencies'][crypto] = crypto_result
                    results['summary']['total_analyzed'] += 1
                    results['summary']['successful_analysis'] += 1
                    
                    # Count stability levels
                    stability = crypto_result.get('recommendation', 'UNKNOWN')
                    if 'HIGH' in stability:
                        results['summary']['high_stability'] += 1
                    elif 'MEDIUM' in stability:
                        results['summary']['medium_stability'] += 1
                    elif 'LOW' in stability:
                        results['summary']['low_stability'] += 1
                    
                    # Display results
                    print(f"  ✅ Success: {crypto_result['total_trading_points']} trading points analyzed")
                    print(f"  📅 Trading period: {crypto_result['trading_start_date']} to {crypto_result['trading_end_date']}")
                    print(f"  📊 Recommended: Limit={crypto_result['recommended_limit']}%, Duration={crypto_result['recommended_duration']}")
                    print(f"  📈 Expected Returns: {crypto_result['expected_returns']:.3f}")
                    print(f"  🔒 Stability: {crypto_result['overall_stability']:.3f} ({crypto_result['recommendation_text']})")
                    
                    # Show parameter statistics
                    limit_stats = crypto_result['limit_stats']
                    duration_stats = crypto_result['duration_stats']
                    print(f"  📋 Limit: Avg={limit_stats['average']}±{limit_stats['std_dev']:.2f}, Most Common={limit_stats['most_common']}")
                    print(f"  📋 Duration: Avg={duration_stats['average']}±{duration_stats['std_dev']:.2f}, Most Common={duration_stats['most_common']}")
                    
                    # Show trading strategy info
                    print(f"  💡 Strategy: {crypto_result['trading_strategy']}")
                    print(f"  📊 Data Usage: {crypto_result['data_usage']}")
                    
                else:
                    results['summary']['total_analyzed'] += 1
                    results['summary']['failed_analysis'] += 1
                    print(f"  ❌ Analysis failed")
                    
            except Exception as e:
                results['summary']['total_analyzed'] += 1
                results['summary']['failed_analysis'] += 1
                print(f"  ❌ Error: {e}")
        
        # Display summary
        print("\n" + "=" * 50)
        print("📊 Forward-Looking Rolling Window Optimization Summary")
        print("=" * 50)
        print(f"Strategy: {strategy.upper()}")
        print(f"Optimization Window: {window_size}")
        print(f"Re-optimization Frequency: {step_size}")
        print(f"Total Analyzed: {results['summary']['total_analyzed']}")
        print(f"Successful: {results['summary']['successful_analysis']}")
        print(f"Failed: {results['summary']['failed_analysis']}")
        print()
        print("Parameter Stability Distribution:")
        print(f"  High Stability: {results['summary']['high_stability']} (reliable for trading)")
        print(f"  Medium Stability: {results['summary']['medium_stability']} (moderate risk)")
        print(f"  Low Stability: {results['summary']['low_stability']} (high risk, frequent updates needed)")
        print()
        print("💡 Key Benefits:")
        print(f"  • Parameters adapt to changing market conditions")
        print(f"  • Avoid overfitting to historical data")
        print(f"  • Forward-looking approach for better performance")
        print(f"  • Regular re-optimization maintains relevance")
        
        # Save results
        try:
            import json
            from datetime import datetime
            
            data_dir = 'data'
            os.makedirs(data_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"forward_looking_optimization_{strategy}_{window_size}_{step_size}_{timestamp}.json"
            filepath = os.path.join(data_dir, filename)
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            
            print(f"\n💾 Results saved to: {filepath}")
            
        except Exception as e:
            print(f"\n❌ Error saving results: {e}")
        
        print("\n✅ Forward-Looking Rolling Window Optimization Completed!")
        print("🚀 Ready to implement adaptive trading strategy!")
        
    except KeyboardInterrupt:
        print("\n\n❌ Analysis interrupted by user.")

if __name__ == "__main__":
    main()
