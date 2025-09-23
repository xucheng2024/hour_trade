#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V-shaped Reversal Analysis Runner
V-shaped reversal analysis runner
"""

import os
import sys
import logging
import json
from datetime import datetime
from typing import Dict, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import VReversalDataLoader
from v_pattern_detector import VPatternDetector, print_pattern_summary
from v_strategy_backtester import VReversalBacktester, print_backtest_summary

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_comprehensive_analysis(symbols: List[str] = None, 
                             months: int = 6,
                             save_results: bool = True) -> Dict:
    """
    Run comprehensive V-shaped reversal analysis
    
    Args:
        symbols: List of cryptocurrencies to analyze
        months: Number of months of data to analyze
        save_results: Whether to save results
        
    Returns:
        Analysis results dictionary
    """
    print("🚀 Starting V-shaped Reversal Analysis")
    print("=" * 60)
    
    # 1. Load data
    print("📊 Loading data...")
    data_loader = VReversalDataLoader()
    
    if symbols is None:
        # Select some main cryptocurrencies for analysis
        available_symbols = data_loader.get_available_symbols()
        symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT', '1INCH-USDT', 'AAVE-USDT', 'ACA-USDT']
        symbols = [s for s in symbols if s in available_symbols][:5]  # Maximum 5 cryptocurrencies
    
    data_dict = data_loader.load_multiple_symbols(symbols, months=months)
    
    if not data_dict:
        print("❌ No data loaded")
        return {}
    
    print(f"✅ Loaded data for {len(data_dict)} symbols")
    
    # 2. V-shaped pattern detection
    print("\n🔍 Detecting V-shaped patterns...")
    detector = VPatternDetector(
        min_depth_pct=0.03,     # Minimum decline 3%
        max_depth_pct=0.25,     # Maximum decline 25%
        min_recovery_pct=0.70,  # Minimum recovery 70%
        max_total_time=48,      # Maximum total time 48 hours
        max_recovery_time=24    # Maximum recovery time 24 hours
    )
    
    all_patterns = {}
    total_patterns = 0
    
    for symbol, df in data_dict.items():
        patterns = detector.detect_patterns(df)
        all_patterns[symbol] = patterns
        total_patterns += len(patterns)
        
        print(f"  {symbol}: {len(patterns)} patterns detected")
        if patterns:
            print_pattern_summary(patterns[:3])  # Show first 3 patterns
    
    print(f"\n✅ Total patterns detected: {total_patterns}")
    
    # 3. Strategy backtesting
    print("\n📈 Running strategy backtest...")
    backtester = VReversalBacktester(
        holding_hours=20,         # Fixed holding 20 hours
        min_pattern_quality=0.2,  # Minimum quality score 0.2
        transaction_cost=0.001    # Transaction cost 0.1%
    )
    
    backtest_results = backtester.backtest_multiple_symbols(data_dict, detector)
    
    # 4. Display results
    print_backtest_summary(backtest_results)
    
    # 5. Generate detailed report
    summary = backtester.generate_summary_report(backtest_results)
    
    print(f"\n📋 Strategy Summary:")
    print(f"  Total symbols: {summary['overview']['total_symbols']}")
    print(f"  Total patterns: {summary['overview']['total_patterns']}")
    print(f"  Total trades: {summary['overview']['total_trades']}")
    print(f"  Overall win rate: {summary['overview']['overall_win_rate']:.1%}")
    print(f"  Average return per trade: {summary['overview']['avg_return_per_trade']:.2%}")
    print(f"  Total strategy return: {summary['overview']['total_return']:.2%}")
    print(f"  Sharpe ratio: {summary['overview']['sharpe_ratio']:.2f}")
    print(f"  Average holding time: {summary['overview']['avg_holding_hours']:.1f} hours")
    
    # Exit reason analysis
    print(f"\n🚪 Exit Analysis:")
    for reason, stats in summary['exit_analysis'].items():
        print(f"  {reason}: {stats['count']} trades ({stats['avg_return']:.2%} avg return)")
    
    # 6. Save results
    if save_results:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed results
        results_file = f"v_reversal_analysis_{timestamp}.json"
        
        # Prepare serializable results
        serializable_results = {
            "metadata": {
                "timestamp": timestamp,
                "symbols": symbols,
                "months": months,
                "total_patterns": total_patterns
            },
            "detector_config": {
                "min_depth_pct": detector.min_depth_pct,
                "max_depth_pct": detector.max_depth_pct,
                "min_recovery_pct": detector.min_recovery_pct,
                "max_total_time": detector.max_total_time,
                "max_recovery_time": detector.max_recovery_time
            },
            "backtester_config": {
                "holding_hours": backtester.holding_hours,
                "min_pattern_quality": backtester.min_pattern_quality,
                "transaction_cost": backtester.transaction_cost,
                "strategy_type": "fixed_holding_only"
            },
            "summary": summary,
            "pattern_details": {}
        }
        
        # Add pattern details
        for symbol, patterns in all_patterns.items():
            serializable_results["pattern_details"][symbol] = []
            for pattern in patterns:
                serializable_results["pattern_details"][symbol].append({
                    "start_time": pattern.start_time.isoformat(),
                    "bottom_time": pattern.bottom_time.isoformat(),
                    "recovery_time": pattern.recovery_time_stamp.isoformat(),
                    "depth_pct": pattern.depth_pct,
                    "recovery_hours": pattern.recovery_time,
                    "total_hours": pattern.total_time,
                    "volume_spike": pattern.volume_spike,
                    "start_price": pattern.start_price,
                    "bottom_price": pattern.bottom_price,
                    "recovery_price": pattern.recovery_price
                })
        
        # Save to data directory
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(parent_dir, 'data')
        results_path = os.path.join(data_dir, results_file)
        
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        print(f"💾 Results saved to: {results_path}")
    
    return summary

def quick_test():
    """Quick test V-shaped reversal strategy"""
    print("⚡ Quick V-Reversal Test")
    print("=" * 40)
    
    # Use fewer cryptocurrencies and shorter time for quick test
    result = run_comprehensive_analysis(
        symbols=['BTC-USDT', 'ETH-USDT', '1INCH-USDT'], 
        months=3,
        save_results=True
    )
    
    return result

def full_analysis():
    """Full analysis"""
    print("🔬 Full V-Reversal Analysis")
    print("=" * 40)
    
    # Use more cryptocurrencies and longer time for full analysis
    result = run_comprehensive_analysis(
        symbols=None,  # Use default cryptocurrency list
        months=6,
        save_results=True
    )
    
    return result

def main():
    """Main function"""
    print("🎯 V-shaped Reversal Strategy Analysis")
    print("=" * 50)
    print("1. Quick test (3 symbols, 3 months)")
    print("2. Full analysis (5 symbols, 6 months)")
    print("3. Custom analysis")
    
    try:
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == '1':
            result = quick_test()
        elif choice == '2':
            result = full_analysis()
        elif choice == '3':
            symbols_input = input("Enter symbols (comma-separated, or press Enter for default): ").strip()
            months_input = input("Enter months (default 6): ").strip()
            
            symbols = None
            if symbols_input:
                symbols = [s.strip().upper() for s in symbols_input.split(',')]
            
            months = 6
            if months_input:
                try:
                    months = int(months_input)
                except ValueError:
                    print("Invalid months input, using default 6")
            
            result = run_comprehensive_analysis(symbols=symbols, months=months)
        else:
            print("Invalid choice")
            return
        
        print("\n🎉 Analysis completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
