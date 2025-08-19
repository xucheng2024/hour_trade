#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy Earnings Calculator Runner
Simple interface to calculate potential earnings from trading strategies
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from analysis.strategy_earnings_calculator import StrategyEarningsCalculator

def main():
    """Main function with simple interface"""
    print("🚀 Strategy Earnings Calculator")
    print("=" * 50)
    print("Calculate potential earnings from daily/hourly strategies over time periods")
    print("This tool considers scenarios where there might be no trading opportunities")
    print()
    
    # Get user input
    try:
        strategy = input("Choose strategy (daily/hourly) [daily]: ").strip().lower() or "daily"
        if strategy not in ['daily', 'hourly']:
            print("❌ Invalid strategy. Using daily.")
            strategy = "daily"
        
        period = input("Choose time period (1y/6m/3m/1m) [1y]: ").strip().lower() or "1y"
        if period not in ['1y', '6m', '3m', '1m']:
            print("❌ Invalid period. Using 1y.")
            period = "1y"
        
        capital_input = input("Enter initial capital in USDT [100]: ").strip() or "100"
        try:
            capital = float(capital_input)
        except ValueError:
            print("❌ Invalid capital. Using 100 USDT.")
            capital = 100.0
        
        fee_input = input("Enter trading fee (0.1% = 0.001) [0.001]: ").strip() or "0.001"
        try:
            fee = float(fee_input)
        except ValueError:
            print("❌ Invalid fee. Using 0.1% (0.001).")
            fee = 0.001
        
        print(f"\n📊 Analysis Parameters:")
        print(f"  Strategy: {strategy}")
        print(f"  Time Period: {period}")
        print(f"  Initial Capital: {int(capital)} USDT")
        print(f"  Trading Fee: {fee*100:.1f}%")
        print()
        
        # Confirm analysis
        confirm = input("Start analysis? (y/n) [y]: ").strip().lower() or "y"
        if confirm not in ['y', 'yes']:
            print("❌ Analysis cancelled.")
            return
        
        print("\n" + "=" * 50)
        
        # Initialize calculator
        calculator = StrategyEarningsCalculator(
            initial_capital=capital,
            trading_fee=fee
        )
        
        # Calculate earnings
        results = calculator.calculate_strategy_earnings(
            strategy_type=strategy,
            time_period=period
        )
        
        # Save results
        if results:
            calculator.save_results(results)
        
        print("\n" + "=" * 50)
        print("✅ Strategy Earnings Analysis Completed!")
        
        # Show key insights
        if results and 'summary' in results:
            summary = results['summary']
            print(f"\n💡 Key Insights:")
            print(f"  • You could have earned {int(summary['total_earnings'])} USDT")
            print(f"  • Final capital would be {int(summary['final_capital'])} USDT")
            print(f"  • Total return: {summary['total_return_percentage']:.2f}%")
            print(f"  • Annualized return: {summary['annualized_return']:.2f}%")
            print(f"  • {summary['successful_trades']} cryptocurrencies had trading opportunities")
            print(f"  • {summary['no_trade_opportunities']} cryptocurrencies had no opportunities")
            
            if summary['best_performers']:
                best = summary['best_performers'][0]
                print(f"  • Best performer: {best['crypto']} with {int(best['earnings'])} USDT earnings")
        
    except KeyboardInterrupt:
        print("\n\n❌ Analysis interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")

if __name__ == "__main__":
    main()
