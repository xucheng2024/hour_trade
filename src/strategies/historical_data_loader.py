#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Historical Data Loader for OKX Trading Strategies
Handle historical data loading, preprocessing, and configuration management
"""

import json
import logging
from typing import Optional, Dict, Any, Tuple
import numpy as np
import pandas as pd
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger(__name__)

class HistoricalDataLoader:
    """Historical data loader with data preprocessing and type handling"""
    
    def __init__(self):
        self.config = self._load_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """Load configuration file"""
        import os
        # Get the directory where this file is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up to the project root
        project_root = os.path.dirname(os.path.dirname(current_dir))
        config_path = os.path.join(project_root, 'trading_config.json')
        
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}")
            return {}
    
    def _preprocess_data(self, raw_data: np.ndarray, instId: str) -> Tuple[Optional[np.ndarray], Optional[pd.DataFrame]]:
        """
        Preprocess raw data with proper type conversion and validation
        Returns: (processed_numpy_array, processed_dataframe)
        """
        try:
            # Skip the first data point to avoid initial data anomalies
            if len(raw_data) > 1:
                raw_data = raw_data[1:]
                logger.info(f"Skipped first data point for {instId} to avoid initial anomalies")
            
            # OKX API columns: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
            expected_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm']
            
            if raw_data.shape[1] != 9:
                logger.error(f"Invalid data structure for {instId}: expected 9 columns, got {raw_data.shape[1]}")
                return None, None
            
            # Create DataFrame for easier processing
            df = pd.DataFrame(raw_data, columns=expected_columns)
            
            # Convert timestamp to numeric first, then to datetime
            df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['date'] = df['datetime'].dt.date
            df['time'] = df['datetime'].dt.time
            
            # Convert numeric columns with proper type handling
            numeric_columns = ['open', 'high', 'low', 'close', 'volume', 'volCcy', 'volCcyQuote', 'confirm']
            
            for col in numeric_columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Remove rows with NaN values
            initial_rows = len(df)
            df = df.dropna()
            if len(df) < initial_rows:
                logger.warning(f"Removed {initial_rows - len(df)} rows with NaN values for {instId}")
            
            # Data validation
            if len(df) == 0:
                logger.error(f"No valid data remaining after preprocessing for {instId}")
                return None, None
            
            # Price validation
            price_columns = ['open', 'high', 'low', 'close']
            for col in price_columns:
                # Check for negative or extremely high prices
                invalid_prices = df[col] <= 0
                if invalid_prices.any():
                    logger.warning(f"Found {invalid_prices.sum()} invalid prices in {col} column for {instId}")
                    df = df[~invalid_prices]
                
                # Check for unreasonably high prices (> 1e10)
                extreme_prices = df[col] > 1e10
                if extreme_prices.any():
                    logger.warning(f"Found {extreme_prices.sum()} extreme prices in {col} column for {instId}")
                    df = df[~extreme_prices]
            
            # Volume validation
            volume_columns = ['volume', 'volCcy', 'volCcyQuote']
            for col in volume_columns:
                # Check for negative volumes
                invalid_volumes = df[col] < 0
                if invalid_volumes.any():
                    logger.warning(f"Found {invalid_volumes.sum()} negative volumes in {col} column for {instId}")
                    df = df[~invalid_volumes]
            
            # Price relationship validation
            invalid_high_low = df['high'] < df['low']
            invalid_high_open = df['high'] < df['open']
            invalid_high_close = df['high'] < df['close']
            invalid_low_open = df['low'] > df['open']
            invalid_low_close = df['low'] > df['close']
            
            invalid_rows = (invalid_high_low | invalid_high_open | invalid_high_close | 
                          invalid_low_open | invalid_low_close)
            
            if invalid_rows.any():
                logger.warning(f"Found {invalid_rows.sum()} rows with invalid price relationships for {instId}")
                df = df[~invalid_rows]
            
            # Sort by timestamp
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Convert back to numpy array for compatibility
            numpy_data = df[expected_columns].values
            
            # Add additional processed columns
            df['price_change'] = df['close'] - df['open']
            df['price_change_pct'] = (df['price_change'] / df['open']) * 100
            df['high_low_spread'] = df['high'] - df['low']
            df['body_size'] = abs(df['close'] - df['open'])
            
            logger.info(f"Successfully preprocessed data for {instId}: {len(df)} rows, {len(df.columns)} columns")
            
            return numpy_data, df
            
        except Exception as e:
            logger.error(f"Error preprocessing data for {instId}: {e}")
            return None, None
    
    def get_hist_candle_data(self, instId: str, start: int = 0, end: int = 0, bar: str = "1m", 
                            return_dataframe: bool = False) -> Optional[np.ndarray]:
        """
        Get historical candlestick data with preprocessing
        Args:
            instId: Instrument ID
            start: Start timestamp (ms)
            end: End timestamp (ms)
            bar: Timeframe
            return_dataframe: If True, return processed DataFrame instead of numpy array
        """
        import os
        # Get the directory where this file is located
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Go up to the project root
        project_root = os.path.dirname(os.path.dirname(current_dir))
        path = os.path.join(project_root, 'data')
        file = f"{instId}_{bar}.npz"
        
        try:
            data = np.load(os.path.join(path, file))
            name = data.files[0]
            raw_candles = data[name]
            
            # Preprocess the data
            processed_candles, processed_df = self._preprocess_data(raw_candles, instId)
            
            if processed_candles is None:
                return None
            
            # If start=0 and end=0, return all data
            if start == 0 and end == 0:
                return processed_df if return_dataframe else processed_candles
            
            # Filter by date range
            if return_dataframe:
                mask = (processed_df['timestamp'] >= start) & (processed_df['timestamp'] <= end)
                return processed_df[mask]
            else:
                date = processed_candles[:, 0].astype(np.int64)
                mask = (date >= start) & (date <= end)
                return processed_candles[mask]
                
        except Exception as e:
            logger.error(f"Error loading data for {instId}: {e}")
            return None
    
    def get_dataframe_with_dates(self, instId: str, start: int = 0, end: int = 0, bar: str = "1m") -> Optional[pd.DataFrame]:
        """
        Get historical data as DataFrame with proper date columns
        """
        return self.get_hist_candle_data(instId, start, end, bar, return_dataframe=True)
    
    def convert_timestamp_to_date(self, timestamp_ms: int) -> str:
        """Convert millisecond timestamp to readable date string"""
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
        except Exception as e:
            logger.error(f"Error converting timestamp {timestamp_ms}: {e}")
            return str(timestamp_ms)
    
    def get_data_summary(self, instId: str, bar: str = "1m") -> Optional[Dict[str, Any]]:
        """Get summary statistics for the data"""
        df = self.get_dataframe_with_dates(instId, 0, 0, bar)
        if df is None or len(df) == 0:
            return None
        
        try:
            summary = {
                'instrument': instId,
                'timeframe': bar,
                'total_rows': len(df),
                'date_range': {
                    'start': self.convert_timestamp_to_date(df['timestamp'].min()),
                    'end': self.convert_timestamp_to_date(df['timestamp'].max())
                },
                'price_stats': {
                    'min_price': df[['open', 'high', 'low', 'close']].min().min(),
                    'max_price': df[['open', 'high', 'low', 'close']].max().max(),
                    'avg_price': df[['open', 'high', 'low', 'close']].mean().mean()
                },
                'volume_stats': {
                    'total_volume': df['volume'].sum(),
                    'avg_volume': df['volume'].mean(),
                    'max_volume': df['volume'].max()
                },
                'data_quality': {
                    'missing_values': df.isnull().sum().to_dict(),
                    'duplicate_timestamps': df['timestamp'].duplicated().sum()
                }
            }
            return summary
        except Exception as e:
            logger.error(f"Error generating summary for {instId}: {e}")
            return None

    def get_latest_three_months_data(self, instId: str, bar: str = "1m", 
                                    return_dataframe: bool = True) -> Optional[Any]:
        """
        Get the latest three months of historical data
        Args:
            instId: Instrument ID
            bar: Timeframe
            return_dataframe: If True, return DataFrame, else numpy array
        """
        try:
            # Get all data first to find the latest timestamp
            all_data = self.get_hist_candle_data(instId, 0, 0, bar, return_dataframe=True)
            if all_data is None or len(all_data) == 0:
                logger.error(f"No data available for {instId}")
                return None
            
            # Get the latest timestamp
            latest_timestamp = all_data['timestamp'].max()
            
            # Calculate three months ago (90 days) in milliseconds
            three_months_ago = latest_timestamp - (90 * 24 * 60 * 60 * 1000)
            
            logger.info(f"Getting latest 3 months data for {instId}: "
                       f"from {self.convert_timestamp_to_date(three_months_ago)} "
                       f"to {self.convert_timestamp_to_date(latest_timestamp)}")
            
            # Get the filtered data
            return self.get_hist_candle_data(instId, three_months_ago, latest_timestamp, 
                                           bar, return_dataframe)
            
        except Exception as e:
            logger.error(f"Error getting latest three months data for {instId}: {e}")
            return None
    
    def get_data_for_date_range(self, instId: str, days: int, bar: str = "1m", 
                               return_dataframe: bool = True, start_date: Optional[datetime] = None, 
                               end_date: Optional[datetime] = None) -> Optional[Any]:
        """
        Get data for a specific number of days from the latest available data
        Args:
            instId: Instrument ID
            days: Number of days to look back
            bar: Timeframe
            return_dataframe: If True, return DataFrame, else numpy array
            start_date: Optional start date (if provided, overrides days calculation)
            end_date: Optional end date (if provided, overrides days calculation)
        """
        try:
            # Get all data first to find the latest timestamp
            all_data = self.get_hist_candle_data(instId, 0, 0, bar, return_dataframe=True)
            if all_data is None or len(all_data) == 0:
                logger.error(f"No data available for {instId}")
                return None
            
            if start_date and end_date:
                # Use provided date range
                start_timestamp = int(start_date.timestamp() * 1000)
                end_timestamp = int(end_date.timestamp() * 1000)
                
                logger.info(f"Getting data for {instId} from {start_date} to {end_date}")
            else:
                # Use days calculation
                latest_timestamp = all_data['timestamp'].max()
                start_timestamp = latest_timestamp - (days * 24 * 60 * 60 * 1000)
                end_timestamp = latest_timestamp
                
                logger.info(f"Getting {days} days data for {instId}: "
                           f"from {self.convert_timestamp_to_date(start_timestamp)} "
                           f"to {self.convert_timestamp_to_date(end_timestamp)}")
            
            # Get the filtered data
            return self.get_hist_candle_data(instId, start_timestamp, end_timestamp, 
                                           bar, return_dataframe)
            
        except Exception as e:
            logger.error(f"Error getting {days} days data for {instId}: {e}")
            return None


# Singleton instance
_historical_data_loader = None

def get_historical_data_loader() -> HistoricalDataLoader:
    """Get singleton historical data loader instance"""
    global _historical_data_loader
    if _historical_data_loader is None:
        _historical_data_loader = HistoricalDataLoader()
    return _historical_data_loader
