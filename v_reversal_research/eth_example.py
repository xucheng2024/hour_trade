#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETH V-Pattern Trading Example
ETH V-shaped reversal trading example demonstration
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def create_eth_example():
    """Create specific ETH V-shaped reversal example"""
    
    # Simulate 24-hour ETH price data
    hours = np.arange(0, 25)
    
    # Create V-shaped price movement
    # 0-8h: Drop from 3000 to 2700 (10% decline)
    # 8-16h: Rise from 2700 to 2880 (60% recovery)
    # 16-24h: Continue with small fluctuations
    
    prices = []
    for h in hours:
        if h <= 8:  # Decline phase
            price = 3000 - (3000 - 2700) * (h / 8)
        elif h <= 16:  # Recovery phase
            recovery = (3000 - 2700) * 0.6  # 60% recovery
            price = 2700 + recovery * ((h - 8) / 8)
        else:  # Post-purchase fluctuations
            base_price = 2880
            noise = np.sin((h - 16) * 0.5) * 20  # Small fluctuations
            price = base_price + noise
        
        prices.append(price)
    
    return hours, np.array(prices)

def analyze_v_pattern(hours, prices):
    """Analyze key timing points of V-pattern"""
    
    print("🎯 ETH V-shaped Reversal Trading Example Analysis")
    print("=" * 50)
    
    # Key timing points
    peak_time = 0
    trough_time = 8
    recovery_time = 16
    
    peak_price = prices[peak_time]
    trough_price = prices[trough_time]
    recovery_price = prices[recovery_time]
    
    # Calculate indicators
    depth_pct = (peak_price - trough_price) / peak_price
    recovery_pct = (recovery_price - trough_price) / (peak_price - trough_price)
    total_time = recovery_time - peak_time
    recovery_duration = recovery_time - trough_time
    
    print(f"📊 V-pattern Analysis:")
    print(f"  📈 High: ${peak_price:.0f} (Hour {peak_time})")
    print(f"  📉 Low: ${trough_price:.0f} (Hour {trough_time})")
    print(f"  🔄 Recovery: ${recovery_price:.0f} (Hour {recovery_time})")
    print()
    
    print(f"📋 Key Indicator Checks:")
    print(f"  ✅ Decline: {depth_pct:.1%} (Target: 3%-10%)")
    print(f"  ✅ Recovery: {recovery_pct:.1%} (Target: ≥60%)")
    print(f"  ✅ Total time: {total_time} hours (Target: ≤24 hours)")
    print(f"  ✅ Recovery time: {recovery_duration} hours (Target: ≤18 hours)")
    print()
    
    # Trading execution
    entry_price = recovery_price
    stop_loss = entry_price * 0.92  # 8% stop loss
    take_profit = entry_price * 1.15  # 15% take profit
    
    print(f"🎯 Trading Execution:")
    print(f"  💰 Entry price: ${entry_price:.0f}")
    print(f"  🛡️ Stop loss: ${stop_loss:.0f} (-8%)")
    print(f"  🎯 Take profit: ${take_profit:.0f} (+15%)")
    print(f"  ⏰ Max holding: 16 hours")
    print()
    
    # Scenario analysis
    print(f"📈 Possible Outcomes:")
    print(f"  🎉 Take profit (reach ${take_profit:.0f}): +15% = +${(take_profit-entry_price):.0f}")
    print(f"  😢 Stop loss (drop to ${stop_loss:.0f}): -8% = -${(entry_price-stop_loss):.0f}")
    print(f"  😐 Time expiry: Depends on price after 16 hours")
    
    return {
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'take_profit': take_profit,
        'depth_pct': depth_pct,
        'recovery_pct': recovery_pct
    }

def simulate_trading_outcome(analysis):
    """Simulate trading outcomes"""
    print("\n" + "="*50)
    print("🎲 Trading Outcome Simulation")
    print("="*50)
    
    entry_price = analysis['entry_price']
    
    # Simulate three scenarios
    scenarios = [
        {"name": "🎯 Take profit scenario", "exit_price": 3312, "reason": "Reached 15% take profit"},
        {"name": "🛡️ Stop loss scenario", "exit_price": 2649, "reason": "Triggered 8% stop loss"},
        {"name": "⏰ Time expiry", "exit_price": 3050, "reason": "Market sell after 16 hours"}
    ]
    
    for scenario in scenarios:
        exit_price = scenario['exit_price']
        return_pct = (exit_price - entry_price) / entry_price
        profit = exit_price - entry_price
        
        print(f"\n{scenario['name']}:")
        print(f"  Buy: ${entry_price:.0f}")
        print(f"  Sell: ${exit_price:.0f}")
        print(f"  Return: {return_pct:+.1%} (${profit:+.0f})")
        print(f"  Reason: {scenario['reason']}")

def plot_v_pattern(hours, prices, analysis):
    """Plot V-pattern chart"""
    plt.figure(figsize=(12, 8))
    
    # Plot price curve
    plt.plot(hours, prices, 'b-', linewidth=2, label='ETH Price')
    
    # Mark key points
    plt.axvline(x=0, color='g', linestyle='--', alpha=0.7, label='Peak (High)')
    plt.axvline(x=8, color='r', linestyle='--', alpha=0.7, label='Trough (Low)')
    plt.axvline(x=16, color='orange', linestyle='--', alpha=0.7, label='Entry Signal')
    
    # Mark buy point
    entry_price = analysis['entry_price']
    plt.scatter([16], [entry_price], color='orange', s=100, zorder=5, label=f'Buy: ${entry_price:.0f}')
    
    # Mark stop loss and take profit lines
    plt.axhline(y=analysis['stop_loss'], color='red', linestyle=':', alpha=0.7, label=f'Stop Loss: ${analysis["stop_loss"]:.0f}')
    plt.axhline(y=analysis['take_profit'], color='green', linestyle=':', alpha=0.7, label=f'Take Profit: ${analysis["take_profit"]:.0f}')
    
    plt.xlabel('Time (Hours)')
    plt.ylabel('ETH Price (USD)')
    plt.title('ETH V-Pattern Reversal Trading Example\nOptimized Parameters: 3-10% depth, 60% recovery, 8% SL, 15% TP')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    
    # Save chart
    plt.savefig('/Users/mac/Downloads/stocks/ex_okx/v_reversal_research/eth_v_pattern_example.png', 
                dpi=300, bbox_inches='tight')
    print(f"\n📊 Chart saved: v_reversal_research/eth_v_pattern_example.png")
    plt.close()

def main():
    """Main function"""
    print("💎 ETH V-shaped Reversal Strategy Entry Timing Explained")
    print("="*60)
    
    # 1. Create example data
    hours, prices = create_eth_example()
    
    # 2. Analyze V-pattern
    analysis = analyze_v_pattern(hours, prices)
    
    # 3. Simulate trading outcomes
    simulate_trading_outcome(analysis)
    
    # 4. Plot chart
    plot_v_pattern(hours, prices, analysis)
    
    print(f"\n💡 Summary:")
    print(f"This is the optimized ETH V-shaped reversal strategy entry timing!")
    print(f"The key is to patiently wait for V-pattern completion confirmation before buying.")

if __name__ == "__main__":
    main()
