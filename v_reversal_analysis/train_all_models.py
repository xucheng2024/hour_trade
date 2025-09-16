#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
训练所有币种的V型反转模型
使用所有历史数据分别训练每个币种，并保存模型文件
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
sys.path.append('/Users/mac/Downloads/stocks/ex_okx')
from src.strategies.historical_data_loader import get_historical_data_loader
import pickle
import os
import warnings
warnings.filterwarnings('ignore')

class VReversalModelTrainer:
    """V型反转模型训练器"""
    
    def __init__(self):
        self.data_loader = get_historical_data_loader()
        self.models = {}
        self.training_results = {}
        
    def get_all_cryptos(self):
        """获取所有可用的币种列表"""
        # 从配置文件读取币种列表
        try:
            with open('/Users/mac/Downloads/stocks/ex_okx/src/config/cryptos_selected.json', 'r') as f:
                import json
                crypto_config = json.load(f)
                return crypto_config  # 直接返回列表
        except:
            # 如果配置文件不存在，使用默认列表
            return [
                'SOL-USDT', 'BTC-USDT', 'ETH-USDT', 'ADA-USDT', 'LINK-USDT', 'DOGE-USDT',
                'AVAX-USDT', 'UNI-USDT', 'NEAR-USDT', 'ALGO-USDT', 'ICP-USDT', 'FIL-USDT',
                'THETA-USDT', 'AAVE-USDT', 'COMP-USDT', 'MKR-USDT', '1INCH-USDT', 'CRV-USDT',
                'LRC-USDT', 'BAT-USDT', 'DOT-USDT', 'ATOM-USDT', 'SUSHI-USDT', 'SNX-USDT',
                'YFI-USDT', 'BAL-USDT', 'ZRX-USDT', 'MATIC-USDT', 'FTM-USDT', 'VET-USDT'
            ]
    
    def calculate_features(self, df):
        """计算技术特征"""
        # 基础价格特征
        df['price_change'] = df['close'] - df['open']
        df['price_change_pct'] = (df['price_change'] / df['open']) * 100
        df['high_low_spread'] = df['high'] - df['low']
        df['high_low_spread_pct'] = (df['high_low_spread'] / df['open']) * 100
        
        # 移动平均线特征
        for window in [3, 5, 10, 20, 50]:
            df[f'ma_{window}'] = df['close'].rolling(window=window).mean()
            df[f'ma_{window}_ratio'] = df['close'] / (df[f'ma_{window}'] + 1e-8)
        
        # 价格位置特征
        for window in [10, 20, 50]:
            df[f'high_{window}'] = df['high'].rolling(window=window).max()
            df[f'low_{window}'] = df['low'].rolling(window=window).min()
            df[f'price_position_{window}'] = (df['close'] - df[f'low_{window}']) / (df[f'high_{window}'] - df[f'low_{window}'] + 1e-8)
            df[f'decline_from_high_{window}'] = (df[f'high_{window}'] - df['close']) / df[f'high_{window}'] * 100
        
        # 波动率特征
        for window in [5, 10, 20]:
            df[f'volatility_{window}'] = df['close'].rolling(window=window).std()
            df[f'volatility_ratio_{window}'] = df[f'volatility_{window}'] / df[f'volatility_{window}'].rolling(window=20).mean()
        
        # 成交量特征
        df['volume_ma_10'] = df['volume'].rolling(window=10).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_ma_10'] + 1e-8)
        df['volume_price_trend'] = df['volume'] * df['price_change_pct']
        
        # 时间序列特征
        df['is_declining'] = df['close'] < df['close'].shift(1)
        df['is_rising'] = df['close'] > df['close'].shift(1)
        
        # 连续下跌/上涨计数
        df['decline_count'] = df['is_declining'].groupby((~df['is_declining']).cumsum()).cumsum()
        df['rise_count'] = df['is_rising'].groupby((~df['is_rising']).cumsum()).cumsum()
        
        # 下跌速度特征
        df['decline_speed'] = df['decline_from_high_20'] / (df['decline_count'] + 1)
        df['recovery_speed'] = df['price_change_pct'] / (df['rise_count'] + 1)
        
        # RSI特征
        df['rsi_14'] = self.calculate_rsi(df['close'], 14)
        df['rsi_oversold'] = (df['rsi_14'] < 30).astype(int)
        df['rsi_oversold_count'] = df['rsi_oversold'].groupby((~df['rsi_oversold']).cumsum()).cumsum()
        
        # 布林带特征
        df['bb_middle'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + (df['bb_std'] * 2)
        df['bb_lower'] = df['bb_middle'] - (df['bb_std'] * 2)
        df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'] + 1e-8)
        df['bb_squeeze'] = (df['bb_upper'] - df['bb_lower']) / df['bb_middle']
        
        # 计算未来收益（用于回测）
        for hours in [1, 2, 4, 8, 12, 24]:
            df[f'return_{hours}h'] = (df['close'].shift(-hours) / df['close'] - 1) * 100
        
        return df
    
    def calculate_rsi(self, prices, window=14):
        """计算RSI指标"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def train_single_crypto(self, crypto):
        """训练单个币种的模型"""
        print(f"\n📊 训练 {crypto}...")
        
        try:
            # 加载小时数据
            df = self.data_loader.get_dataframe_with_dates(crypto, 0, 0, '1H')
            if df is None or len(df) < 1000:
                print(f"❌ {crypto}: 数据不足 ({len(df) if df is not None else 0}小时)")
                return None
            
            # 计算特征
            df = self.calculate_features(df)
            
            # 使用所有历史数据训练
            train_data = df.dropna()
            
            if len(train_data) < 500:
                print(f"⚠️  {crypto}: 有效训练数据不足 ({len(train_data)}小时)")
                return None
            
            # 计算严格分位数阈值
            thresholds = self.calculate_strict_thresholds(train_data, crypto)
            
            if thresholds is None:
                print(f"⚠️  {crypto}: 无法计算阈值")
                return None
            
            # 创建模型
            model = {
                'crypto': crypto,
                'thresholds': thresholds,
                'training_data_size': len(train_data),
                'training_date': datetime.now().isoformat(),
                'features': {
                    'decline_95': thresholds['decline_95'],
                    'position_5': thresholds['position_5'],
                    'rsi_5': thresholds['rsi_5'],
                    'volume_95': thresholds['volume_95']
                }
            }
            
            # 在训练数据上测试模型效果
            test_results = self.test_model_on_data(train_data, thresholds, crypto)
            if test_results:
                model['training_performance'] = test_results
                
                # 检查中位数收益是否达到1%
                median_return = test_results.get('median_return_24h', 0)
                signal_count = test_results.get('signal_count', 0)
                
                if median_return < 1.0:
                    print(f"⚠️  {crypto}: 中位数收益{median_return:.2f}% < 1%，跳过")
                    return None
                
                # 检查信号数量是否达到10个
                if signal_count < 10:
                    print(f"⚠️  {crypto}: 信号数量{signal_count} < 10个，跳过")
                    return None
            
            print(f"✅ {crypto}: 模型训练完成")
            print(f"   训练数据: {len(train_data)}小时")
            print(f"   回撤95%阈值: {thresholds['decline_95']:.2f}%")
            print(f"   位置5%阈值: {thresholds['position_5']:.3f}")
            print(f"   RSI 5%阈值: {thresholds['rsi_5']:.1f}")
            print(f"   成交量95%阈值: {thresholds['volume_95']:.2f}")
            if test_results:
                print(f"   中位数收益: {test_results.get('median_return_24h', 0):.2f}%")
                print(f"   信号数量: {test_results.get('signal_count', 0)}")
            
            return model
            
        except Exception as e:
            print(f"❌ {crypto}: 训练失败 - {e}")
            return None
    
    def calculate_strict_thresholds(self, train_data, crypto):
        """计算严格分位数阈值"""
        if len(train_data) < 100:
            return None
        
        thresholds = {
            'decline_95': train_data['decline_from_high_20'].quantile(0.95),
            'position_5': train_data['price_position_20'].quantile(0.05),
            'rsi_5': train_data['rsi_14'].quantile(0.05),
            'volume_95': train_data['volume_ratio'].quantile(0.95),
        }
        
        return thresholds
    
    def test_model_on_data(self, data, thresholds, crypto):
        """在数据上测试模型效果"""
        # 应用严格阈值
        strict_mask = (
            (data['decline_from_high_20'] >= thresholds['decline_95']) &
            (data['price_position_20'] <= thresholds['position_5']) &
            (data['rsi_14'] <= thresholds['rsi_5']) &
            (data['volume_ratio'] >= thresholds['volume_95'])
        )
        
        signals = data[strict_mask]
        
        if len(signals) == 0:
            return None
        
        # 计算24小时收益
        returns_24h = signals['return_24h'].dropna()
        
        if len(returns_24h) == 0:
            return None
        
        performance = {
            'signal_count': len(signals),
            'median_return_24h': returns_24h.median(),  # 使用中位数
            'avg_return_24h': returns_24h.mean(),
            'win_rate_24h': (returns_24h > 0).mean(),
            'profitable_rate_24h': (returns_24h > 1.0).mean(),
            'max_return_24h': returns_24h.max(),
            'min_return_24h': returns_24h.min(),
            'std_return_24h': returns_24h.std()
        }
        
        return performance
    
    def train_all_models(self):
        """训练所有币种的模型"""
        print("🤖 V型反转模型训练器")
        print("=" * 80)
        print("使用所有历史数据分别训练每个币种")
        print("=" * 80)
        
        # 获取所有币种
        all_cryptos = self.get_all_cryptos()
        print(f"总币种数: {len(all_cryptos)}")
        
        successful_models = 0
        failed_models = 0
        
        for i, crypto in enumerate(all_cryptos, 1):
            print(f"\n[{i}/{len(all_cryptos)}] 处理 {crypto}...")
            
            model = self.train_single_crypto(crypto)
            
            if model:
                self.models[crypto] = model
                successful_models += 1
            else:
                failed_models += 1
        
        # 生成训练汇总
        print("\n" + "=" * 80)
        print("📋 模型训练汇总")
        print("=" * 80)
        print(f"总币种数: {len(all_cryptos)}")
        print(f"成功训练: {successful_models}")
        print(f"训练失败: {failed_models}")
        print(f"成功率: {successful_models/len(all_cryptos)*100:.1f}%")
        
        # 显示成功训练的模型
        if self.models:
            print(f"\n✅ 成功训练的模型 (中位数收益≥1% 且 信号数≥10个):")
            for crypto, model in self.models.items():
                perf = model.get('training_performance', {})
                print(f"  {crypto}: {perf.get('signal_count', 0)}个信号, "
                      f"中位数收益{perf.get('median_return_24h', 0):.2f}%, "
                      f"平均收益{perf.get('avg_return_24h', 0):.2f}%, "
                      f"胜率{perf.get('win_rate_24h', 0)*100:.0f}%")
        
        return successful_models > 0
    
    def save_models(self, filename='v_reversal_models.pkl'):
        """保存所有模型"""
        if not self.models:
            print("❌ 没有模型可保存")
            return False
        
        # 创建模型目录
        model_dir = 'v_reversal_analysis/models'
        os.makedirs(model_dir, exist_ok=True)
        
        # 保存所有模型到一个文件
        all_models_path = os.path.join(model_dir, filename)
        with open(all_models_path, 'wb') as f:
            pickle.dump(self.models, f)
        
        print(f"💾 所有模型已保存到: {all_models_path}")
        
        # 为每个币种单独保存模型
        for crypto, model in self.models.items():
            single_model_path = os.path.join(model_dir, f'{crypto}_model.pkl')
            with open(single_model_path, 'wb') as f:
                pickle.dump(model, f)
        
        print(f"💾 单独模型已保存到: {model_dir}/")
        
        return True
    
    def load_models(self, filename='v_reversal_models.pkl'):
        """加载所有模型"""
        model_path = f'v_reversal_analysis/models/{filename}'
        
        try:
            with open(model_path, 'rb') as f:
                self.models = pickle.load(f)
            
            print(f"📂 模型已从 {model_path} 加载")
            print(f"加载了 {len(self.models)} 个币种的模型")
            return True
        except FileNotFoundError:
            print(f"❌ 模型文件 {model_path} 不存在")
            return False
    
    def get_model_summary(self):
        """获取模型摘要"""
        if not self.models:
            return "没有可用的模型"
        
        summary = {
            'total_models': len(self.models),
            'cryptos': list(self.models.keys()),
            'total_signals': 0,
            'avg_performance': {}
        }
        
        for crypto, model in self.models.items():
            perf = model.get('training_performance', {})
            if perf:
                summary['total_signals'] += perf.get('signal_count', 0)
        
        return summary

def main():
    """主函数"""
    trainer = VReversalModelTrainer()
    
    # 训练所有模型
    if trainer.train_all_models():
        # 保存模型
        trainer.save_models()
        
        # 显示模型摘要
        summary = trainer.get_model_summary()
        print(f"\n📊 模型摘要:")
        print(f"总模型数: {summary['total_models']}")
        print(f"总信号数: {summary['total_signals']}")
        print(f"币种列表: {', '.join(summary['cryptos'])}")
        
        print(f"\n🎯 模型文件位置:")
        print(f"所有模型: v_reversal_analysis/models/v_reversal_models.pkl")
        print(f"单独模型: v_reversal_analysis/models/[币种名]_model.pkl")
        
        print(f"\n💡 使用方法:")
        print(f"1. 加载模型: trainer.load_models()")
        print(f"2. 获取模型: model = trainer.models['BTC-USDT']")
        print(f"3. 应用阈值: 检查是否满足严格异常条件")
        
    else:
        print("❌ 模型训练失败")

if __name__ == "__main__":
    main()
