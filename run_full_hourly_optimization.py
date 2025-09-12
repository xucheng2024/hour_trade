#!/usr/bin/env python3
"""
对所有加密货币运行小时策略优化
基于现有的日策略参数，测试最优卖出时机
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os
import time

def test_hourly_strategy_for_crypto(crypto, params, lookahead_hours=24):
    """
    测试单个加密货币的小时策略
    
    Args:
        crypto: 加密货币名称
        params: 优化参数 (包含high_open_ratio_threshold和volume_ratio_threshold)
        lookahead_hours: 向前看的小时数
    """
    p_threshold = params['high_open_ratio_threshold']
    v_threshold = params['volume_ratio_threshold']
    
    try:
        # 获取小时数据
        data_file = f"data/{crypto}_1H.npz"
        if not os.path.exists(data_file):
            return None
        
        # 加载数据
        data = np.load(data_file)
        raw_data = data['data']
        
        # 转换为DataFrame (小时数据有9列)
        if raw_data.shape[1] == 9:
            # 小时数据格式: timestamp, open, high, low, close, volume, volume_ccy, volume_ccy, confirm
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volume_ccy', 'volume_ccy2', 'confirm'])
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]  # 只保留需要的列
        else:
            # 日数据格式: timestamp, open, high, low, close, volume
            df = pd.DataFrame(raw_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
        
        # 转换数值列为float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        # 获取最近3个月的数据
        end_date = df['timestamp'].max()
        start_date = end_date - timedelta(days=90)
        
        recent_data = df[df['timestamp'] >= start_date].copy()
        
        if len(recent_data) < 100:  # 至少需要100小时的数据
            return None
        
        # 寻找买入信号
        buy_signals = []
        
        for i in range(len(recent_data) - lookahead_hours):
            current_open = recent_data.iloc[i]['open']
            current_high = recent_data.iloc[i]['high']
            current_volume = recent_data.iloc[i]['volume']
            previous_volume = recent_data.iloc[i-1]['volume'] if i > 0 else current_volume
            
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
                    'timestamp': recent_data.iloc[i]['timestamp']
                })
        
        if len(buy_signals) == 0:
            return None
        
        # 测试不同卖出时机
        sell_timing_results = {}
        
        for sell_hours in range(1, 25):  # 1-24小时
            profits = []
            
            for signal in buy_signals:
                buy_time_idx = signal['buy_hour']
                buy_price = signal['buy_price']
                
                # 计算卖出价格（包含手续费）
                sell_time_idx = buy_time_idx + sell_hours
                if sell_time_idx < len(recent_data):
                    sell_price = recent_data.iloc[sell_time_idx]['close']
                    
                    # 计算利润（包含手续费）
                    buy_price_with_fee = buy_price * 1.001  # 买入手续费
                    sell_price_with_fee = sell_price * 0.999  # 卖出手续费
                    profit = (sell_price_with_fee / buy_price_with_fee) - 1
                    profits.append(profit)
            
            if profits:
                compound_return = np.prod([1 + p for p in profits])
                win_rate = sum(1 for p in profits if p > 0) / len(profits)
                mean_return = np.mean(profits)
                median_return = np.median(profits)
                
                sell_timing_results[sell_hours] = {
                    'compound_return': compound_return,
                    'win_rate': win_rate,
                    'mean_return': mean_return,
                    'median_return': median_return,
                    'total_trades': len(profits)
                }
        
        if not sell_timing_results:
            return None
        
        # 找到最佳卖出时机
        best_hours = max(sell_timing_results.keys(), 
                        key=lambda h: sell_timing_results[h]['compound_return'])
        best_result = sell_timing_results[best_hours]
        
        # 计算卖出价格比例
        compound_return = best_result['compound_return']
        avg_return = best_result['mean_return']
        sell_price_ratio = 1.0 + avg_return + 0.002  # 补偿手续费
        sell_price_ratio = min(max(sell_price_ratio, 1.01), 1.15)  # 限制在1%-15%之间
        
        # 确定风险等级
        win_rate = best_result['win_rate']
        if win_rate >= 0.8:
            risk_level = "low"
        elif win_rate >= 0.6:
            risk_level = "medium"
        else:
            risk_level = "high"
        
        return {
            'crypto': crypto,
            'p_threshold': p_threshold,
            'v_threshold': v_threshold,
            'buy_signals': len(buy_signals),
            'best_timing': best_hours,
            'sell_price_ratio': sell_price_ratio,
            'performance': {
                'compound_return': compound_return,
                'win_rate': win_rate,
                'mean_return': best_result['mean_return'],
                'median_return': best_result['median_return'],
                'total_trades': best_result['total_trades']
            },
            'risk_level': risk_level,
            'recommended': win_rate >= 0.5 and compound_return > 1.0
        }
        
    except Exception as e:
        print(f"  ❌ {crypto} 测试失败: {e}")
        return None

def run_full_hourly_optimization():
    """对所有加密货币运行小时策略优化"""
    
    print("🚀 开始对所有加密货币进行小时策略优化")
    print("=" * 80)
    
    # 加载日策略优化参数
    try:
        with open('crypto_trading_triggers.json', 'r') as f:
            config = json.load(f)
            triggers = config.get('triggers', {})
        print(f"✅ 加载了 {len(triggers)} 个加密货币的日策略参数")
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return
    
    results = {}
    success_count = 0
    total_count = len(triggers)
    
    print(f"📊 开始处理 {total_count} 个加密货币...")
    print("-" * 80)
    
    start_time = time.time()
    
    for i, (crypto, params) in enumerate(triggers.items(), 1):
        print(f"[{i:3d}/{total_count}] 处理 {crypto}...", end=" ")
        
        result = test_hourly_strategy_for_crypto(crypto, params)
        
        if result:
            results[crypto] = result
            success_count += 1
            print(f"✅ 成功 - 最佳{result['best_timing']}小时, 收益{result['performance']['compound_return']:.3f}×, 胜率{result['performance']['win_rate']:.1%}")
        else:
            print("❌ 失败")
        
        # 每10个显示进度
        if i % 10 == 0:
            elapsed = time.time() - start_time
            avg_time = elapsed / i
            remaining = (total_count - i) * avg_time
            print(f"    进度: {i}/{total_count} ({i/total_count:.1%}), 预计剩余: {remaining/60:.1f}分钟")
    
    print("\n" + "=" * 80)
    print("📊 小时策略优化完成!")
    print(f"成功处理: {success_count}/{total_count} ({success_count/total_count:.1%})")
    
    if success_count == 0:
        print("❌ 没有成功处理任何加密货币")
        return
    
    # 生成配置
    hourly_config = {
        "strategy_type": "hourly_sell_timing",
        "description": "基于优化参数的小时数据卖出时机配置 - 全量优化",
        "last_updated": datetime.now().strftime("%Y-%m-%d"),
        "data_period": "最近3个月小时数据",
        "fees": {
            "buy_fee": 0.001,
            "sell_fee": 0.001
        },
        "crypto_configs": {}
    }
    
    # 转换结果格式
    for crypto, result in results.items():
        hourly_config["crypto_configs"][crypto] = {
            "buy_conditions": {
                "high_open_ratio_threshold": result['p_threshold'],
                "volume_ratio_threshold": result['v_threshold']
            },
            "sell_timing": {
                "best_hours": result['best_timing'],
                "sell_price_ratio": result['sell_price_ratio'],
                "description": f"买入后{result['best_timing']}小时卖出，卖出价格为目标开盘价的{result['sell_price_ratio']:.1%}"
            },
            "performance": result['performance'],
            "risk_level": result['risk_level'],
            "recommended": bool(result['recommended'])
        }
    
    # 添加统计信息
    all_compound_returns = [r['performance']['compound_return'] for r in results.values()]
    all_win_rates = [r['performance']['win_rate'] for r in results.values()]
    all_best_hours = [r['best_timing'] for r in results.values()]
    
    hourly_config["statistics"] = {
        "total_cryptos": success_count,
        "success_rate": f"{success_count/total_count:.1%}",
        "compound_returns": {
            "min": float(np.min(all_compound_returns)),
            "max": float(np.max(all_compound_returns)),
            "mean": float(np.mean(all_compound_returns)),
            "median": float(np.median(all_compound_returns))
        },
        "win_rates": {
            "min": float(np.min(all_win_rates)),
            "max": float(np.max(all_win_rates)),
            "mean": float(np.mean(all_win_rates)),
            "median": float(np.median(all_win_rates))
        },
        "best_hours_distribution": {
            "min": int(np.min(all_best_hours)),
            "max": int(np.max(all_best_hours)),
            "mean": float(np.mean(all_best_hours)),
            "median": float(np.median(all_best_hours))
        }
    }
    
    # 保存配置
    try:
        with open('crypto_hourly_sell_config_full.json', 'w', encoding='utf-8') as f:
            json.dump(hourly_config, f, indent=2, ensure_ascii=False)
        print(f"✅ 完整配置已保存到: crypto_hourly_sell_config_full.json")
    except Exception as e:
        print(f"❌ 保存配置失败: {e}")
    
    # 显示统计摘要
    print(f"\n📈 统计摘要:")
    print(f"  复合收益范围: {np.min(all_compound_returns):.3f}× - {np.max(all_compound_returns):.3f}×")
    print(f"  平均复合收益: {np.mean(all_compound_returns):.3f}×")
    print(f"  胜率范围: {np.min(all_win_rates):.1%} - {np.max(all_win_rates):.1%}")
    print(f"  平均胜率: {np.mean(all_win_rates):.1%}")
    print(f"  最佳卖出时机范围: {np.min(all_best_hours)} - {np.max(all_best_hours)} 小时")
    print(f"  平均最佳卖出时机: {np.mean(all_best_hours):.1f} 小时")
    
    # 显示前10名
    sorted_results = sorted(results.items(), 
                          key=lambda x: x[1]['performance']['compound_return'], 
                          reverse=True)[:10]
    
    print(f"\n🏆 前10名最佳表现:")
    for i, (crypto, result) in enumerate(sorted_results, 1):
        perf = result['performance']
        print(f"  {i:2d}. {crypto:12s}: {perf['compound_return']:.3f}×, {perf['win_rate']:.1%}, {result['best_timing']:2d}小时")

if __name__ == "__main__":
    run_full_hourly_optimization()
