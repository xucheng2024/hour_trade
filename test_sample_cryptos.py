#!/usr/bin/env python3
"""
测试几个代表性加密货币的最近3个月表现
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import os

def test_crypto_recent_performance(crypto, params):
    """测试单个加密货币的最近3个月表现"""
    print(f"\n📊 测试 {crypto}:")
    print(f"  参数: P={params['high_open_ratio_threshold']:.1%}, V={params['volume_ratio_threshold']:.1f}x")
    
    try:
        # 获取数据
        data_file = f"data/{crypto}_1D.npz"
        if not os.path.exists(data_file):
            print(f"  ❌ 数据文件不存在")
            return None
            
        data = np.load(data_file)
        raw_data = data['data']
        timestamps = pd.to_datetime(raw_data[:, 0].astype(int), unit='ms')
        
        # 计算时间范围
        end_date = timestamps.max()
        start_date = end_date - timedelta(days=90)
        mask = (timestamps >= start_date) & (timestamps <= end_date)
        recent_data = raw_data[mask]
        
        print(f"  数据时间范围: {start_date.strftime('%Y-%m-%d')} 至 {end_date.strftime('%Y-%m-%d')}")
        print(f"  数据点数量: {len(recent_data)}")
        
        # 转换数据
        df = pd.DataFrame({
            'timestamp': timestamps[mask],
            'open': recent_data[:, 1].astype(float),
            'high': recent_data[:, 2].astype(float),
            'low': recent_data[:, 3].astype(float),
            'close': recent_data[:, 4].astype(float),
            'volume': recent_data[:, 5].astype(float)
        })
        
        # 计算比率
        df['price_ratio'] = (df['high'] - df['open']) / df['open']
        df['volume_ratio'] = df['volume'] / df['volume'].shift(1)
        
        # 获取参数
        p = params['high_open_ratio_threshold']
        v = params['volume_ratio_threshold']
        
        # 交易信号
        buy_signals = (df['price_ratio'] >= p) & (df['volume_ratio'] >= v)
        
        print(f"  满足价格条件的天数: {(df['price_ratio'] >= p).sum()}")
        print(f"  满足成交量条件的天数: {(df['volume_ratio'] >= v).sum()}")
        print(f"  同时满足条件的天数: {buy_signals.sum()}")
        
        # 计算收益
        returns = []
        trade_details = []
        
        for idx in df[buy_signals].index:
            if idx < len(df) - 1:  # 确保不是最后一天
                buy_price = df.loc[idx, 'open']
                sell_price = df.loc[idx + 1, 'close']
                fee = 0.002  # 0.1% 买入 + 0.1% 卖出
                profit = (sell_price - buy_price) / buy_price - fee
                returns.append(profit)
                trade_details.append({
                    'date': df.loc[idx, 'timestamp'].strftime('%Y-%m-%d'),
                    'buy_price': buy_price,
                    'sell_price': sell_price,
                    'profit': profit
                })
        
        if returns:
            returns = np.array(returns)
            win_rate = (returns > 0).sum() / len(returns)
            compound_return = np.prod(1 + returns)
            median_return = np.median(returns)
            mean_return = np.mean(returns)
            
            print(f"  总交易次数: {len(returns)}")
            print(f"  胜率: {win_rate:.1%}")
            print(f"  复合收益: {compound_return:.6f}")
            print(f"  平均收益: {mean_return:.4f}")
            print(f"  中位数收益: {median_return:.4f}")
            
            print(f"  交易详情:")
            for i, trade in enumerate(trade_details, 1):
                print(f"    {i}. {trade['date']}: 买入={trade['buy_price']:.2f}, 卖出={trade['sell_price']:.2f}, 收益={trade['profit']:.4f}")
            
            return {
                'total_trades': len(returns),
                'win_rate': win_rate,
                'compound_return': compound_return,
                'median_return': median_return,
                'mean_return': mean_return,
                'trade_details': trade_details
            }
        else:
            print(f"  总交易次数: 0")
            print(f"  无交易记录")
            return {
                'total_trades': 0,
                'win_rate': 0,
                'compound_return': 0,
                'median_return': 0,
                'mean_return': 0,
                'trade_details': []
            }
            
    except Exception as e:
        print(f"  ❌ 测试失败: {e}")
        return None

def main():
    """主函数"""
    print("🚀 测试代表性加密货币的最近3个月表现")
    
    # 加载优化参数
    try:
        with open('crypto_trading_triggers.json', 'r') as f:
            config = json.load(f)
            optimized_params = config.get('triggers', {})
        print(f"✅ 加载了 {len(optimized_params)} 个加密货币的优化参数")
    except Exception as e:
        print(f"❌ 加载配置失败: {e}")
        return
    
    # 选择几个代表性的加密货币进行测试
    test_cryptos = [
        'BTC-USDT',   # 比特币
        'ETH-USDT',   # 以太坊
        'SOL-USDT',   # Solana
        'DOGE-USDT',  # 狗狗币
        'ADA-USDT',   # Cardano
        'AVAX-USDT',  # Avalanche
        'DOT-USDT',   # Polkadot
        'MATIC-USDT', # Polygon
        'LINK-USDT',  # Chainlink
        'UNI-USDT'    # Uniswap
    ]
    
    results = {}
    
    for crypto in test_cryptos:
        if crypto in optimized_params:
            result = test_crypto_recent_performance(crypto, optimized_params[crypto])
            if result:
                results[crypto] = result
    
    # 生成摘要
    print(f"\n📊 测试结果摘要")
    print(f"=" * 60)
    
    total_cryptos = len(results)
    cryptos_with_trades = sum(1 for r in results.values() if r['total_trades'] > 0)
    
    print(f"📈 总体统计:")
    print(f"  测试加密货币数量: {total_cryptos}")
    print(f"  有交易记录的币种: {cryptos_with_trades}")
    print(f"  无交易记录币种: {total_cryptos - cryptos_with_trades}")
    
    if cryptos_with_trades > 0:
        # 收益统计
        compound_returns = [r['compound_return'] for r in results.values() if r['total_trades'] > 0]
        win_rates = [r['win_rate'] for r in results.values() if r['total_trades'] > 0]
        total_trades = [r['total_trades'] for r in results.values() if r['total_trades'] > 0]
        
        print(f"\n💰 收益统计 (有交易的币种):")
        print(f"  复合收益 - 平均: {np.mean(compound_returns):.3f}, 中位数: {np.median(compound_returns):.3f}")
        print(f"  复合收益 - 最高: {np.max(compound_returns):.3f}, 最低: {np.min(compound_returns):.3f}")
        print(f"  胜率 - 平均: {np.mean(win_rates):.1%}, 中位数: {np.median(win_rates):.1%}")
        
        print(f"\n📊 交易统计:")
        print(f"  总交易次数: {sum(total_trades)}")
        print(f"  平均每币种交易次数: {np.mean(total_trades):.1f}")
        
        # 表现最佳的币种
        best_performers = sorted(results.items(), 
                               key=lambda x: x[1]['compound_return'], 
                               reverse=True)
        
        print(f"\n🏆 最近3个月表现排名:")
        for i, (crypto, result) in enumerate(best_performers, 1):
            if result['total_trades'] > 0:
                print(f"  {i:2d}. {crypto}: 复合收益={result['compound_return']:.3f}, 胜率={result['win_rate']:.1%}, 交易次数={result['total_trades']}")
            else:
                print(f"  {i:2d}. {crypto}: 无交易记录")
    
    print(f"\n✅ 测试完成!")

if __name__ == "__main__":
    main()
