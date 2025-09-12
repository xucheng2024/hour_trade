#!/usr/bin/env python3
"""
测试小时数据的最佳卖出时机
策略：当后续24小时内最高价超过开盘价*比例时买入，测试买入后1-24小时内最佳卖出时机
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os

def test_hourly_sell_timing(crypto, params, lookahead_hours=24):
    """
    测试小时数据的最佳卖出时机
    
    Args:
        crypto: 加密货币名称
        params: 优化参数 (包含high_open_ratio_threshold和volume_ratio_threshold)
        lookahead_hours: 向前看的小时数
    """
    p_threshold = params['high_open_ratio_threshold']
    v_threshold = params['volume_ratio_threshold']
    
    print(f"\n📊 测试 {crypto} 小时数据卖出时机:")
    print(f"  使用优化参数: P={p_threshold:.1%}, V={v_threshold:.1f}x")
    print(f"  策略: 当未来{lookahead_hours}小时内最高价 > 开盘价 × (1+{p_threshold:.1%}) 且成交量条件满足时买入")
    print(f"  测试: 买入后1-24小时内最佳卖出时机")
    
    try:
        # 获取小时数据
        data_file = f"data/{crypto}_1H.npz"
        if not os.path.exists(data_file):
            print(f"  ❌ 小时数据文件不存在")
            return None
            
        data = np.load(data_file)
        raw_data = data['data']
        timestamps = pd.to_datetime(raw_data[:, 0].astype(int), unit='ms')
        
        # 计算时间范围（最近3个月）
        end_date = timestamps.max()
        start_date = end_date - timedelta(days=90)
        mask = (timestamps >= start_date) & (timestamps <= end_date)
        recent_data = raw_data[mask]
        recent_timestamps = timestamps[mask]
        
        print(f"  数据时间范围: {start_date.strftime('%Y-%m-%d %H:%M')} 至 {end_date.strftime('%Y-%m-%d %H:%M')}")
        print(f"  数据点数量: {len(recent_data)} 小时")
        
        # 转换数据
        df = pd.DataFrame({
            'timestamp': recent_timestamps,
            'open': recent_data[:, 1].astype(float),
            'high': recent_data[:, 2].astype(float),
            'low': recent_data[:, 3].astype(float),
            'close': recent_data[:, 4].astype(float),
            'volume': recent_data[:, 5].astype(float)
        })
        
        # 寻找买入信号
        buy_signals = []
        
        for i in range(len(df) - lookahead_hours):
            current_open = df.iloc[i]['open']
            current_high = df.iloc[i]['high']
            current_volume = df.iloc[i]['volume']
            previous_volume = df.iloc[i-1]['volume'] if i > 0 else current_volume
            
            # 计算价格比率和成交量比率
            price_ratio = (current_high - current_open) / current_open
            volume_ratio = current_volume / previous_volume if previous_volume > 0 else 1
            
            # 检查是否满足买入条件
            if price_ratio >= p_threshold and volume_ratio >= v_threshold:
                buy_signals.append({
                    'buy_hour': i,
                    'buy_price': current_open,
                    'price_ratio': price_ratio,
                    'volume_ratio': volume_ratio,
                    'timestamp': df.iloc[i]['timestamp']
                })
        
        print(f"  买入信号数量: {len(buy_signals)}")
        
        if len(buy_signals) == 0:
            print(f"  ❌ 没有找到买入信号")
            return None
        
        # 测试不同卖出时机的收益
        sell_timing_results = {}
        
        for sell_hours in range(1, min(25, lookahead_hours + 1)):  # 1-24小时
            returns = []
            successful_trades = 0
            
            for signal in buy_signals:
                buy_idx = signal['buy_hour']
                sell_idx = buy_idx + sell_hours
                
                # 确保卖出时间在数据范围内
                if sell_idx < len(df):
                    buy_price = signal['buy_price']
                    sell_price = df.iloc[sell_idx]['close']
                    
                    # 计算收益（扣除手续费）
                    fee = 0.002  # 0.1% 买入 + 0.1% 卖出
                    profit = (sell_price - buy_price) / buy_price - fee
                    
                    returns.append(profit)
                    if profit > 0:
                        successful_trades += 1
            
            if returns:
                returns = np.array(returns)
                win_rate = successful_trades / len(returns)
                compound_return = np.prod(1 + returns)
                mean_return = np.mean(returns)
                median_return = np.median(returns)
                
                sell_timing_results[sell_hours] = {
                    'total_trades': len(returns),
                    'win_rate': win_rate,
                    'compound_return': compound_return,
                    'mean_return': mean_return,
                    'median_return': median_return,
                    'std_return': np.std(returns)
                }
        
        # 找到最佳卖出时机
        if sell_timing_results:
            best_timing = max(sell_timing_results.items(), key=lambda x: x[1]['compound_return'])
            best_hours = best_timing[0]
            best_result = best_timing[1]
            
            print(f"\n  🏆 最佳卖出时机: {best_hours}小时后")
            print(f"    复合收益: {best_result['compound_return']:.6f}")
            print(f"    胜率: {best_result['win_rate']:.1%}")
            print(f"    平均收益: {best_result['mean_return']:.4f}")
            print(f"    中位数收益: {best_result['median_return']:.4f}")
            print(f"    交易次数: {best_result['total_trades']}")
            
            # 显示前5个最佳时机
            sorted_timings = sorted(sell_timing_results.items(), 
                                  key=lambda x: x[1]['compound_return'], 
                                  reverse=True)[:5]
            
            print(f"\n  📈 前5个最佳卖出时机:")
            for i, (hours, result) in enumerate(sorted_timings, 1):
                print(f"    {i}. {hours}小时: 复合收益={result['compound_return']:.6f}, 胜率={result['win_rate']:.1%}, 交易次数={result['total_trades']}")
            
            return {
                'crypto': crypto,
                'p_threshold': p_threshold,
                'v_threshold': v_threshold,
                'buy_signals': len(buy_signals),
                'best_timing': best_hours,
                'best_result': best_result,
                'all_timings': sell_timing_results
            }
        
        return None
        
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        return None

def main():
    """主函数"""
    print("🚀 使用优化参数测试小时数据最佳卖出时机")
    print("=" * 60)
    
    # 加载优化参数
    try:
        with open('crypto_trading_triggers.json', 'r') as f:
            config = json.load(f)
            optimized_params = config.get('triggers', {})
        print(f"✅ 加载了 {len(optimized_params)} 个加密货币的优化参数")
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return
    
    # 测试几个代表性加密货币
    test_cryptos = [
        'BTC-USDT',
        'ETH-USDT', 
        'SOL-USDT',
        'DOGE-USDT',
        'ADA-USDT'
    ]
    
    all_results = {}
    
    for crypto in test_cryptos:
        if crypto in optimized_params:
            print(f"\n{'='*60}")
            result = test_hourly_sell_timing(crypto, optimized_params[crypto])
            
            if result:
                all_results[crypto] = result
    
    # 生成总结报告
    print(f"\n{'='*60}")
    print("📊 总结报告")
    print("=" * 60)
    
    for crypto, result in all_results.items():
        if result:
            best_hours = result['best_timing']
            best_compound = result['best_result']['compound_return']
            best_winrate = result['best_result']['win_rate']
            total_signals = result['buy_signals']
            p_threshold = result['p_threshold']
            v_threshold = result['v_threshold']
            
            print(f"\n📈 {crypto}:")
            print(f"  参数: P={p_threshold:.1%}, V={v_threshold:.1f}x")
            print(f"  最佳卖出时机: {best_hours}小时")
            print(f"  复合收益: {best_compound:.6f}")
            print(f"  胜率: {best_winrate:.1%}")
            print(f"  交易信号: {total_signals}个")
    
    # 保存结果
    try:
        with open('hourly_sell_timing_results.json', 'w') as f:
            json.dump(all_results, f, indent=2, default=str)
        print(f"\n✅ 结果已保存到: hourly_sell_timing_results.json")
    except Exception as e:
        print(f"❌ 保存结果失败: {e}")

if __name__ == "__main__":
    main()
