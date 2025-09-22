#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Loader for V-shaped Reversal Research
V型反转研究数据加载器
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.strategies.historical_data_loader import get_historical_data_loader
from src.config.okx_config import get_config, get_crypto_list_file

logger = logging.getLogger(__name__)

class VReversalDataLoader:
    """V型反转研究专用数据加载器"""
    
    def __init__(self):
        """初始化数据加载器"""
        self.config = get_config()
        self.hist_loader = get_historical_data_loader()
        self.crypto_list = self._load_crypto_list()
        
        logger.info(f"✅ V-Reversal Data Loader initialized with {len(self.crypto_list)} cryptocurrencies")
    
    def _load_crypto_list(self) -> List[str]:
        """加载可用的加密货币列表"""
        try:
            crypto_file = get_crypto_list_file()
            with open(crypto_file, 'r') as f:
                cryptos = json.load(f)
            
            # 过滤有小时数据的币种
            available_cryptos = []
            data_dir = self.config.get_path('data_directory')
            
            for crypto in cryptos:
                hourly_file = os.path.join(data_dir, f"{crypto}_1H.npz")
                if os.path.exists(hourly_file):
                    available_cryptos.append(crypto)
            
            logger.info(f"Found hourly data for {len(available_cryptos)}/{len(cryptos)} cryptocurrencies")
            return available_cryptos
            
        except Exception as e:
            logger.error(f"Error loading crypto list: {e}")
            return []
    
    def load_hourly_data(self, symbol: str, months: int = 6) -> Optional[pd.DataFrame]:
        """
        加载单个币种的小时数据
        
        Args:
            symbol: 币种符号
            months: 加载几个月的数据
            
        Returns:
            标准化的DataFrame
        """
        try:
            # 使用现有基础设施加载数据
            data = self.hist_loader.get_hist_candle_data(symbol, bar="1H", return_dataframe=True)
            
            if data is None or len(data) == 0:
                logger.error(f"No data available for {symbol}")
                return None
            
            # 标准化数据格式
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(data['timestamp'], unit='ms'),
                'open': data['open'].astype(float),
                'high': data['high'].astype(float), 
                'low': data['low'].astype(float),
                'close': data['close'].astype(float),
                'volume': data['volume'].astype(float) if 'volume' in data else 0,
                'symbol': symbol
            })
            
            # 按时间排序
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # 过滤到指定月数
            if months < 12:  # 避免过度过滤
                cutoff_date = df['timestamp'].max() - timedelta(days=months * 30)
                df = df[df['timestamp'] >= cutoff_date]
            
            # 添加技术指标列供V型反转分析使用
            df = self._add_technical_indicators(df)
            
            logger.info(f"Loaded {len(df)} hourly records for {symbol} "
                       f"from {df['timestamp'].min()} to {df['timestamp'].max()}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading data for {symbol}: {e}")
            return None
    
    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """添加技术指标"""
        # 简单移动平均线
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        
        # 价格变化率
        df['price_change'] = df['close'].pct_change()
        df['price_change_abs'] = df['price_change'].abs()
        
        # 波动率 (20小时滚动标准差)
        df['volatility_20h'] = df['price_change'].rolling(window=20).std()
        
        # 高低点距离开盘价的比例
        df['high_pct'] = (df['high'] - df['open']) / df['open']
        df['low_pct'] = (df['low'] - df['open']) / df['open']
        
        # 实体大小 (开盘收盘差)
        df['body_pct'] = (df['close'] - df['open']) / df['open']
        
        # 上下影线长度
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
        df['upper_shadow_pct'] = df['upper_shadow'] / df['open']
        df['lower_shadow_pct'] = df['lower_shadow'] / df['open']
        
        return df
    
    def load_multiple_symbols(self, symbols: List[str] = None, months: int = 6) -> Dict[str, pd.DataFrame]:
        """
        加载多个币种的数据
        
        Args:
            symbols: 币种列表，None表示所有
            months: 加载几个月的数据
            
        Returns:
            符号到DataFrame的字典
        """
        if symbols is None:
            symbols = self.crypto_list[:10]  # 默认前10个币种
        
        data_dict = {}
        successful_loads = 0
        
        for symbol in symbols:
            logger.info(f"Loading data for {symbol}...")
            df = self.load_hourly_data(symbol, months)
            if df is not None and len(df) > 100:  # 至少100个小时的数据
                data_dict[symbol] = df
                successful_loads += 1
            else:
                logger.warning(f"Insufficient data for {symbol}")
        
        logger.info(f"✅ Successfully loaded data for {successful_loads}/{len(symbols)} symbols")
        return data_dict
    
    def get_available_symbols(self) -> List[str]:
        """获取可用币种列表"""
        return self.crypto_list.copy()


def load_sample_data() -> Dict[str, pd.DataFrame]:
    """加载样本数据进行测试"""
    loader = VReversalDataLoader()
    
    # 选择一些主要币种进行测试
    test_symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT', '1INCH-USDT', 'AAVE-USDT']
    available_symbols = loader.get_available_symbols()
    
    # 过滤到实际可用的币种
    symbols_to_load = [s for s in test_symbols if s in available_symbols][:3]
    
    return loader.load_multiple_symbols(symbols_to_load, months=3)


if __name__ == "__main__":
    # 测试数据加载
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Testing V-Reversal Data Loader")
    data = load_sample_data()
    
    print(f"📊 Loaded data for {len(data)} symbols:")
    for symbol, df in data.items():
        print(f"  {symbol}: {len(df)} records, {df['timestamp'].min()} to {df['timestamp'].max()}")

