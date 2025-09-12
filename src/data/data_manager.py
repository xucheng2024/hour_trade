#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Data Management Module
Optimized for fetching and managing historical cryptocurrency data
"""

import json
import time
import os
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union
import warnings
import logging

import pandas as pd
import numpy as np
from okx.MarketData import MarketAPI
from okx.Account import AccountAPI

# Import configuration
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.config.okx_config import get_config, get_data_directory, get_crypto_list_file, get_log_file

# Suppress warnings
warnings.filterwarnings("ignore", category=RuntimeWarning)

# Get configuration
config = get_config()

# Dynamic cryptocurrency list - loaded from config file
# Use src/data/crypto_list_generator.py to update this list from OKX API
SELECTED_CRYPTOS = []

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.get('log_level', 'INFO')),
    format=config.get('log_format', '%(asctime)s - %(levelname)s - %(message)s'),
    handlers=[
        logging.FileHandler(get_log_file()),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class OKXDataManager:
    """Manages OKX data fetching and storage operations"""
    
    def __init__(self, flag: str = None, data_dir: str = None):
        """
        Initialize OKX Data Manager
        
        Args:
            flag: Trading flag ("0" for production, "1" for demo)
            data_dir: Directory to store data files
        """
        self.flag = flag or config.get('trading_flag', '0')
        self.data_dir = data_dir or get_data_directory()
        self.market_api = None
        self.account_api = None
        
        # Ensure data directory exists
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Initialize API connections
        self._init_apis()
    
    def _init_apis(self, max_retries: int = None, retry_delay: int = None) -> None:
        """Initialize OKX API connections with retry logic"""
        max_retries = max_retries or config.get_int('api_retry_attempts', 5)
        retry_delay = retry_delay or config.get_int('api_retry_delay', 10)
        
        for attempt in range(max_retries):
            try:
                self.market_api = MarketAPI(flag=self.flag)
                self.account_api = AccountAPI(flag=self.flag)
                logger.info("✅ OKX APIs initialized successfully")
                break
            except Exception as e:
                logger.error(f"❌ API initialization attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise RuntimeError(f"Failed to initialize OKX APIs after {max_retries} attempts")
    
    def get_historical_data(
        self, 
        inst_id: str, 
        bar: str, 
        max_retries: int = None, 
        retry_delay: int = None,
        rate_limit_delay: float = None
    ) -> Optional[np.ndarray]:
        """
        Fetch historical candlestick data for a cryptocurrency
        
        Args:
            inst_id: Instrument ID (e.g., 'BTC-USDT')
            bar: Timeframe (e.g., '1H', '15m', '1D')
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds
            rate_limit_delay: Delay between API calls to respect rate limits
            
        Returns:
            numpy array of candlestick data or None if failed
        """
        file_path = self._get_file_path(inst_id, bar)
        
        # Check if data already exists
        if os.path.exists(file_path):
            logger.info(f"📁 Data already exists for {inst_id} ({bar}): {file_path}")
            return None
        
        logger.info(f"🔄 Fetching historical data for {inst_id} ({bar})")
        
        # Use configuration defaults if not specified
        max_retries = max_retries or config.get_int('api_retry_attempts', 5)
        retry_delay = retry_delay or config.get_int('api_retry_delay', 10)
        rate_limit_delay = rate_limit_delay or config.get_float('rate_limit_delay', 0.15)
        
        try:
            # Initial data fetch
            data = self._fetch_candlesticks(inst_id, bar, max_retries, retry_delay)
            if data is None or len(data) == 0:
                logger.warning(f"⚠️  No initial data received for {inst_id}")
                return None
            
            # Fetch additional historical data
            data = self._fetch_additional_data(inst_id, bar, data, max_retries, retry_delay, rate_limit_delay)
            
            if data is not None and len(data) > 0:
                # Save data to file
                self._save_data(file_path, data)
                logger.info(f"✅ Successfully saved {len(data)} candlesticks for {inst_id} ({bar})")
                return data
            else:
                logger.warning(f"⚠️  No data to save for {inst_id} ({bar})")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error fetching data for {inst_id} ({bar}): {e}")
            return None
    
    def _fetch_candlesticks(
        self, 
        inst_id: str, 
        bar: str, 
        max_retries: int, 
        retry_delay: int,
        after: Optional[int] = None
    ) -> Optional[np.ndarray]:
        """Fetch candlestick data with retry logic"""
        for attempt in range(max_retries):
            try:
                if after is not None:
                    # Use history-candles endpoint for historical data
                    candles = self.market_api.get_history_candlesticks(
                        instId=inst_id, 
                        after=str(after), 
                        bar=bar,
                        limit=300  # history-candles supports up to 300 records per request
                    )
                else:
                    # Use regular candlesticks endpoint for recent data
                    candles = self.market_api.get_candlesticks(
                        instId=inst_id, 
                        bar=bar,
                        limit=1000  # 获取最大数量的记录
                    )
                
                if candles and 'data' in candles:
                    return candles['data']  # OKX API已经按时间顺序返回，不需要翻转
                else:
                    logger.warning(f"⚠️  Invalid response format for {inst_id}")
                    return None
                    
            except Exception as e:
                logger.error(f"❌ Attempt {attempt + 1} failed for {inst_id}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    logger.error(f"❌ All attempts failed for {inst_id}")
                    return None
        
        return None
    
    def _fetch_additional_data(
        self, 
        inst_id: str, 
        bar: str, 
        initial_data: np.ndarray, 
        max_retries: int, 
        retry_delay: int, 
        rate_limit_delay: float
    ) -> np.ndarray:
        """Fetch additional historical data by paginating backwards"""
        data = initial_data
        total_fetched = len(data)
        max_pages = 100  # 增加分页次数，获取更多历史数据，history-candlesticks支持更早的数据
        
        for page in range(max_pages):
            try:
                # Get timestamp for next batch
                # data[0][0] is the timestamp of the earliest record in current data (first row, first column)
                earliest_timestamp = int(data[0][0])
                
                # Use the earliest timestamp as 'after' parameter to get older data
                after = earliest_timestamp
                
                logger.info(f"📄 Fetching page {page + 1} for {inst_id}, after timestamp: {after}")
                
                # Fetch additional data
                additional_data = self._fetch_candlesticks(inst_id, bar, max_retries, retry_delay, after)
                
                if additional_data is None or len(additional_data) == 0:
                    logger.info(f"📊 Reached end of historical data for {inst_id}")
                    break
                
                # Check if we got new data (not just the same data)
                if len(additional_data) == 0:
                    logger.info(f"📊 No new data available for {inst_id}")
                    break
                
                # Check if the new data is actually older (smaller timestamp)
                if len(additional_data) > 0:
                    new_earliest_timestamp = int(additional_data[0][0])
                    if new_earliest_timestamp >= earliest_timestamp:
                        logger.info(f"📊 No older data available for {inst_id}")
                        break
                    
                    # Additional check: ensure we're not getting duplicate data
                    # Check if the new data overlaps with existing data
                    new_latest_timestamp = int(additional_data[-1][0])
                    if new_latest_timestamp >= earliest_timestamp:
                        logger.info(f"📊 New data overlaps with existing data for {inst_id}, stopping")
                        break
                
                # Concatenate data - put older data first to maintain chronological order
                data = np.concatenate((additional_data, data))
                
                # Remove duplicates based on timestamp and sort to ensure chronological order
                unique_indices = np.unique(data[:, 0], return_index=True)[1]
                data = data[unique_indices]
                data = data[data[:, 0].argsort()]
                
                new_total = len(data)
                logger.info(f"📈 Fetched {new_total - total_fetched} additional candlesticks for {inst_id} (Total: {new_total})")
                total_fetched = new_total
                
                # Rate limiting
                time.sleep(rate_limit_delay)
                
            except Exception as e:
                logger.error(f"❌ Error fetching additional data for {inst_id}: {e}")
                break
        
        return data
    
    def _get_file_path(self, inst_id: str, bar: str) -> str:
        """Generate file path for storing data"""
        filename = f"{inst_id}_{bar}{config.get('data_file_extension', '.npz')}"
        return os.path.join(self.data_dir, filename)
    
    def _save_data(self, file_path: str, data: np.ndarray) -> None:
        """Save data to compressed numpy file"""
        try:
            np.savez_compressed(file_path, data=data)
            logger.info(f"💾 Data saved to {file_path}")
        except Exception as e:
            logger.error(f"❌ Error saving data to {file_path}: {e}")
            raise
    
    def batch_fetch_data(
        self, 
        inst_ids: List[str], 
        bars: List[str] = None,
        max_workers: int = None
    ) -> Dict[str, Dict[str, bool]]:
        """
        Fetch data for multiple instruments and timeframes
        
        Args:
            inst_ids: List of instrument IDs
            bars: List of timeframes (default: ['1H'])
            max_workers: Maximum concurrent workers (currently limited to 1 for rate limiting)
            
        Returns:
            Dictionary with fetch results
        """
        if bars is None:
            bars = config.get_list('default_timeframes', ['1H'])
        
        max_workers = max_workers or config.get_int('max_workers', 1)
        
        results = {}
        total_operations = len(inst_ids) * len(bars)
        completed = 0
        
        logger.info(f"🚀 Starting batch data fetch for {len(inst_ids)} instruments × {len(bars)} timeframes = {total_operations} operations")
        
        for inst_id in inst_ids:
            results[inst_id] = {}
            
            for bar in bars:
                try:
                    logger.info(f"📊 Processing {inst_id} ({bar}) - {completed + 1}/{total_operations}")
                    
                    data = self.get_historical_data(inst_id, bar)
                    results[inst_id][bar] = data is not None
                    
                    completed += 1
                    
                except Exception as e:
                    logger.error(f"❌ Error processing {inst_id} ({bar}): {e}")
                    results[inst_id][bar] = False
                    completed += 1
        
        # Print summary
        successful = sum(
            sum(1 for success in timeframe_results.values() if success)
            for timeframe_results in results.values()
        )
        
        logger.info(f"✅ Batch fetch completed: {successful}/{total_operations} successful")
        return results

def load_crypto_list(file_path: str = None) -> List[str]:
    """Load cryptocurrency list from JSON file"""
    if file_path is None:
        file_path = get_crypto_list_file()
    
    try:
        with open(file_path, 'r') as file:
            cryptos = json.load(file)
        logger.info(f"📋 Loaded {len(cryptos)} cryptocurrencies from {file_path}")
        return cryptos
    except Exception as e:
        logger.error(f"❌ Error loading crypto list from {file_path}: {e}")
        return []

def save_crypto_list(cryptos: List[str], file_path: str = None) -> None:
    """Save cryptocurrency list to JSON file"""
    if file_path is None:
        file_path = get_crypto_list_file()
    
    try:
        # Ensure directory exists
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w') as file:
            json.dump(cryptos, file, indent=2)
        logger.info(f"✅ Successfully saved {len(cryptos)} cryptocurrencies to {file_path}")
    except Exception as e:
        logger.error(f"❌ Error saving crypto list to {file_path}: {e}")
        raise

def validate_crypto_list(cryptos: List[str]) -> List[str]:
    """Validate and clean cryptocurrency list"""
    valid_cryptos = []
    
    for crypto in cryptos:
        if not crypto or not isinstance(crypto, str):
            continue
            
        # Validate format (should end with -USDT)
        if not crypto.endswith('-USDT'):
            logger.warning(f"⚠️  Skipping invalid format: {crypto}")
            continue
            
        valid_cryptos.append(crypto)
    
    return valid_cryptos

def get_okx_crypto_info() -> Dict[str, str]:
    """Get cryptocurrency information and listing dates from OKX"""
    try:
        from okx.PublicData import PublicAPI
        
        flag = "0"
        public_data_api = PublicAPI(flag=flag)
        
        result = public_data_api.get_instruments(instType="SPOT")
        data = result.get('data', [])
        
        crypto_info = {}
        for item in data:
            if item.get('quoteCcy') == 'USDT' and item.get('state') == 'live':
                inst_id = item.get('instId')
                list_time = item.get('listTime')
                if inst_id and list_time:
                    crypto_info[inst_id] = list_time
        
        logger.info(f"📡 Retrieved info for {len(crypto_info)} cryptocurrencies from OKX")
        return crypto_info
    except ImportError as e:
        logger.warning(f"⚠️  OKX PublicData module not available: {e}")
        return {}
    except Exception as e:
        logger.error(f"❌ Error fetching crypto info: {e}")
        return {}

def update_crypto_list() -> List[str]:
    """Update cryptocurrency list by validating against OKX API"""
    logger.info("🔄 Starting cryptocurrency list update...")
    
    # Load existing cryptos from config file
    existing_cryptos = load_crypto_list()
    logger.info(f"📊 Found {len(existing_cryptos)} existing cryptocurrencies")
    
    if not existing_cryptos:
        logger.warning("⚠️ No existing crypto list found. Run src/data/crypto_list_generator.py first.")
        return []
    
    # Get current crypto info from OKX
    crypto_info = get_okx_crypto_info()
    
    # Filter and validate existing cryptos
    valid_cryptos = [crypto for crypto in existing_cryptos if crypto in crypto_info]
    logger.info(f"✅ Found {len(valid_cryptos)} valid cryptocurrencies on OKX")
    
    # Validate the list
    validated_cryptos = validate_crypto_list(valid_cryptos)
    logger.info(f"🔍 Validated {len(validated_cryptos)} cryptocurrencies")
    
    # Save updated list to file
    save_crypto_list(validated_cryptos)
    
    # Print summary
    logger.info(f"📋 Final cryptocurrency list ({len(validated_cryptos)} coins):")
    for i, crypto in enumerate(validated_cryptos, 1):
        logger.info(f"  {i:2d}. {crypto}")
    
    logger.info("✨ Cryptocurrency list update completed!")
    return validated_cryptos

def main():
    """Main function to execute data fetching"""
    logger.info("🚀 Starting OKX Data Manager")
    
    try:
        # Initialize data manager
        data_manager = OKXDataManager(flag="0")
        
        # Load cryptocurrency list
        cryptos = load_crypto_list()
        if not cryptos:
            logger.error("❌ No cryptocurrencies loaded, exiting")
            return
        
        # Define timeframes to fetch - specifically daily data
        timeframes = ['1D']  # Daily timeframe
        
        # Fetch data for all cryptocurrencies
        results = data_manager.batch_fetch_data(cryptos, timeframes)
        
        # Print summary
        logger.info("📊 Data Fetch Summary:")
        for inst_id, timeframe_results in results.items():
            for timeframe, success in timeframe_results.items():
                status = "✅" if success else "❌"
                logger.info(f"  {status} {inst_id} ({timeframe})")
        
        logger.info("🎉 Data fetching completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Fatal error in main execution: {e}")
        raise

if __name__ == "__main__":
    main()

