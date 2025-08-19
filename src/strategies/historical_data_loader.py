#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Historical Data Loader for OKX Trading Strategies
Handle historical data loading and configuration management
"""

import json
import logging
from typing import Optional, Dict, Any
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

class HistoricalDataLoader:
    """Historical data loader, responsible for historical data loading and configuration management"""
    
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
    
    def get_hist_candle_data(self, instId: str, start: int, end: int, bar: str) -> Optional[np.ndarray]:
        """Get historical candlestick data"""
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
            candles = data[name]
            
            # Validate data structure
            if candles.shape[1] != 9:
                logger.error(f"Invalid data structure for {instId}: expected 9 columns, got {candles.shape[1]}")
                return None
            
            # Convert string data to proper numeric types with validation
            # OKX API columns: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
            # NOT: [ts, vol1, vol2, vol3, open, high, low, close, confirm]
            numeric_candles = np.zeros((candles.shape[0], candles.shape[1]))
            
            for i in range(candles.shape[0]):
                for j in range(candles.shape[1]):
                    try:
                        if j == 0:  # ts column
                            numeric_candles[i, j] = float(candles[i, j])
                        elif j == 8:  # confirm column
                            numeric_candles[i, j] = float(candles[i, j])
                        else:  # price and volume columns
                            value = float(candles[i, j])
                            # Validate price data (columns 1-4: open, high, low, close)
                            if j in [1, 2, 3, 4]:  # open, high, low, close
                                if value <= 0 or value > 1e10:  # Reasonable price range
                                    logger.warning(f"Invalid price value for {instId} at row {i}, col {j}: {value}")
                                    return None
                            numeric_candles[i, j] = value
                    except (ValueError, TypeError) as e:
                        logger.error(f"Data conversion error for {instId} at row {i}, col {j}: {candles[i, j]} - {e}")
                        return None
            
            # Additional validation: check if prices make sense
            # OKX API column mapping: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
            open_prices = numeric_candles[:, 1]  # Col 1: open
            high_prices = numeric_candles[:, 2]  # Col 2: high
            low_prices = numeric_candles[:, 3]   # Col 3: low
            close_prices = numeric_candles[:, 4] # Col 4: close
            
            # Validate price relationships
            if not np.all(high_prices >= low_prices) or not np.all(high_prices >= open_prices) or not np.all(high_prices >= close_prices):
                logger.error(f"Invalid price relationships for {instId}: high must be >= low, open, close")
                return None
            
            if not np.all(low_prices <= open_prices) or not np.all(low_prices <= close_prices):
                logger.error(f"Invalid price relationships for {instId}: low must be <= open, close")
                return None
            
            # If start=0 and end=0, return all data
            if start == 0 and end == 0:
                return numeric_candles
            
            # Otherwise, filter by date range
            date = numeric_candles[:, -1].astype(np.int64)
            return numeric_candles[(date >= start) & (date <= end)]
        except Exception as e:
            logger.error(f"Error loading data for {instId}: {e}")
            return None


# Singleton instance
_historical_data_loader = None

def get_historical_data_loader() -> HistoricalDataLoader:
    """Get singleton historical data loader instance"""
    global _historical_data_loader
    if _historical_data_loader is None:
        _historical_data_loader = HistoricalDataLoader()
    return _historical_data_loader
