#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V型反转实时交易脚本
使用训练好的模型进行实时交易
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
sys.path.append('/Users/mac/Downloads/stocks/ex_okx')
from src.strategies.historical_data_loader import get_historical_data_loader
import pickle
import time
import warnings
warnings.filterwarnings('ignore')

class LiveTradingBot:
    """实时交易机器人"""
    
    def __init__(self):
        self.data_loader = get_historical_data_loader()
        self.models = {}
        self.positions = {}
        self.trade_history = []
        self.is_running = False
        
    def load_models(self, model_file='v_reversal_analysis/models/v_reversal_models.pkl'):
        """加载训练好的模型"""
        try:
            with open(model_file, 'rb') as f:
                self.models = pickle.load(f)
            
            print(f"✅ 成功加载 {len(self.models)} 个币种的模型")
            for crypto, model in self.models.items():
                print(f"  {crypto}: 回撤阈值{model['thresholds']['decline_95']:.2f}%, "
                      f"位置阈值{model['thresholds']['position_5']:.3f}, "
                      f"RSI阈值{model['thresholds']['rsi_5']:.1f}, "
                      f"成交量阈值{model['thresholds']['volume_95']:.2f}")
            return True
        except Exception as e:
            print(f"❌ 加载模型失败: {e}")
            return False
    
    def calculate_features(self, df):
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
        df['rsi_14'] = self.calculate_rsi(df['close'], 14)
        
        return df
    
    def calculate_rsi(self, prices, window=14):
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def check_signal(self, crypto):
        """检查单个币种的交易信号"""
        if crypto not in self.models:
            return None
        
        try:
            # 获取最新数据
            df = self.data_loader.get_dataframe_with_dates(crypto, 0, 0, '1H')
            if df is None or len(df) < 100:
                return None
            
            # 计算特征
            df = self.calculate_features(df)
            
            # 获取最新数据点
            latest_data = df.tail(1).iloc[0]
            
            # 检查是否满足严格异常条件
            thresholds = self.models[crypto]['thresholds']
            
            is_signal = (
                latest_data['decline_from_high_20'] >= thresholds['decline_95'] and
                latest_data['price_position_20'] <= thresholds['position_5'] and
                latest_data['rsi_14'] <= thresholds['rsi_5'] and
                latest_data['volume_ratio'] >= thresholds['volume_95']
            )
            
            if is_signal:
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
                return signal
            
            return None
            
        except Exception as e:
            print(f"❌ {crypto}: 信号检查失败 - {e}")
            return None
    
    def scan_all_signals(self):
        """扫描所有币种的交易信号"""
        signals = []
        
        for crypto in self.models.keys():
            signal = self.check_signal(crypto)
            if signal:
                signals.append(signal)
        
        return signals
    
    def execute_trade(self, signal, position_size=0.05, stop_loss=-0.02, take_profit=0.05):
        """执行交易"""
        if signal['crypto'] in self.positions:
            print(f"⚠️  {signal['crypto']}: 已有持仓，跳过")
            return None
        
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
                    self.close_position(crypto, current_price, 'STOP_LOSS', current_return)
                    closed_trades.append(crypto)
                
                # 检查止盈
                elif current_return >= position['take_profit']:
                    self.close_position(crypto, current_price, 'TAKE_PROFIT', current_return)
                    closed_trades.append(crypto)
                
                # 检查时间止损（24小时）
                elif (datetime.now() - position['entry_time']).total_seconds() > 24 * 3600:
                    self.close_position(crypto, current_price, 'TIME_STOP', current_return)
                    closed_trades.append(crypto)
                
            except Exception as e:
                print(f"❌ {crypto}: 持仓监控失败 - {e}")
        
        return closed_trades
    
    def close_position(self, crypto, exit_price, reason, return_pct):
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
    
    def run_live_trading(self, scan_interval=3600, position_size=0.05, stop_loss=-0.02, take_profit=0.05):
        """运行实时交易"""
        print("🤖 启动V型反转实时交易机器人")
        print("=" * 60)
        print(f"扫描间隔: {scan_interval}秒")
        print(f"仓位大小: {position_size*100:.1f}%")
        print(f"止损位: {stop_loss*100:.1f}%")
        print(f"止盈位: {take_profit*100:.1f}%")
        print("=" * 60)
        
        self.is_running = True
        
        try:
            while self.is_running:
                print(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 扫描交易信号...")
                
                # 扫描信号
                signals = self.scan_all_signals()
                
                if signals:
                    print(f"发现 {len(signals)} 个交易信号:")
                    for signal in signals:
                        print(f"  {signal['crypto']}: {signal['price']:.4f}")
                        
                        # 执行交易
                        self.execute_trade(signal, position_size, stop_loss, take_profit)
                else:
                    print("当前无交易信号")
                
                # 监控持仓
                closed_trades = self.monitor_positions()
                if closed_trades:
                    print(f"平仓: {', '.join(closed_trades)}")
                
                # 显示性能
                if self.trade_history:
                    self.print_performance()
                
                # 等待下次扫描
                print(f"等待 {scan_interval} 秒...")
                time.sleep(scan_interval)
                
        except KeyboardInterrupt:
            print("\n⏹️  用户停止交易机器人")
        except Exception as e:
            print(f"\n❌ 交易机器人错误: {e}")
        finally:
            self.is_running = False
            print("🔚 交易机器人已停止")

def main():
    """主函数"""
    bot = LiveTradingBot()
    
    # 加载模型
    if not bot.load_models():
        print("❌ 无法加载模型，退出")
        return
    
    # 运行实时交易
    bot.run_live_trading(
        scan_interval=3600,  # 1小时扫描一次
        position_size=0.05,  # 5%仓位
        stop_loss=-0.02,     # 2%止损
        take_profit=0.05     # 5%止盈
    )

if __name__ == "__main__":
    main()
