#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V-Pattern Parameter Optimization Runner
V型模式参数优化运行器
"""

import os
import sys
import logging
from datetime import datetime
from typing import Dict, List

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import VReversalDataLoader
from parameter_optimizer import VPatternParameterOptimizer, print_optimization_summary, ValidationResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def run_parameter_optimization(symbols: List[str] = None, 
                             total_months: int = 9,
                             test_months: int = 3) -> Dict[str, ValidationResult]:
    """
    运行V型模式参数优化
    
    Args:
        symbols: 要优化的币种列表
        total_months: 总数据月数
        test_months: 测试期月数
        
    Returns:
        优化验证结果字典
    """
    print("🚀 V-Pattern Parameter Optimization")
    print("=" * 60)
    print(f"📊 Configuration:")
    print(f"  Total data period: {total_months} months")
    print(f"  Training period: {total_months - test_months} months")
    print(f"  Test period: {test_months} months")
    print()
    
    # 1. 加载数据
    print("📊 Loading data...")
    data_loader = VReversalDataLoader()
    
    if symbols is None:
        # 选择一些主要币种进行优化
        available_symbols = data_loader.get_available_symbols()
        symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT', '1INCH-USDT', 'AAVE-USDT']
        symbols = [s for s in symbols if s in available_symbols][:3]  # 限制为3个币种以加快速度
    
    data_dict = data_loader.load_multiple_symbols(symbols, months=total_months)
    
    if not data_dict:
        print("❌ No data loaded")
        return {}
    
    print(f"✅ Loaded data for {len(data_dict)} symbols")
    
    # 显示数据信息
    for symbol, df in data_dict.items():
        print(f"  {symbol}: {len(df)} records, "
              f"{df['timestamp'].min().strftime('%Y-%m-%d')} to "
              f"{df['timestamp'].max().strftime('%Y-%m-%d')}")
    print()
    
    # 2. 创建优化器
    print("🔧 Initializing parameter optimizer...")
    optimizer = VPatternParameterOptimizer(
        test_months=test_months,
        min_train_months=total_months - test_months - 1,
        max_workers=2  # 减少并发以避免过载
    )
    
    # 3. 运行优化和验证
    print("⚡ Starting parameter optimization...")
    print("   This may take a few minutes...")
    print()
    
    validation_results = optimizer.run_full_optimization_and_validation(data_dict)
    
    if not validation_results:
        print("❌ No successful optimizations")
        return {}
    
    # 4. 显示结果
    print_optimization_summary(validation_results)
    
    # 5. 详细参数显示
    print(f"\n📋 Optimized Parameters for Each Symbol:")
    print("=" * 80)
    
    for symbol, result in validation_results.items():
        params = result.optimal_params
        print(f"\n🎯 {symbol}:")
        print(f"  Depth range: {params.min_depth_pct:.1%} - {params.max_depth_pct:.1%}")
        print(f"  Recovery requirement: {params.min_recovery_pct:.1%}")
        print(f"  Time limits: Total ≤ {params.max_total_time}h, Recovery ≤ {params.max_recovery_time}h")
        print(f"  Training: {params.train_patterns} patterns → {params.train_trades} trades "
              f"({params.train_win_rate:.1%} win rate, {params.train_total_return:.1%} return)")
        print(f"  Testing: {result.test_patterns} patterns → {result.test_trades} trades "
              f"({result.test_win_rate:.1%} win rate, {result.test_total_return:.1%} return)")
        print(f"  Consistency: {result.consistency_ratio:.2f}")
    
    # 6. 保存结果
    print(f"\n💾 Saving optimization results...")
    saved_file = optimizer.save_optimization_results(validation_results)
    print(f"✅ Results saved to: {saved_file}")
    
    return validation_results

def quick_optimization():
    """快速优化测试"""
    print("⚡ Quick Parameter Optimization Test")
    print("=" * 50)
    
    # 使用较少币种和较短时间进行快速测试
    result = run_parameter_optimization(
        symbols=['BTC-USDT', 'ETH-USDT'],  # 只测试2个币种
        total_months=6,                    # 总共6个月数据
        test_months=2                      # 测试期2个月
    )
    
    return result

def full_optimization():
    """完整优化"""
    print("🔬 Full Parameter Optimization")
    print("=" * 50)
    
    # 使用更多币种和更长时间进行完整优化
    result = run_parameter_optimization(
        symbols=None,      # 使用默认币种列表
        total_months=9,    # 总共9个月数据
        test_months=3      # 测试期3个月
    )
    
    return result

def compare_with_default_params(validation_results: Dict[str, ValidationResult]):
    """与默认参数对比"""
    if not validation_results:
        return
    
    print(f"\n🔍 Comparing with Default Parameters")
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
    
    print(f"{'Symbol':<12} {'Optimized Return':<16} {'vs Default':<12}")
    print("-" * 50)
    
    for symbol, result in validation_results.items():
        optimized_return = result.test_total_return
        # 这里可以添加与默认参数的对比逻辑
        print(f"{symbol:<12} {optimized_return:>14.2%} {'(Optimized)':>11}")

def main():
    """主函数"""
    print("🎯 V-Pattern Parameter Optimization System")
    print("=" * 60)
    print("1. Quick optimization (2 symbols, 6 months data)")
    print("2. Full optimization (3+ symbols, 9 months data)")
    print("3. Custom optimization")
    
    try:
        choice = input("\nSelect option (1-3): ").strip()
        
        if choice == '1':
            result = quick_optimization()
        elif choice == '2':
            result = full_optimization()
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
            
            result = run_parameter_optimization(
                symbols=symbols, 
                total_months=total_months,
                test_months=test_months
            )
        else:
            print("Invalid choice")
            return
        
        # 对比分析
        if result:
            compare_with_default_params(result)
        
        print("\n🎉 Parameter optimization completed successfully!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Optimization interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during optimization: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()

