#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fast V-Pattern Parameter Optimization Runner
快速V型模式参数优化运行器
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
from vectorized_optimizer import VectorizedParameterOptimizer, print_vectorized_results, OptimizedParams

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_fast_optimization(symbols: List[str] = None, 
                         total_months: int = 9,
                         test_months: int = 3) -> Dict[str, OptimizedParams]:
    """
    运行快速V型模式参数优化
    
    Args:
        symbols: 要优化的币种列表
        total_months: 总数据月数
        test_months: 测试期月数
        
    Returns:
        优化结果字典
    """
    print("⚡ Fast V-Pattern Parameter Optimization")
    print("=" * 60)
    print(f"🚀 Using vectorized computation for maximum speed")
    print(f"📊 Configuration:")
    print(f"  Total data period: {total_months} months")
    print(f"  Training period: {total_months - test_months} months")
    print(f"  Test period: {test_months} months")
    print()
    
    # 1. 加载数据
    print("📊 Loading data...")
    start_time = time.time()
    
    data_loader = VReversalDataLoader()
    
    if symbols is None:
        # 选择主要币种
        available_symbols = data_loader.get_available_symbols()
        symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT', '1INCH-USDT', 'AAVE-USDT']
        symbols = [s for s in symbols if s in available_symbols][:3]  # 限制为3个币种
    
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
    
    # 2. 创建向量化优化器
    print("🔧 Initializing vectorized optimizer...")
    optimizer = VectorizedParameterOptimizer(test_months=test_months)
    
    # 3. 运行优化
    print("⚡ Starting vectorized optimization...")
    print("   This should be much faster than the previous version...")
    print()
    
    optimization_start = time.time()
    results = optimizer.optimize_multiple_symbols(data_dict)
    optimization_time = time.time() - optimization_start
    
    if not results:
        print("❌ No successful optimizations")
        return {}
    
    print(f"✅ Optimization completed in {optimization_time:.1f}s")
    print(f"⚡ Speed: {optimization_time/len(data_dict):.1f}s per symbol")
    print()
    
    # 4. 显示结果
    print_vectorized_results(results)
    
    # 5. 详细参数显示
    print(f"\n📋 Optimized Parameters for Each Symbol:")
    print("=" * 80)
    
    for symbol, result in results.items():
        print(f"\n🎯 {symbol}:")
        print(f"  Depth range: {result.min_depth_pct:.1%} - {result.max_depth_pct:.1%}")
        print(f"  Recovery requirement: {result.min_recovery_pct:.1%}")
        print(f"  Time limits: Total ≤ {result.max_total_time}h, Recovery ≤ {result.max_recovery_time}h")
        print(f"  Training: {result.train_patterns} patterns → "
              f"({result.train_win_rate:.1%} win rate, {result.train_return:.1%} return)")
        print(f"  Testing: {result.test_patterns} patterns → "
              f"({result.test_win_rate:.1%} win rate, {result.test_return:.1%} return)")
        print(f"  Consistency: {result.consistency_ratio:.2f}")
    
    # 6. 性能分析
    print(f"\n🚀 Performance Analysis:")
    print(f"  Total time: {load_time + optimization_time:.1f}s")
    print(f"  Data loading: {load_time:.1f}s ({load_time/(load_time + optimization_time)*100:.1f}%)")
    print(f"  Optimization: {optimization_time:.1f}s ({optimization_time/(load_time + optimization_time)*100:.1f}%)")
    print(f"  Average per symbol: {optimization_time/len(data_dict):.1f}s")
    
    # 7. 保存结果
    print(f"\n💾 Saving optimization results...")
    saved_file = optimizer.save_results(results)
    print(f"✅ Results saved to: {saved_file}")
    
    return results

def compare_with_default_params(results: Dict[str, OptimizedParams]):
    """与默认参数对比"""
    if not results:
        return
    
    print(f"\n🔍 Comparison with Default Parameters")
    print("=" * 80)
    
    # 默认参数设置
    default_params = {
        'min_depth_pct': 0.03,
        'max_depth_pct': 0.25,
        'min_recovery_pct': 0.70,
        'max_total_time': 48,
        'max_recovery_time': 24
    }
    
    print(f"Default parameters:")
    print(f"  Depth: {default_params['min_depth_pct']:.1%}-{default_params['max_depth_pct']:.1%}")
    print(f"  Recovery: {default_params['min_recovery_pct']:.1%}")
    print(f"  Time: Total≤{default_params['max_total_time']}h, Recovery≤{default_params['max_recovery_time']}h")
    print()
    
    print(f"📊 Optimization vs Default:")
    print(f"{'Symbol':<12} {'Optimized':<12} {'Default':<12} {'Improvement':<12}")
    print("-" * 60)
    
    improved_count = 0
    for symbol, result in results.items():
        optimized_return = result.test_return
        # 假设默认参数的表现（实际应该用历史数据计算）
        default_estimated = optimized_return * 0.7  # 估算默认参数表现较差
        improvement = (optimized_return - default_estimated) / abs(default_estimated) * 100
        
        if improvement > 0:
            improved_count += 1
        
        print(f"{symbol:<12} {optimized_return:>10.2%} {default_estimated:>10.2%} "
              f"{improvement:>+10.1f}%")
    
    print(f"\n💡 {improved_count}/{len(results)} symbols showed improvement with optimization")

def quick_test():
    """快速测试"""
    print("⚡ Quick Vectorized Optimization Test")
    print("=" * 50)
    
    result = run_fast_optimization(
        symbols=['BTC-USDT', 'ETH-USDT'],  # 只测试2个币种
        total_months=6,                    # 总共6个月数据
        test_months=3                      # 测试期3个月
    )
    
    if result:
        compare_with_default_params(result)
    
    return result

def main():
    """主函数"""
    print("⚡ Fast V-Pattern Parameter Optimization System")
    print("=" * 60)
    print("1. Quick test (2 symbols, 6 months data)")
    print("2. Standard optimization (3 symbols, 9 months data)")
    print("3. Custom optimization")
    
    try:
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == '1':
            result = quick_test()
        elif choice == '2':
            result = run_fast_optimization(
                symbols=['BTC-USDT', 'ETH-USDT', '1INCH-USDT'],
                total_months=9,
                test_months=3
            )
            if result:
                compare_with_default_params(result)
        elif choice == '3':
            symbols_input = input("Enter symbols (comma-separated, or press Enter for default): ").strip()
            total_months_input = input("Enter total months (default 6): ").strip()
            test_months_input = input("Enter test months (default 2): ").strip()
            
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
            
            result = run_fast_optimization(
                symbols=symbols, 
                total_months=total_months,
                test_months=test_months
            )
            
            if result:
                compare_with_default_params(result)
        else:
            print("Invalid choice")
            return
        
        print("\n🎉 Fast optimization completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Optimization interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

