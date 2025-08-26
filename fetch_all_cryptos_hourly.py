#!/usr/bin/env python3
"""
Fetch 1-hour data for all cryptocurrencies in the selected list
Similar to daily data fetching but for hourly timeframe
"""

import json
import os
import time
from datetime import datetime
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

def fetch_all_crypto_1h_data():
    """Fetch 1-hour data for all cryptocurrencies"""
    # Initialize data manager
    dm = OKXDataManager()
    
    # Load cryptocurrency list
    cryptos = load_crypto_list()
    if not cryptos:
        print("❌ No cryptocurrencies found in list")
        return
    
    print(f"🚀 Starting 1-hour data fetch for {len(cryptos)} cryptocurrencies")
    print("=" * 60)
    
    # Track results
    results = {}
    total_start_time = time.time()
    
    for i, crypto in enumerate(cryptos, 1):
        print(f"\n📊 [{i}/{len(cryptos)}] Processing {crypto} (1H)...")
        
        # Check if data already exists
        data_file = f"data/{crypto}_1H.npz"
        if os.path.exists(data_file):
            # Load existing data to show info
            try:
                data = dm.get_historical_data(crypto, '1H')
                if data is not None:
                    first_date = datetime.fromtimestamp(int(data[0][0])/1000)
                    last_date = datetime.fromtimestamp(int(data[-1][0])/1000)
                    print(f"   ✅ Data exists: {len(data)} records")
                    print(f"   📅 Range: {first_date.strftime('%Y-%m-%d %H:%M')} to {last_date.strftime('%Y-%m-%d %H:%M')}")
                    results[crypto] = {'status': 'exists', 'records': len(data)}
                else:
                    print(f"   ⚠️  Data file exists but failed to load")
                    results[crypto] = {'status': 'load_failed'}
            except Exception as e:
                print(f"   ❌ Error loading existing data: {e}")
                results[crypto] = {'status': 'load_error', 'error': str(e)}
        else:
            # Fetch new data
            try:
                start_time = time.time()
                data = dm.get_historical_data(crypto, '1H')
                fetch_time = time.time() - start_time
                
                if data is not None:
                    first_date = datetime.fromtimestamp(int(data[0][0])/1000)
                    last_date = datetime.fromtimestamp(int(data[-1][0])/1000)
                    print(f"   ✅ Fetched: {len(data)} records in {fetch_time:.1f}s")
                    print(f"   📅 Range: {first_date.strftime('%Y-%m-%d %H:%M')} to {last_date.strftime('%Y-%m-%d %H:%M')}")
                    results[crypto] = {'status': 'fetched', 'records': len(data), 'time': fetch_time}
                else:
                    print(f"   ❌ Failed to fetch data")
                    results[crypto] = {'status': 'fetch_failed'}
                    
            except Exception as e:
                print(f"   ❌ Error fetching data: {e}")
                results[crypto] = {'status': 'fetch_error', 'error': str(e)}
        
        # Rate limiting between requests (longer for hourly data)
        if i < len(cryptos):
            time.sleep(1.0)  # 1 second delay for hourly data
    
    # Print summary
    total_time = time.time() - total_start_time
    print("\n" + "=" * 60)
    print("📊 1-HOUR DATA FETCH SUMMARY")
    print("=" * 60)
    
    # Count results by status
    status_counts = {}
    total_records = 0
    
    for crypto, result in results.items():
        status = result['status']
        status_counts[status] = status_counts.get(status, 0) + 1
        
        if 'records' in result:
            total_records += result['records']
    
    print(f"Total cryptocurrencies: {len(cryptos)}")
    print(f"Total time: {total_time:.1f} seconds")
    print(f"Total records: {total_records:,}")
    print()
    
    for status, count in status_counts.items():
        print(f"{status}: {count}")
    
    print("\n✅ 1-hour data fetch completed!")

if __name__ == "__main__":
    fetch_all_crypto_1h_data()
