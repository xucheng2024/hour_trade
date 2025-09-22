#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run Profit Maximization for V-Pattern Strategy
运行V型反转策略利润最大化
"""

import os
import sys
import logging
import time
from datetime import datetime
from typing import Dict, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import VReversalDataLoader
from profit_maximizer import VectorizedProfitMaximizer, print_profit_maximization_results, MaxProfitParams

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_profit_maximization(symbols: List[str] = None, 
                           total_months: int = 9,
                           test_months: int = 3) -> Dict[str, MaxProfitParams]:
    """
    运行利润最大化优化
    
    Args:
        symbols: 要优化的币种列表
        total_months: 总数据月数
        test_months: 测试期月数
        
    Returns:
        优化结果字典
    """
    print("💰 V-Pattern Strategy Profit Maximization")
    print("=" * 60)
    print(f"🎯 目标: 通过优化所有参数实现利润最大化")
    print(f"📊 Configuration:")
    print(f"  Total data period: {total_months} months")
    print(f"  Training period: {total_months - test_months} months")
    print(f"  Test period: {test_months} months")
    print(f"  优化参数: V型检测 + 止盈止损 + 持有时间")
    print()
    
    # 1. 加载数据
    print("📊 Loading data...")
    start_time = time.time()
    
    data_loader = VReversalDataLoader()
    
    if symbols is None:
        # 选择主要币种
        available_symbols = data_loader.get_available_symbols()
        symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT']
        symbols = [s for s in symbols if s in available_symbols][:2]  # 限制为2个币种以提高速度
    
    data_dict = data_loader.load_multiple_symbols(symbols, months=total_months)
    
    if not data_dict:
        print("❌ No data loaded")
        return {}
    
    load_time = time.time() - start_time
    print(f"✅ Loaded data for {len(data_dict)} symbols in {load_time:.1f}s")
    
    # 显示数据信息
    for symbol, df in data_dict.items():
        print(f"  {symbol}: {len(df)} records, "
              f"{df['timestamp'].min().strftime('%Y-%m-%d')} to "
              f"{df['timestamp'].max().strftime('%Y-%m-%d')}")
    print()
    
    # 2. 创建利润最大化器
    print("🔧 Initializing profit maximizer...")
    maximizer = VectorizedProfitMaximizer(test_months=test_months)
    
    print(f"📋 优化参数范围:")
    print(f"  V型深度: 2%-25%")
    print(f"  恢复要求: 60%-80%")
    print(f"  时间限制: 24-48小时")
    print(f"  止损: 3%-10%")
    print(f"  止盈: 8%-25%")
    print(f"  持有时间: 6-72小时 (重点优化)")
    print()
    
    # 3. 运行优化
    print("⚡ Starting profit maximization...")
    print("   This will test thousands of parameter combinations...")
    print("   Focus: Maximum profit with acceptable risk")
    print()
    
    optimization_start = time.time()
    results = maximizer.optimize_multiple_symbols(data_dict)
    optimization_time = time.time() - optimization_start
    
    if not results:
        print("❌ No successful optimizations")
        return {}
    
    print(f"✅ Optimization completed in {optimization_time:.1f}s")
    print(f"⚡ Speed: {optimization_time/len(data_dict):.1f}s per symbol")
    print()
    
    # 4. 显示结果
    print_profit_maximization_results(results)
    
    # 5. 详细参数显示
    print(f"\n📋 Optimized Parameters for Maximum Profit:")
    print("=" * 80)
    
    for symbol, result in results.items():
        print(f"\n💰 {symbol} - Max Profit Configuration:")
        print(f"  🎯 V-Pattern Detection:")
        print(f"    Depth range: {result.min_depth_pct:.1%} - {result.max_depth_pct:.1%}")
        print(f"    Recovery requirement: {result.min_recovery_pct:.1%}")
        print(f"    Time limits: Total ≤ {result.max_total_time}h, Recovery ≤ {result.max_recovery_time}h")
        
        print(f"  📈 Trading Strategy:")
        print(f"    Stop Loss: {result.stop_loss_pct:.1%}")
        print(f"    Take Profit: {result.take_profit_pct:.1%}")
        print(f"    Holding Time: {result.holding_hours} hours")
        
        print(f"  📊 Performance:")
        print(f"    Test Return: {result.test_return:.2%}")
        print(f"    Win Rate: {result.test_win_rate:.1%}")
        print(f"    Trades: {result.test_trades}")
        print(f"    Sharpe Ratio: {result.sharpe_ratio:.2f}")
        print(f"    Profit Factor: {result.profit_factor:.2f}")
        print(f"    Max Drawdown: {result.max_drawdown:.2%}")
    
    # 6. 性能分析
    print(f"\n🚀 Performance Analysis:")
    print(f"  Total time: {load_time + optimization_time:.1f}s")
    print(f"  Data loading: {load_time:.1f}s")
    print(f"  Optimization: {optimization_time:.1f}s")
    print(f"  Average per symbol: {optimization_time/len(data_dict):.1f}s")
    
    # 7. 对比分析
    print(f"\n📈 Profit Enhancement Analysis:")
    baseline_return = 0.05  # 假设基线5%收益
    
    for symbol, result in results.items():
        enhancement = (result.test_return - baseline_return) / baseline_return * 100
        print(f"  {symbol}: {result.test_return:.2%} vs {baseline_return:.1%} baseline "
              f"({enhancement:+.0f}% enhancement)")
    
    # 8. 保存结果
    print(f"\n💾 Saving profit maximization results...")
    saved_file = maximizer.save_results(results)
    print(f"✅ Results saved to: {saved_file}")
    
    return results

def quick_profit_test():
    """快速利润最大化测试"""
    print("⚡ Quick Profit Maximization Test")
    print("=" * 50)
    
    result = run_profit_maximization(
        symbols=['BTC-USDT', 'ETH-USDT'],
        total_months=6,
        test_months=3
    )
    
    return result

def compare_strategies(results: Dict[str, MaxProfitParams]):
    """对比不同策略配置"""
    if not results:
        return
    
    print(f"\n🔍 Strategy Configuration Analysis")
    print("=" * 80)
    
    # 分析最佳配置模式
    sl_values = [r.stop_loss_pct for r in results.values()]
    tp_values = [r.take_profit_pct for r in results.values()]
    holding_values = [r.holding_hours for r in results.values()]
    
    print(f"📊 Optimal Parameter Patterns:")
    print(f"  Average Stop Loss: {np.mean(sl_values):.1%}")
    print(f"  Average Take Profit: {np.mean(tp_values):.1%}")
    print(f"  Average Holding Time: {np.mean(holding_values):.1f} hours")
    
    # 风险收益分析
    print(f"\n⚖️ Risk-Return Analysis:")
    for symbol, result in results.items():
        risk_adj_return = result.test_return / abs(result.max_drawdown) if result.max_drawdown != 0 else float('inf')
        print(f"  {symbol}: Risk-Adjusted Return = {risk_adj_return:.2f}")

def main():
    """主函数"""
    print("💰 V-Pattern Profit Maximization System")
    print("=" * 60)
    print("🎯 Find the BEST parameters for maximum profit!")
    print("1. Quick test (2 symbols, 6 months data)")
    print("2. Standard optimization (2 symbols, 9 months data)")
    print("3. Custom optimization")
    
    try:
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == '1':
            result = quick_profit_test()
        elif choice == '2':
            result = run_profit_maximization(
                symbols=['BTC-USDT', 'ETH-USDT'],
                total_months=9,
                test_months=3
            )
        elif choice == '3':
            symbols_input = input("Enter symbols (comma-separated, or press Enter for default): ").strip()
            total_months_input = input("Enter total months (default 9): ").strip()
            test_months_input = input("Enter test months (default 3): ").strip()
            
            symbols = None
            if symbols_input:
                symbols = [s.strip().upper() for s in symbols_input.split(',')]
            
            total_months = 9
            if total_months_input:
                try:
                    total_months = int(total_months_input)
                except ValueError:
                    print("Invalid total months input, using default 9")
            
            test_months = 3
            if test_months_input:
                try:
                    test_months = int(test_months_input)
                except ValueError:
                    print("Invalid test months input, using default 3")
            
            if test_months >= total_months:
                print("Error: Test months must be less than total months")
                return
            
            result = run_profit_maximization(
                symbols=symbols, 
                total_months=total_months,
                test_months=test_months
            )
        else:
            print("Invalid choice")
            return
        
        # 策略对比分析
        if result:
            compare_strategies(result)
        
        print("\n🎉 Profit maximization completed successfully!")
        print("💡 Use the optimized parameters for maximum profit potential!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Optimization interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import numpy as np
    # 直接运行快速测试
    print("💰 Running Quick Profit Maximization Test...")
    quick_profit_test()
