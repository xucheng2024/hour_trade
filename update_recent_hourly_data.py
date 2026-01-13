#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Force Update Recent Hourly Data
Updates the most recent data for all cryptocurrencies
"""

import sys
import os
import json
import time
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.data.data_manager import OKXDataManager
from src.config.okx_config import get_crypto_list_file

def load_crypto_list():
    """Load the cryptocurrency list from config"""
    try:
        with open(get_crypto_list_file(), 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Error loading crypto list: {e}")
        return []

def update_symbol_data(dm: OKXDataManager, symbol: str, bar: str = "1H"):
    """Force update data for a symbol by fetching latest data and merging"""
    data_dir = Path("data")
    file_path = data_dir / f"{symbol}_{bar}.npz"
    
    try:
        # Load existing data if exists
        existing_data = None
        if file_path.exists():
            try:
                data = np.load(file_path, allow_pickle=True)
                key = data.files[0]
                existing_data = data[key]
                if len(existing_data) > 0:
                    last_ts = int(existing_data[-1][0])
                    last_date = datetime.fromtimestamp(last_ts / 1000)
                    print(f"   📅 Existing data: {len(existing_data)} records, latest: {last_date.strftime('%Y-%m-%d %H:%M')}")
            except Exception as e:
                print(f"   ⚠️  Failed to load existing data: {e}")
        
        # Fetch latest data from API
        print(f"   🔄 Fetching latest data from OKX...")
        latest_data = dm._fetch_candlesticks(symbol, bar, max_retries=3, retry_delay=5)
        
        if latest_data is None or len(latest_data) == 0:
            print(f"   ❌ Failed to fetch new data")
            return False
        
        # Convert to numpy array format
        latest_array = np.array(latest_data)
        
        if existing_data is not None and len(existing_data) > 0:
            # Merge: remove duplicates and keep latest
            existing_ts = existing_data[:, 0].astype(np.int64)
            latest_ts = latest_array[:, 0].astype(np.int64)
            
            # Find new records (not in existing)
            new_mask = ~np.isin(latest_ts, existing_ts)
            new_records = latest_array[new_mask]
            
            if len(new_records) > 0:
                # Combine and sort by timestamp
                combined = np.vstack([existing_data, new_records])
                combined = combined[combined[:, 0].astype(np.int64).argsort()]
                
                # Save updated data
                np.savez_compressed(file_path, data=combined)
                print(f"   ✅ Updated: {len(existing_data)} → {len(combined)} records (+{len(new_records)} new)")
                return True
            else:
                print(f"   ✅ Already up to date")
                return True
        else:
            # No existing data, save new data
            np.savez_compressed(file_path, data=latest_array)
            print(f"   ✅ Saved: {len(latest_array)} records")
            return True
            
    except Exception as e:
        print(f"   ❌ Error updating {symbol}: {e}")
        return False

def main():
    """Main function to update all crypto data"""
    print("="*70)
    print("Force Update Recent Hourly Data")
    print("="*70)
    
    # Initialize data manager
    dm = OKXDataManager()
    
    # Load crypto list
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found")
        return
    
    print(f"\n📊 Updating data for {len(cryptos)} cryptocurrencies...\n")
    
    updated = 0
    failed = 0
    
    for i, crypto in enumerate(cryptos, 1):
        print(f"[{i}/{len(cryptos)}] {crypto}:")
        if update_symbol_data(dm, crypto, "1H"):
            updated += 1
        else:
            failed += 1
        
        # Rate limiting
        if i < len(cryptos):
            time.sleep(0.5)
    
    print(f"\n{'='*70}")
    print("Update Summary")
    print(f"{'='*70}")
    print(f"Total: {len(cryptos)}")
    print(f"Updated: {updated}")
    print(f"Failed: {failed}")
    print(f"{'='*70}\n")

if __name__ == "__main__":
    main()
