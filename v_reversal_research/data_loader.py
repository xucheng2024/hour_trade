#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data Loader for V-shaped Reversal Research
V-shaped reversal research data loader
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
    """V-shaped reversal research dedicated data loader"""
    
    def __init__(self):
        """Initialize data loader"""
        self.config = get_config()
        self.hist_loader = get_historical_data_loader()
        self.crypto_list = self._load_crypto_list()
        
        logger.info(f"✅ V-Reversal Data Loader initialized with {len(self.crypto_list)} cryptocurrencies")
    
    def _load_crypto_list(self) -> List[str]:
        """Load available cryptocurrency list"""
        try:
            crypto_file = get_crypto_list_file()
            with open(crypto_file, 'r') as f:
                cryptos = json.load(f)
            
            # Filter cryptocurrencies with hourly data
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
        Load hourly data for a single cryptocurrency
        
        Args:
            symbol: Cryptocurrency symbol
            months: Number of months of data to load
            
        Returns:
            Standardized DataFrame
        """
        try:
            # Use existing infrastructure to load data
            data = self.hist_loader.get_hist_candle_data(symbol, bar="1H", return_dataframe=True)
            
            if data is None or len(data) == 0:
                logger.error(f"No data available for {symbol}")
                return None
            
            # Standardize data format
            df = pd.DataFrame({
                'timestamp': pd.to_datetime(data['timestamp'], unit='ms'),
                'open': data['open'].astype(float),
                'high': data['high'].astype(float), 
                'low': data['low'].astype(float),
                'close': data['close'].astype(float),
                'volume': data['volume'].astype(float) if 'volume' in data else 0,
                'symbol': symbol
            })
            
            # Sort by time
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Filter to specified number of months
            if months < 12:  # Avoid over-filtering
                cutoff_date = df['timestamp'].max() - timedelta(days=months * 30)
                df = df[df['timestamp'] >= cutoff_date]
            
            # Add technical indicator columns for V-shaped reversal analysis
            df = self._add_technical_indicators(df)
            
            logger.info(f"Loaded {len(df)} hourly records for {symbol} "
                       f"from {df['timestamp'].min()} to {df['timestamp'].max()}")
            
            return df
            
        except Exception as e:
            logger.error(f"Error loading data for {symbol}: {e}")
            return None
    
    def _add_technical_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add technical indicators"""
        # Simple moving averages
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_50'] = df['close'].rolling(window=50).mean()
        
        # Price change rate
        df['price_change'] = df['close'].pct_change()
        df['price_change_abs'] = df['price_change'].abs()
        
        # Volatility (20-hour rolling standard deviation)
        df['volatility_20h'] = df['price_change'].rolling(window=20).std()
        
        # High/low point distance from open price ratio
        df['high_pct'] = (df['high'] - df['open']) / df['open']
        df['low_pct'] = (df['low'] - df['open']) / df['open']
        
        # Body size (open-close difference)
        df['body_pct'] = (df['close'] - df['open']) / df['open']
        
        # Upper and lower shadow lengths
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
        df['upper_shadow_pct'] = df['upper_shadow'] / df['open']
        df['lower_shadow_pct'] = df['lower_shadow'] / df['open']
        
        return df
    
    def load_multiple_symbols(self, symbols: List[str] = None, months: int = 6) -> Dict[str, pd.DataFrame]:
        """
        Load data for multiple cryptocurrencies
        
        Args:
            symbols: Cryptocurrency list, None means all
            months: Number of months of data to load
            
        Returns:
            Dictionary of symbol to DataFrame
        """
        if symbols is None:
            symbols = self.crypto_list[:10]  # Default first 10 cryptocurrencies
        
        data_dict = {}
        successful_loads = 0
        
        for symbol in symbols:
            logger.info(f"Loading data for {symbol}...")
            df = self.load_hourly_data(symbol, months)
            if df is not None and len(df) > 100:  # At least 100 hours of data
                data_dict[symbol] = df
                successful_loads += 1
            else:
                logger.warning(f"Insufficient data for {symbol}")
        
        logger.info(f"✅ Successfully loaded data for {successful_loads}/{len(symbols)} symbols")
        return data_dict
    
    def get_available_symbols(self) -> List[str]:
        """Get available cryptocurrency list"""
        return self.crypto_list.copy()


def load_sample_data() -> Dict[str, pd.DataFrame]:
    """Load sample data for testing"""
    loader = VReversalDataLoader()
    
    # Select some main cryptocurrencies for testing
    test_symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT', '1INCH-USDT', 'AAVE-USDT']
    available_symbols = loader.get_available_symbols()
    
    # Filter to actually available cryptocurrencies
    symbols_to_load = [s for s in test_symbols if s in available_symbols][:3]
    
    return loader.load_multiple_symbols(symbols_to_load, months=3)


if __name__ == "__main__":
    # Test data loading
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Testing V-Reversal Data Loader")
    data = load_sample_data()
    
    print(f"📊 Loaded data for {len(data)} symbols:")
    for symbol, df in data.items():
        print(f"  {symbol}: {len(df)} records, {df['timestamp'].min()} to {df['timestamp'].max()}")

