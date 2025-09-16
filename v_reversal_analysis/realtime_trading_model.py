#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V型反转实时交易模型
基于严格分位数异常检测的实时交易系统
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
sys.path.append('/Users/mac/Downloads/stocks/ex_okx')
from src.strategies.historical_data_loader import get_historical_data_loader
import warnings
warnings.filterwarnings('ignore')

class VReversalTradingModel:
    """V型反转实时交易模型"""
    
    def __init__(self):
        self.data_loader = get_historical_data_loader()
        self.thresholds = {}  # 存储各币种的阈值
        self.positions = {}   # 存储当前持仓
        self.trade_history = []  # 交易历史
        
    def train_model(self, crypto_list, training_days=90):
        """训练模型 - 计算各币种的分位数阈值"""
        print("🤖 训练V型反转交易模型...")
        print(f"训练币种: {len(crypto_list)}个")
        print(f"训练数据: 最近{training_days}天之前的所有历史数据")
        
        for crypto in crypto_list:
            try:
                # 加载历史数据
                df = self.data_loader.get_dataframe_with_dates(crypto, 0, 0, '1H')
                if df is None or len(df) < 1000:
                    print(f"❌ {crypto}: 数据不足，跳过")
                    continue
                
                # 计算特征
                df = self._calculate_features(df)
                
                # 分割训练数据
                cutoff_date = datetime.now() - timedelta(days=training_days)
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                cutoff_timestamp = int(cutoff_date.timestamp() * 1000)
                train_data = df[df['timestamp'] < cutoff_timestamp]
                
                if len(train_data) < 500:
                    print(f"⚠️  {crypto}: 训练数据不足")
                    continue
                
                # 计算严格分位数阈值
                thresholds = self._calculate_strict_thresholds(train_data, crypto)
                if thresholds:
                    self.thresholds[crypto] = thresholds
                    print(f"✅ {crypto}: 阈值计算完成")
                
            except Exception as e:
                print(f"❌ {crypto}: 训练失败 - {e}")
        
        print(f"\n🎯 模型训练完成，成功训练 {len(self.thresholds)} 个币种")
        return len(self.thresholds) > 0
    
    def _calculate_features(self, df):
        """计算技术特征"""
        # 基础价格特征
        df['price_change'] = df['close'] - df['open']
        df['price_change_pct'] = (df['price_change'] / df['open']) * 100
        
        # 价格位置特征
        for window in [10, 20, 50]:
            df[f'high_{window}'] = df['high'].rolling(window=window).max()
            df[f'low_{window}'] = df['low'].rolling(window=window).min()
            df[f'price_position_{window}'] = (df['close'] - df[f'low_{window}']) / (df[f'high_{window}'] - df[f'low_{window}'] + 1e-8)
            df[f'decline_from_high_{window}'] = (df[f'high_{window}'] - df['close']) / df[f'high_{window}'] * 100
        
        # 成交量特征
        df['volume_ma_10'] = df['volume'].rolling(window=10).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_ma_10'] + 1e-8)
        
        # RSI特征
        df['rsi_14'] = self._calculate_rsi(df['close'], 14)
        
        return df
    
    def _calculate_rsi(self, prices, window=14):
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_strict_thresholds(self, train_data, crypto):
        """计算严格分位数阈值"""
        valid_train = train_data.dropna()
        if len(valid_train) < 100:
            return None
        
        thresholds = {
            'decline_95': valid_train['decline_from_high_20'].quantile(0.95),
            'position_5': valid_train['price_position_20'].quantile(0.05),
            'rsi_5': valid_train['rsi_14'].quantile(0.05),
            'volume_95': valid_train['volume_ratio'].quantile(0.95),
        }
        
        return thresholds
    
    def scan_signals(self, crypto_list):
        """扫描交易信号"""
        signals = []
        
        for crypto in crypto_list:
            if crypto not in self.thresholds:
                continue
            
            try:
                # 获取最新数据
                df = self.data_loader.get_dataframe_with_dates(crypto, 0, 0, '1H')
                if df is None or len(df) < 100:
                    continue
                
                # 计算特征
                df = self._calculate_features(df)
                
                # 获取最新数据点
                latest_data = df.tail(1).iloc[0]
                
                # 检查是否满足严格异常条件
                if self._check_strict_anomaly(latest_data, crypto):
                    signal = {
                        'crypto': crypto,
                        'timestamp': latest_data['timestamp'],
                        'price': latest_data['close'],
                        'decline_from_high_20': latest_data['decline_from_high_20'],
                        'price_position_20': latest_data['price_position_20'],
                        'rsi_14': latest_data['rsi_14'],
                        'volume_ratio': latest_data['volume_ratio'],
                        'signal_time': datetime.now()
                    }
                    signals.append(signal)
                    
            except Exception as e:
                print(f"❌ {crypto}: 信号扫描失败 - {e}")
        
        return signals
    
    def _check_strict_anomaly(self, data, crypto):
        """检查是否满足严格异常条件"""
        thresholds = self.thresholds[crypto]
        
        return (
            data['decline_from_high_20'] >= thresholds['decline_95'] and
            data['price_position_20'] <= thresholds['position_5'] and
            data['rsi_14'] <= thresholds['rsi_5'] and
            data['volume_ratio'] >= thresholds['volume_95']
        )
    
    def execute_trade(self, signal, position_size=0.05, stop_loss=-0.02, take_profit=0.05):
        """执行交易"""
        trade = {
            'crypto': signal['crypto'],
            'entry_price': signal['price'],
            'entry_time': signal['signal_time'],
            'position_size': position_size,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'status': 'OPEN'
        }
        
        self.positions[signal['crypto']] = trade
        self.trade_history.append(trade.copy())
        
        print(f"🚀 开仓信号: {signal['crypto']}")
        print(f"   价格: {signal['price']:.4f}")
        print(f"   回撤: {signal['decline_from_high_20']:.2f}%")
        print(f"   位置: {signal['price_position_20']:.3f}")
        print(f"   RSI: {signal['rsi_14']:.1f}")
        print(f"   成交量比: {signal['volume_ratio']:.2f}")
        print(f"   仓位大小: {position_size*100:.1f}%")
        print(f"   止损位: {stop_loss*100:.1f}%")
        print(f"   止盈位: {take_profit*100:.1f}%")
        
        return trade
    
    def monitor_positions(self):
        """监控持仓"""
        closed_trades = []
        
        for crypto, position in self.positions.items():
            if position['status'] != 'OPEN':
                continue
            
            try:
                # 获取最新价格
                df = self.data_loader.get_dataframe_with_dates(crypto, 0, 0, '1H')
                if df is None or len(df) < 1:
                    continue
                
                current_price = df['close'].iloc[-1]
                entry_price = position['entry_price']
                
                # 计算当前收益
                current_return = (current_price - entry_price) / entry_price
                
                # 检查止损
                if current_return <= position['stop_loss']:
                    self._close_position(crypto, current_price, 'STOP_LOSS', current_return)
                    closed_trades.append(crypto)
                
                # 检查止盈
                elif current_return >= position['take_profit']:
                    self._close_position(crypto, current_price, 'TAKE_PROFIT', current_return)
                    closed_trades.append(crypto)
                
                # 检查时间止损（24小时）
                elif (datetime.now() - position['entry_time']).total_seconds() > 24 * 3600:
                    self._close_position(crypto, current_price, 'TIME_STOP', current_return)
                    closed_trades.append(crypto)
                
            except Exception as e:
                print(f"❌ {crypto}: 持仓监控失败 - {e}")
        
        return closed_trades
    
    def _close_position(self, crypto, exit_price, reason, return_pct):
        """平仓"""
        if crypto not in self.positions:
            return
        
        position = self.positions[crypto]
        position['exit_price'] = exit_price
        position['exit_time'] = datetime.now()
        position['return_pct'] = return_pct * 100
        position['reason'] = reason
        position['status'] = 'CLOSED'
        
        print(f"🔚 平仓信号: {crypto}")
        print(f"   平仓价格: {exit_price:.4f}")
        print(f"   收益: {return_pct*100:.2f}%")
        print(f"   平仓原因: {reason}")
        
        # 从持仓中移除
        del self.positions[crypto]
    
    def get_performance_summary(self):
        """获取性能摘要"""
        if not self.trade_history:
            return "暂无交易记录"
        
        closed_trades = [t for t in self.trade_history if t['status'] == 'CLOSED']
        open_trades = [t for t in self.trade_history if t['status'] == 'OPEN']
        
        if not closed_trades:
            return f"总交易数: {len(self.trade_history)}, 持仓中: {len(open_trades)}"
        
        returns = [t['return_pct'] for t in closed_trades]
        
        # 计算复利收益
        compound_return = 1.0
        for ret in returns:
            compound_return *= (1 + ret/100)
        compound_return_pct = (compound_return - 1) * 100
        
        summary = {
            'total_trades': len(self.trade_history),
            'closed_trades': len(closed_trades),
            'open_trades': len(open_trades),
            'avg_return': np.mean(returns),
            'win_rate': len([r for r in returns if r > 0]) / len(returns) * 100,
            'compound_return': compound_return_pct,
            'max_return': max(returns),
            'min_return': min(returns)
        }
        
        return summary
    
    def print_performance(self):
        """打印性能报告"""
        summary = self.get_performance_summary()
        
        if isinstance(summary, str):
            print(summary)
            return
        
        print("\n📊 交易性能报告")
        print("=" * 50)
        print(f"总交易数: {summary['total_trades']}")
        print(f"已平仓: {summary['closed_trades']}")
        print(f"持仓中: {summary['open_trades']}")
        print(f"平均收益: {summary['avg_return']:.2f}%")
        print(f"胜率: {summary['win_rate']:.1f}%")
        print(f"复利收益: {summary['compound_return']:.2f}%")
        print(f"最大收益: {summary['max_return']:.2f}%")
        print(f"最小收益: {summary['min_return']:.2f}%")
    
    def save_model(self, filename='v_reversal_model.pkl'):
        """保存模型"""
        import pickle
        
        model_data = {
            'thresholds': self.thresholds,
            'trade_history': self.trade_history,
            'positions': self.positions
        }
        
        with open(filename, 'wb') as f:
            pickle.dump(model_data, f)
        
        print(f"💾 模型已保存到: {filename}")
    
    def load_model(self, filename='v_reversal_model.pkl'):
        """加载模型"""
        import pickle
        
        try:
            with open(filename, 'rb') as f:
                model_data = pickle.load(f)
            
            self.thresholds = model_data['thresholds']
            self.trade_history = model_data['trade_history']
            self.positions = model_data['positions']
            
            print(f"📂 模型已从 {filename} 加载")
            return True
        except FileNotFoundError:
            print(f"❌ 模型文件 {filename} 不存在")
            return False

def main():
    """主函数 - 演示如何使用模型"""
    print("🤖 V型反转实时交易模型")
    print("=" * 50)
    
    # 创建模型实例
    model = VReversalTradingModel()
    
    # 选择交易币种
    crypto_list = [
        'SOL-USDT', 'BTC-USDT', 'ETH-USDT', 'ADA-USDT', 'LINK-USDT', 'DOGE-USDT',
        'AVAX-USDT', 'UNI-USDT', 'NEAR-USDT', 'ALGO-USDT', 'ICP-USDT', 'FIL-USDT',
        'THETA-USDT', 'AAVE-USDT', 'COMP-USDT', 'MKR-USDT', '1INCH-USDT', 'CRV-USDT',
        'LRC-USDT', 'BAT-USDT'
    ]
    
    # 训练模型
    if model.train_model(crypto_list):
        print("\n✅ 模型训练成功")
        
        # 扫描信号
        print("\n🔍 扫描交易信号...")
        signals = model.scan_signals(crypto_list)
        
        if signals:
            print(f"发现 {len(signals)} 个交易信号:")
            for signal in signals:
                print(f"  {signal['crypto']}: {signal['price']:.4f}")
        else:
            print("当前无交易信号")
        
        # 保存模型
        model.save_model()
        
        # 显示性能
        model.print_performance()
        
    else:
        print("❌ 模型训练失败")

if __name__ == "__main__":
    main()
