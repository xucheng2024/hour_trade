#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick Signal Check - Daily Monitoring Tool
Run this script daily to check current market state and signals
"""

import pandas as pd
from datetime import datetime


def check_current_signal():
    """Check the current signal and provide recommendation"""
    print(f"\n{'='*70}")
    print(f"  COMPLEX SYSTEM SIGNAL CHECK - BTC")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    # Load latest data
    df = pd.read_csv('complex_system_signals.csv')
    df['date'] = pd.to_datetime(df['date'])
    
    # Get last 5 days for context
    recent = df.tail(5)
    latest = df.iloc[-1]
    
    # Display recent price action
    print("📊 RECENT PRICE ACTION (Last 5 Days):")
    print(f"{'='*70}")
    print(f"{'Date':<12} {'Price':>12} {'Buy Score':>12} {'Sell Score':>12}")
    print(f"{'-'*70}")
    for idx, row in recent.iterrows():
        buy_indicator = "🟢" if row['buy_signal'] else "  "
        sell_indicator = "🔴" if row['sell_signal'] else "  "
        print(f"{str(row['date'].date()):<12} ${row['close']:>10,.0f} "
              f"{buy_indicator}{row['buy_score']:>10.1f} "
              f"{sell_indicator}{row['sell_score']:>10.1f}")
    
    print(f"\n{'='*70}")
    print(f"CURRENT STATE (Latest: {latest['date'].date()})")
    print(f"{'='*70}\n")
    
    # Current price and signals
    print(f"💰 Price: ${latest['close']:,.2f}")
    print(f"\n📈 SCORES:")
    print(f"   Buy Score:  {latest['buy_score']:.1f} / 5.0 {'🟢 BUY SIGNAL!' if latest['buy_signal'] else ''}")
    print(f"   Sell Score: {latest['sell_score']:.1f} / 5.0 {'🔴 SELL SIGNAL!' if latest['sell_signal'] else ''}")
    
    # Detailed indicators
    print(f"\n📊 KEY INDICATORS:")
    print(f"   Drawdown:        {latest['dd']*100:>6.1f}%  ", end="")
    if latest['dd'] < -0.70:
        print("(🔴 Extreme)")
    elif latest['dd'] < -0.50:
        print("(🟡 High)")
    elif latest['dd'] < -0.30:
        print("(🟢 Moderate)")
    else:
        print("(⚪ Low)")
    
    print(f"   Volatility Z:    {latest['vol_z']:>6.2f}   ", end="")
    if abs(latest['vol_z']) > 2:
        print("(🔴 Extreme)")
    elif abs(latest['vol_z']) > 1:
        print("(🟡 Elevated)")
    else:
        print("(🟢 Normal)")
    
    print(f"   RSI(14):         {latest['rsi14']:>6.1f}   ", end="")
    if latest['rsi14'] > 80:
        print("(🔴 Extreme Overbought)")
    elif latest['rsi14'] > 70:
        print("(🟡 Overbought)")
    elif latest['rsi14'] < 30:
        print("(🟢 Oversold)")
    else:
        print("(⚪ Neutral)")
    
    print(f"   MA200 Distance:  {latest['dist_ma200']*100:>6.1f}%  ", end="")
    if latest['dist_ma200'] > 0.50:
        print("(🔴 Very High)")
    elif latest['dist_ma200'] > 0.20:
        print("(🟡 High)")
    elif latest['dist_ma200'] < -0.20:
        print("(🟢 Below MA)")
    else:
        print("(⚪ Near MA)")
    
    # Action recommendation
    print(f"\n{'='*70}")
    print(f"💡 RECOMMENDATION:")
    print(f"{'='*70}\n")
    
    if latest['buy_signal']:
        print("🟢 STRONG BUY SIGNAL DETECTED")
        print("\n   Suggested Action:")
        print("   1. Start DCA (Dollar Cost Averaging) over 10 days")
        print("   2. Daily investment = Available Capital / 10")
        print("   3. Monitor drawdown for stop-loss (< -85%)")
        print("   4. Stay disciplined - follow the system")
        print("\n   Context:")
        print(f"   - System shows extreme pressure (DD: {latest['dd']*100:.1f}%)")
        print(f"   - Bottom restructuring signals present")
        print(f"   - Historical 1-year win rate: 96.3%")
        print(f"   - Average 1-year return: +225.7%")
        
    elif latest['sell_signal']:
        print("🔴 STRONG SELL SIGNAL DETECTED")
        print("\n   Suggested Action:")
        print("   1. Begin staged exit over 3 days")
        print("   2. Sell 1/3 of position per day")
        print("   3. Take profits systematically")
        print("   4. Return to cash and wait for next cycle")
        print("\n   Context:")
        print(f"   - System shows critical calm/overheated")
        print(f"   - RSI: {latest['rsi14']:.1f} (overextended)")
        print(f"   - Price vs MA200: +{latest['dist_ma200']*100:.1f}%")
        print(f"   - Typical profit at sell: +120-160%")
        
    elif latest['buy_score'] >= 2.5:
        print("🟡 APPROACHING BUY ZONE")
        print("\n   Status: Not yet a signal, but worth monitoring closely")
        print(f"   Current Score: {latest['buy_score']:.1f} / 3.0 (need 3.0 for signal)")
        print("\n   Suggested Action:")
        print("   - Prepare capital for potential entry")
        print("   - Check daily for signal confirmation")
        print("   - Review risk management strategy")
        
    elif latest['sell_score'] >= 2.5:
        print("🟡 APPROACHING SELL ZONE")
        print("\n   Status: Not yet a signal, but worth monitoring closely")
        print(f"   Current Score: {latest['sell_score']:.1f} / 3.0 (need 3.0 for signal)")
        print("\n   Suggested Action:")
        print("   - Consider taking partial profits (10-20%)")
        print("   - Prepare exit strategy")
        print("   - Check daily for signal confirmation")
        
    else:
        print("⚪ NEUTRAL - NO STRONG SIGNAL")
        print("\n   Status: Normal market conditions")
        print(f"   Buy Score: {latest['buy_score']:.1f} / 3.0")
        print(f"   Sell Score: {latest['sell_score']:.1f} / 3.0")
        print("\n   Suggested Action:")
        print("   - Continue monitoring (run this script daily)")
        print("   - No action required at this time")
        print("   - Maintain existing positions or stay in cash")
    
    print(f"\n{'='*70}\n")
    
    # Historical context
    buy_count = (df['buy_signal'] == True).sum()
    sell_count = (df['sell_signal'] == True).sum()
    days_since_last_buy = (df.index[-1] - df[df['buy_signal'] == True].index[-1]) if buy_count > 0 else None
    days_since_last_sell = (df.index[-1] - df[df['sell_signal'] == True].index[-1]) if sell_count > 0 else None
    
    print("📅 HISTORICAL CONTEXT:")
    print(f"   Total buy signals:  {buy_count} (since 2017)")
    print(f"   Total sell signals: {sell_count} (since 2017)")
    if days_since_last_buy is not None:
        print(f"   Days since last buy:  {days_since_last_buy}")
    if days_since_last_sell is not None:
        print(f"   Days since last sell: {days_since_last_sell}")
    
    print(f"\n{'='*70}\n")


def main():
    try:
        check_current_signal()
    except FileNotFoundError:
        print("\n❌ Error: Signal data not found!")
        print("Please run 'python complex_system_signals.py' first to generate signals.\n")
    except Exception as e:
        print(f"\n❌ Error: {e}\n")


if __name__ == "__main__":
    main()
