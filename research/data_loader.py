#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cryptocurrency Data Loader for Research
Integrates with existing OKX data infrastructure to load hourly data for optimization
"""

import os
import json
import logging
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta

# Import existing data infrastructure
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from src.strategies.historical_data_loader import get_historical_data_loader
from src.config.okx_config import get_config, get_crypto_list_file

# Configure logging
logger = logging.getLogger(__name__)

class CryptoDataLoader:
    """
    Data loader that integrates with existing OKX data infrastructure
    Loads hourly cryptocurrency data for optimization research
    """
    
    def __init__(self):
        """Initialize the data loader with existing infrastructure"""
        self.config = get_config()
        self.hist_loader = get_historical_data_loader()
        self.crypto_list = self._load_crypto_list()
        
        logger.info(f"✅ Data loader initialized with {len(self.crypto_list)} cryptocurrencies")
    
    def _load_crypto_list(self) -> List[str]:
        """Load cryptocurrency list from existing configuration"""
        try:
            crypto_file = get_crypto_list_file()
            with open(crypto_file, 'r') as f:
                cryptos = json.load(f)
            
            # Filter to only include cryptos with available hourly data
            available_cryptos = []
            data_dir = self.config.get_path('data_directory')
            
            for crypto in cryptos:
                hourly_file = os.path.join(data_dir, f"{crypto}_1H.npz")
                if os.path.exists(hourly_file):
                    available_cryptos.append(crypto)
                else:
                    logger.warning(f"Hourly data not found for {crypto}")
            
            logger.info(f"Found hourly data for {len(available_cryptos)}/{len(cryptos)} cryptocurrencies")
            return available_cryptos
            
        except Exception as e:
            logger.error(f"Error loading crypto list: {e}")
            return []
    
    def load_hourly_data(self, symbol: str, months: int = 3) -> Optional[pd.DataFrame]:
        """
        Load hourly data for a specific cryptocurrency
        
        Args:
            symbol: Cryptocurrency symbol (e.g., 'BTC-USDT')
            months: Number of months of historical data to load
            
        Returns:
            DataFrame with columns: ['timestamp', 'open', 'high', 'low', 'close', 'symbol']
        """
        try:
            # Load data using existing infrastructure
            df = self.hist_loader.get_latest_three_months_data(symbol, bar="1H", return_dataframe=True)
            
            if df is None or len(df) == 0:
                logger.error(f"No data available for {symbol}")
                return None
            
            # Standardize column names for optimization system
            standardized_df = pd.DataFrame({
                'timestamp': pd.to_datetime(df['timestamp'], unit='ms'),
                'open': df['open'].astype(float),
                'high': df['high'].astype(float), 
                'low': df['low'].astype(float),
                'close': df['close'].astype(float),
                'symbol': symbol
            })
            
            # Sort by timestamp
            standardized_df = standardized_df.sort_values('timestamp').reset_index(drop=True)
            
            # Filter to requested number of months
            if months < 3:
                cutoff_date = standardized_df['timestamp'].max() - timedelta(days=months * 30)
                standardized_df = standardized_df[standardized_df['timestamp'] >= cutoff_date]
            
            logger.info(f"Loaded {len(standardized_df)} hourly records for {symbol} "
                       f"from {standardized_df['timestamp'].min()} to {standardized_df['timestamp'].max()}")
            
            return standardized_df
            
        except Exception as e:
            logger.error(f"Error loading data for {symbol}: {e}")
            return None
    
    def load_all_data(self, months: int = 3, limit: Optional[int] = None) -> pd.DataFrame:
        """
        Load hourly data for all available cryptocurrencies
        
        Args:
            months: Number of months of historical data to load
            limit: Optional limit on number of cryptocurrencies to load (for testing)
            
        Returns:
            Combined DataFrame with all cryptocurrency data
        """
        logger.info(f"🔄 Loading {months} months of hourly data for all cryptocurrencies...")
        
        all_data = []
        crypto_list = self.crypto_list[:limit] if limit else self.crypto_list
        
        successful_loads = 0
        for i, symbol in enumerate(crypto_list):
            logger.info(f"Loading data for {symbol} ({i+1}/{len(crypto_list)})")
            
            df = self.load_hourly_data(symbol, months)
            if df is not None and len(df) > 0:
                all_data.append(df)
                successful_loads += 1
            else:
                logger.warning(f"Failed to load data for {symbol}")
        
        if not all_data:
            logger.error("No data loaded for any cryptocurrency")
            return pd.DataFrame()
        
        # Combine all data
        combined_df = pd.concat(all_data, ignore_index=True)
        combined_df = combined_df.sort_values(['symbol', 'timestamp']).reset_index(drop=True)
        
        logger.info(f"✅ Successfully loaded data for {successful_loads}/{len(crypto_list)} cryptocurrencies")
        logger.info(f"Total records: {len(combined_df)}, Date range: {combined_df['timestamp'].min()} to {combined_df['timestamp'].max()}")
        
        return combined_df
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available cryptocurrency symbols"""
        return self.crypto_list.copy()
    
    def validate_data_quality(self, df: pd.DataFrame) -> Dict[str, any]:
        """
        Validate data quality and return statistics
        
        Args:
            df: DataFrame to validate
            
        Returns:
            Dictionary with validation results
        """
        if df.empty:
            return {"valid": False, "error": "Empty DataFrame"}
        
        try:
            validation = {
                "valid": True,
                "total_records": len(df),
                "symbols": df['symbol'].nunique(),
                "date_range": {
                    "start": df['timestamp'].min(),
                    "end": df['timestamp'].max()
                },
                "missing_values": df.isnull().sum().to_dict(),
                "price_anomalies": {
                    "negative_prices": (df[['open', 'high', 'low', 'close']] <= 0).sum().sum(),
                    "invalid_ohlc": ((df['high'] < df['low']) | 
                                   (df['high'] < df['open']) | 
                                   (df['high'] < df['close']) |
                                   (df['low'] > df['open']) | 
                                   (df['low'] > df['close'])).sum()
                },
                "symbols_with_data": df.groupby('symbol').size().to_dict()
            }
            
            # Check for critical issues
            if validation["missing_values"]["timestamp"] > 0:
                validation["valid"] = False
                validation["error"] = "Missing timestamp values"
            elif validation["price_anomalies"]["negative_prices"] > 0:
                validation["valid"] = False
                validation["error"] = "Negative price values found"
            elif validation["price_anomalies"]["invalid_ohlc"] > 0:
                validation["valid"] = False
                validation["error"] = "Invalid OHLC relationships found"
            
            return validation
            
        except Exception as e:
            return {"valid": False, "error": f"Validation error: {e}"}


def load_sample_data_for_testing() -> pd.DataFrame:
    """Load a small sample of data for testing purposes"""
    loader = CryptoDataLoader()
    
    # Load data for just a few major cryptocurrencies
    test_symbols = ['BTC-USDT', 'ETH-USDT', 'BNB-USDT']
    available_symbols = loader.get_available_symbols()
    
    test_data = []
    for symbol in test_symbols:
        if symbol in available_symbols:
            df = loader.load_hourly_data(symbol, months=1)  # Just 1 month for testing
            if df is not None:
                test_data.append(df)
    
    if test_data:
        return pd.concat(test_data, ignore_index=True)
    else:
        logger.error("No test data available")
        return pd.DataFrame()
