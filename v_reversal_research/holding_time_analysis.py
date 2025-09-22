#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Holding Time Analysis for V-Pattern Strategy
V型反转策略持有时间分析
"""

import os
import sys
import logging
import time
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_loader import VReversalDataLoader
from profit_maximizer import VectorizedProfitMaximizer, MaxProfitParams

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_holding_time_impact(symbols: List[str] = None, total_months: int = 6, test_months: int = 3):
    """
    分析不同持有时间对收益的影响
    """
    print("📊 V-Pattern Strategy: Holding Time Impact Analysis")
    print("=" * 70)
    print("🎯 重点分析: 买入后最佳持有时间")
    print("⏰ 测试范围: 6小时 到 72小时")
    print()
    
    # 1. 加载数据
    print("📊 Loading data...")
    data_loader = VReversalDataLoader()
    
    if symbols is None:
        symbols = ['BTC-USDT', 'ETH-USDT']
    
    data_dict = data_loader.load_multiple_symbols(symbols, months=total_months)
    
    if not data_dict:
        print("❌ No data loaded")
        return None
    
    print(f"✅ Loaded data for {len(data_dict)} symbols")
    
    # 2. 运行优化
    print("\n⚡ Starting holding time optimization...")
    maximizer = VectorizedProfitMaximizer(test_months=test_months)
    
    start_time = time.time()
    results = maximizer.optimize_multiple_symbols(data_dict)
    optimization_time = time.time() - start_time
    
    if not results:
        print("❌ No successful optimizations")
        return None
    
    print(f"✅ Optimization completed in {optimization_time:.1f}s")
    
    # 3. 分析持有时间影响
    analyze_holding_time_patterns(results)
    
    # 4. 保存详细结果
    save_holding_analysis(results, maximizer)
    
    return results

def analyze_holding_time_patterns(results: Dict[str, MaxProfitParams]):
    """分析持有时间模式"""
    print(f"\n⏰ Holding Time Analysis Results")
    print("=" * 80)
    
    for symbol, result in results.items():
        print(f"\n💰 {symbol} - Optimal Holding Configuration:")
        print(f"  🕐 最佳持有时间: {result.holding_hours} 小时")
        print(f"  📈 测试收益: {result.test_return:.2%}")
        print(f"  🎯 胜率: {result.test_win_rate:.1%}")
        print(f"  📊 交易次数: {result.test_trades}")
        print(f"  ⚖️ 盈亏比: {result.profit_factor:.2f}")
        
        # 分析持有时间的合理性
        analyze_holding_logic(symbol, result)

def analyze_holding_logic(symbol: str, result: MaxProfitParams):
    """分析持有时间的逻辑"""
    holding_hours = result.holding_hours
    
    print(f"  🧠 持有时间分析:")
    
    if holding_hours <= 8:
        print(f"    ⚡ 超短线策略 ({holding_hours}h) - 快进快出，适合高频交易")
        risk_level = "低风险"
    elif holding_hours <= 24:
        print(f"    🎯 短线策略 ({holding_hours}h) - 日内交易，避免隔夜风险") 
        risk_level = "中等风险"
    elif holding_hours <= 48:
        print(f"    📈 中线策略 ({holding_hours}h) - 跨日持有，捕捉更大趋势")
        risk_level = "中高风险"
    else:
        print(f"    🏔️ 长线策略 ({holding_hours}h) - 多日持有，趋势跟踪")
        risk_level = "高风险"
    
    print(f"    🛡️ 风险等级: {risk_level}")
    
    # 计算理论年化收益
    if result.test_trades > 0:
        avg_days_per_trade = holding_hours / 24
        trades_per_year = 365 / avg_days_per_trade
        single_trade_return = result.test_return / result.test_trades
        theoretical_annual = single_trade_return * trades_per_year
        print(f"    📊 理论年化: {theoretical_annual:.1%} (基于平均单笔收益)")

def compare_holding_strategies(results: Dict[str, MaxProfitParams]):
    """对比不同持有策略"""
    print(f"\n📊 Holding Strategy Comparison")
    print("=" * 80)
    
    # 按持有时间分组
    strategies = {
        'Ultra Short (≤8h)': [],
        'Short (9-24h)': [],
        'Medium (25-48h)': [],
        'Long (>48h)': []
    }
    
    for symbol, result in results.items():
        hours = result.holding_hours
        if hours <= 8:
            strategies['Ultra Short (≤8h)'].append((symbol, result))
        elif hours <= 24:
            strategies['Short (9-24h)'].append((symbol, result))
        elif hours <= 48:
            strategies['Medium (25-48h)'].append((symbol, result))
        else:
            strategies['Long (>48h)'].append((symbol, result))
    
    for strategy_name, strategy_results in strategies.items():
        if not strategy_results:
            continue
            
        print(f"\n🎯 {strategy_name}:")
        avg_return = np.mean([r[1].test_return for r in strategy_results])
        avg_win_rate = np.mean([r[1].test_win_rate for r in strategy_results])
        avg_trades = np.mean([r[1].test_trades for r in strategy_results])
        
        print(f"  📈 平均收益: {avg_return:.2%}")
        print(f"  🎯 平均胜率: {avg_win_rate:.1%}")
        print(f"  📊 平均交易数: {avg_trades:.0f}")
        
        for symbol, result in strategy_results:
            print(f"    {symbol}: {result.holding_hours}h, {result.test_return:.1%}")

def save_holding_analysis(results: Dict[str, MaxProfitParams], maximizer: VectorizedProfitMaximizer):
    """保存持有时间分析结果"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"holding_time_analysis_{timestamp}.json"
    
    # 准备分析数据
    analysis_data = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "analysis_type": "holding_time_optimization",
            "focus": "optimal_holding_duration",
            "holding_range": "6-72 hours"
        },
        "summary": {
            "total_symbols": len(results),
            "avg_optimal_hours": np.mean([r.holding_hours for r in results.values()]),
            "holding_distribution": {}
        },
        "detailed_results": {}
    }
    
    # 统计持有时间分布
    holding_times = [r.holding_hours for r in results.values()]
    unique_times, counts = np.unique(holding_times, return_counts=True)
    
    for time_val, count in zip(unique_times, counts):
        analysis_data["summary"]["holding_distribution"][f"{time_val}h"] = int(count)
    
    # 详细结果
    for symbol, result in results.items():
        analysis_data["detailed_results"][symbol] = {
            "optimal_holding_hours": int(result.holding_hours),
            "test_return": float(result.test_return),
            "win_rate": float(result.test_win_rate),
            "trades": int(result.test_trades),
            "profit_factor": float(result.profit_factor),
            "max_drawdown": float(result.max_drawdown),
            "trading_params": {
                "stop_loss_pct": float(result.stop_loss_pct),
                "take_profit_pct": float(result.take_profit_pct)
            }
        }
    
    # 保存文件
    import json
    parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(parent_dir, 'data')
    results_path = os.path.join(data_dir, filename)
    
    with open(results_path, 'w') as f:
        json.dump(analysis_data, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Holding time analysis saved to: {results_path}")
    return results_path

def print_holding_time_insights():
    """打印持有时间优化的洞察"""
    print(f"\n💡 Holding Time Optimization Insights")
    print("=" * 80)
    print("🔍 关键发现:")
    print("  1. 持有时间过短 (<6h): 可能错过趋势发展")
    print("  2. 持有时间过长 (>72h): 承担更多市场风险")
    print("  3. 最优持有时间取决于:")
    print("     - 币种波动特性")
    print("     - 市场环境")
    print("     - 止盈止损设置")
    print("     - 交易频率要求")
    print()
    print("🎯 策略建议:")
    print("  • 超短线 (6-8h): 适合高波动期，快进快出")
    print("  • 短线 (12-24h): 平衡风险收益，日内完成")
    print("  • 中线 (24-48h): 捕捉较大趋势，适合趋势明确时")
    print("  • 长线 (48h+): 只在强趋势确认时使用")

def main():
    """主函数"""
    print("⏰ V-Pattern Holding Time Optimizer")
    print("=" * 60)
    print("🎯 专门优化买入后的最佳持有时间")
    print()
    
    try:
        # 运行持有时间分析
        results = analyze_holding_time_impact()
        
        if results:
            # 对比分析
            compare_holding_strategies(results)
            
            # 打印洞察
            print_holding_time_insights()
            
            print(f"\n🎉 持有时间优化完成!")
            print(f"💡 现在你知道每个币种的最佳持有时间了!")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Analysis interrupted by user")
    except Exception as e:
        print(f"\n❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
