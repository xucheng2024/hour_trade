#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETH V-Pattern Trading Example
ETH V型反转交易实例演示
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def create_eth_example():
    """创建ETH V型反转的具体例子"""
    
    # 模拟24小时的ETH价格数据
    hours = np.arange(0, 25)
    
    # 创建V型价格走势
    # 0-8h: 从3000跌到2700 (10%跌幅)
    # 8-16h: 从2700涨到2880 (60%恢复)
    # 16-24h: 继续小幅波动
    
    prices = []
    for h in hours:
        if h <= 8:  # 下跌阶段
            price = 3000 - (3000 - 2700) * (h / 8)
        elif h <= 16:  # 恢复阶段
            recovery = (3000 - 2700) * 0.6  # 60%恢复
            price = 2700 + recovery * ((h - 8) / 8)
        else:  # 买入后波动
            base_price = 2880
            noise = np.sin((h - 16) * 0.5) * 20  # 小幅波动
            price = base_price + noise
        
        prices.append(price)
    
    return hours, np.array(prices)

def analyze_v_pattern(hours, prices):
    """分析V型模式的关键时点"""
    
    print("🎯 ETH V型反转买入实例分析")
    print("=" * 50)
    
    # 关键时点
    peak_time = 0
    trough_time = 8
    recovery_time = 16
    
    peak_price = prices[peak_time]
    trough_price = prices[trough_time]
    recovery_price = prices[recovery_time]
    
    # 计算指标
    depth_pct = (peak_price - trough_price) / peak_price
    recovery_pct = (recovery_price - trough_price) / (peak_price - trough_price)
    total_time = recovery_time - peak_time
    recovery_duration = recovery_time - trough_time
    
    print(f"📊 V型模式分析:")
    print(f"  📈 高点: ${peak_price:.0f} (第{peak_time}小时)")
    print(f"  📉 低点: ${trough_price:.0f} (第{trough_time}小时)")
    print(f"  🔄 恢复点: ${recovery_price:.0f} (第{recovery_time}小时)")
    print()
    
    print(f"📋 关键指标检查:")
    print(f"  ✅ 跌幅: {depth_pct:.1%} (目标: 3%-10%)")
    print(f"  ✅ 恢复度: {recovery_pct:.1%} (目标: ≥60%)")
    print(f"  ✅ 总时长: {total_time}小时 (目标: ≤24小时)")
    print(f"  ✅ 恢复时长: {recovery_duration}小时 (目标: ≤18小时)")
    print()
    
    # 交易执行
    entry_price = recovery_price
    stop_loss = entry_price * 0.92  # 8%止损
    take_profit = entry_price * 1.15  # 15%止盈
    
    print(f"🎯 交易执行:")
    print(f"  💰 买入价: ${entry_price:.0f}")
    print(f"  🛡️ 止损价: ${stop_loss:.0f} (-8%)")
    print(f"  🎯 止盈价: ${take_profit:.0f} (+15%)")
    print(f"  ⏰ 最长持有: 16小时")
    print()
    
    # 情景分析
    print(f"📈 可能结果:")
    print(f"  🎉 止盈 (到达${take_profit:.0f}): +15% = +${(take_profit-entry_price):.0f}")
    print(f"  😢 止损 (跌到${stop_loss:.0f}): -8% = -${(entry_price-stop_loss):.0f}")
    print(f"  😐 时间到期: 取决于16小时后价格")
    
    return {
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'depth_pct': depth_pct,
        'recovery_pct': recovery_pct
    }

def simulate_trading_outcome(analysis):
    """模拟交易结果"""
    print("\n" + "="*50)
    print("🎲 交易结果模拟")
    print("="*50)
    
    entry_price = analysis['entry_price']
    
    # 模拟三种情况
    scenarios = [
        {"name": "🎯 止盈情况", "exit_price": 3312, "reason": "达到15%止盈"},
        {"name": "🛡️ 止损情况", "exit_price": 2649, "reason": "触发8%止损"},
        {"name": "⏰ 时间到期", "exit_price": 3050, "reason": "16小时后市价卖出"}
    ]
    
    for scenario in scenarios:
        exit_price = scenario['exit_price']
        return_pct = (exit_price - entry_price) / entry_price
        profit = exit_price - entry_price
        
        print(f"\n{scenario['name']}:")
        print(f"  买入: ${entry_price:.0f}")
        print(f"  卖出: ${exit_price:.0f}")
        print(f"  收益: {return_pct:+.1%} (${profit:+.0f})")
        print(f"  原因: {scenario['reason']}")

def plot_v_pattern(hours, prices, analysis):
    """绘制V型模式图"""
    plt.figure(figsize=(12, 8))
    
    # 绘制价格曲线
    plt.plot(hours, prices, 'b-', linewidth=2, label='ETH Price')
    
    # 标记关键点
    plt.axvline(x=0, color='g', linestyle='--', alpha=0.7, label='Peak (High)')
    plt.axvline(x=8, color='r', linestyle='--', alpha=0.7, label='Trough (Low)')
    plt.axvline(x=16, color='orange', linestyle='--', alpha=0.7, label='Entry Signal')
    
    # 标记买入点
    entry_price = analysis['entry_price']
    plt.scatter([16], [entry_price], color='orange', s=100, zorder=5, label=f'Buy: ${entry_price:.0f}')
    
    # 标记止盈止损线
    plt.axhline(y=analysis['stop_loss'], color='red', linestyle=':', alpha=0.7, label=f'Stop Loss: ${analysis["stop_loss"]:.0f}')
    plt.axhline(y=analysis['take_profit'], color='green', linestyle=':', alpha=0.7, label=f'Take Profit: ${analysis["take_profit"]:.0f}')
    
    plt.xlabel('Time (Hours)')
    plt.ylabel('ETH Price (USD)')
    plt.title('ETH V-Pattern Reversal Trading Example\nOptimized Parameters: 3-10% depth, 60% recovery, 8% SL, 15% TP')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # 保存图片
    plt.savefig('/Users/mac/Downloads/stocks/ex_okx/v_reversal_research/eth_v_pattern_example.png', 
                dpi=300, bbox_inches='tight')
    print(f"\n📊 图表已保存: v_reversal_research/eth_v_pattern_example.png")
    plt.close()

def main():
    """主函数"""
    print("💎 ETH V型反转策略买入时机详解")
    print("="*60)
    
    # 1. 创建示例数据
    hours, prices = create_eth_example()
    
    # 2. 分析V型模式
    analysis = analyze_v_pattern(hours, prices)
    
    # 3. 模拟交易结果
    simulate_trading_outcome(analysis)
    
    # 4. 绘制图表
    plot_v_pattern(hours, prices, analysis)
    
    print(f"\n💡 总结:")
    print(f"这就是优化后的ETH V型反转策略的买入时机！")
    print(f"关键是要耐心等待V型模式完成确认后再买入。")

if __name__ == "__main__":
    main()
