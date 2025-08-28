#!/usr/bin/env python3
"""
OKX Crypto List Generator - Command Line Interface
Run this script to generate an updated cryptocurrency list from OKX API
"""

import sys
import os

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.data.crypto_list_generator import main

if __name__ == "__main__":
    print("🚀 OKX Crypto List Generator")
    print("=" * 50)
    print("This script will:")
    print("1. Fetch all available spot instruments from OKX")
    print("2. Filter for USDT pairs with 360+ days listing history")
    print("3. Verify they are currently live")
    print("4. Save the updated list to src/config/cryptos_selected.json")
    print("=" * 50)
    
    try:
        main()
        print("\n✅ Crypto list generation completed!")
        print("You can now run fetch_all_cryptos_daily.py to get data for the new list.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


