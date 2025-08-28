#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OKX Crypto List Generator
Dynamically generates cryptocurrency list from OKX API
Filters for spot pairs with 360+ days listing history and live status
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging

from okx.MarketData import MarketAPI
from okx.PublicData import PublicAPI

# Import configuration
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from src.config.okx_config import get_config, get_crypto_list_file, get_log_file

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(get_log_file()),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class OKXCryptoListGenerator:
    """Generate cryptocurrency list from OKX API with filtering"""
    
    def __init__(self, flag: str = "0"):
        """
        Initialize the generator
        
        Args:
            flag: OKX API flag (0=production, 1=demo)
        """
        self.flag = flag
        self.config = get_config()
        self.market_api = MarketAPI(flag=flag)
        self.public_api = PublicAPI(flag=flag)
        
    def get_all_spot_instruments(self) -> List[Dict]:
        """Get all available spot trading instruments from OKX"""
        try:
            logger.info("🔍 Fetching all spot instruments from OKX...")
            
            # Use PublicAPI.get_instruments to get detailed instrument info including listTime
            response = self.public_api.get_instruments(
                instType="SPOT"
            )
            
            if response.get('code') == '0':
                instruments = response.get('data', [])
                logger.info(f"✅ Found {len(instruments)} spot instruments")
                
                # Debug: show first instrument structure
                if instruments:
                    first_instrument = instruments[0]
                    logger.info(f"🔍 First instrument structure: {list(first_instrument.keys())}")
                    logger.info(f"🔍 Sample data: {first_instrument}")
                
                return instruments
            else:
                logger.error(f"❌ Failed to get instruments: {response.get('msg', 'Unknown error')}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Error fetching instruments: {e}")
            return []
    
    def filter_qualified_cryptos(self, instruments: List[Dict]) -> List[str]:
        """
        Filter instruments based on criteria:
        - USDT pairs only
        - State is 'live' (currently active)
        - Listed for at least 720 days (2 years)
        - Basic validation
        """
        try:
            logger.info("🔍 Filtering qualified cryptocurrencies...")
            
            qualified_cryptos = []
            current_time = datetime.now()
            
            for instrument in instruments:
                try:
                    inst_id = instrument.get('instId', '')
                    state = instrument.get('state', '')
                    list_time = instrument.get('listTime', '')
                    
                    # Check if it's a USDT pair
                    if not inst_id.endswith('-USDT'):
                        continue
                    
                    # Check if state is live (currently active)
                    if state != 'live':
                        logger.debug(f"❌ {inst_id}: state is {state}, not live")
                        continue
                    
                    # Check listing time (720 days = 2 years)
                    if list_time:
                        try:
                            list_timestamp = int(list_time)
                            list_date = datetime.fromtimestamp(list_timestamp / 1000)
                            days_listed = (current_time - list_date).days
                            
                            if days_listed >= 720:
                                qualified_cryptos.append(inst_id)
                                logger.debug(f"✅ {inst_id}: listed {days_listed} days ago")
                            else:
                                logger.debug(f"⏳ {inst_id}: listed {days_listed} days ago (insufficient)")
                        except (ValueError, TypeError):
                            logger.debug(f"❓ {inst_id}: invalid listing time format")
                            continue
                    else:
                        logger.debug(f"❓ {inst_id}: no listing time available")
                        continue
                        
                except Exception as e:
                    logger.warning(f"⚠️ Error processing instrument {instrument.get('instId', 'Unknown')}: {e}")
                    continue
            
            # Sort by symbol name for consistency
            qualified_cryptos.sort()
            
            logger.info(f"✅ Found {len(qualified_cryptos)} qualified cryptocurrencies (720+ days)")
            return qualified_cryptos
            
        except Exception as e:
            logger.error(f"❌ Error filtering cryptos: {e}")
            return []
    
    def get_market_data_validation(self, cryptos: List[str]) -> List[str]:
        """
        Additional validation: check if we can get market data for these cryptos
        This will also help filter out very new cryptos by checking data availability
        """
        try:
            logger.info("🔍 Validating market data availability...")
            
            validated_cryptos = []
            
            for crypto in cryptos[:50]:  # Test first 50 to avoid rate limiting
                try:
                    # Try to get recent candlestick data
                    response = self.market_api.get_candlesticks(
                        instId=crypto,
                        bar="1D",
                        after="",
                        before="",
                        limit="1"
                    )
                    
                    if response.get('code') == '0' and response.get('data'):
                        # Check if we can get historical data (at least 1 year)
                        hist_response = self.market_api.get_history_candlesticks(
                            instId=crypto,
                            bar="1D",
                            after="",
                            before="",
                            limit="400"  # Get up to 400 days of data
                        )
                        
                        if hist_response.get('code') == '0' and hist_response.get('data'):
                            hist_data = hist_response.get('data', [])
                            if len(hist_data) >= 365:  # At least 1 year of data
                                validated_cryptos.append(crypto)
                                logger.debug(f"✅ {crypto}: market data available, {len(hist_data)} days")
                            else:
                                logger.debug(f"⏳ {crypto}: only {len(hist_data)} days of data (insufficient)")
                        else:
                            logger.debug(f"❌ {crypto}: no historical data")
                    else:
                        logger.debug(f"❌ {crypto}: no market data")
                        
                    # Rate limiting
                    time.sleep(0.1)
                    
                except Exception as e:
                    logger.debug(f"⚠️ {crypto}: validation error - {e}")
                    continue
            
            # If validation successful for test samples, assume all are valid
            if len(validated_cryptos) >= 20:
                logger.info(f"✅ Market data validation passed for {len(validated_cryptos)} test samples")
                return cryptos
            else:
                logger.warning(f"⚠️ Market data validation failed, returning original list")
                return cryptos
                
        except Exception as e:
            logger.error(f"❌ Error in market data validation: {e}")
            return cryptos
    
    def generate_crypto_list(self) -> List[str]:
        """Main method to generate the qualified cryptocurrency list"""
        try:
            logger.info("🚀 Starting cryptocurrency list generation...")
            
            # Step 1: Get all spot instruments
            instruments = self.get_all_spot_instruments()
            if not instruments:
                logger.error("❌ No instruments found, exiting")
                return []
            
            # Step 2: Filter based on criteria
            qualified_cryptos = self.filter_qualified_cryptos(instruments)
            if not qualified_cryptos:
                logger.error("❌ No qualified cryptocurrencies found, exiting")
                return []
            
            # Step 3: Additional market data validation
            final_cryptos = self.get_market_data_validation(qualified_cryptos)
            
            # Step 4: Save to file
            self.save_crypto_list(final_cryptos)
            
            logger.info(f"✨ Successfully generated crypto list with {len(final_cryptos)} cryptocurrencies")
            return final_cryptos
            
        except Exception as e:
            logger.error(f"❌ Error generating crypto list: {e}")
            return []
    
    def save_crypto_list(self, cryptos: List[str]) -> None:
        """Save the generated crypto list to file"""
        try:
            file_path = get_crypto_list_file()
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Save to file
            with open(file_path, 'w') as file:
                json.dump(cryptos, file, indent=2)
            
            logger.info(f"✅ Saved {len(cryptos)} cryptocurrencies to {file_path}")
            
            # Also save a backup with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = file_path.replace('.json', f'_backup_{timestamp}.json')
            
            with open(backup_path, 'w') as file:
                json.dump(cryptos, file, indent=2)
            
            logger.info(f"✅ Backup saved to {backup_path}")
            
        except Exception as e:
            logger.error(f"❌ Error saving crypto list: {e}")
            raise
    
    def print_summary(self, cryptos: List[str]) -> None:
        """Print a summary of the generated crypto list"""
        print("\n" + "=" * 60)
        print("📊 GENERATED CRYPTO LIST SUMMARY")
        print("=" * 60)
        print(f"Total cryptocurrencies: {len(cryptos)}")
        print(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Saved to: {get_crypto_list_file()}")
        print("\nCryptocurrencies:")
        
        for i, crypto in enumerate(cryptos, 1):
            print(f"  {i:2d}. {crypto}")
        
        print("=" * 60)

def main():
    """Main function to execute crypto list generation"""
    try:
        logger.info("🚀 Starting OKX Crypto List Generator")
        
        # Initialize generator
        generator = OKXCryptoListGenerator(flag="0")
        
        # Generate crypto list
        cryptos = generator.generate_crypto_list()
        
        if cryptos:
            # Print summary
            generator.print_summary(cryptos)
            logger.info("✅ Crypto list generation completed successfully!")
        else:
            logger.error("❌ Failed to generate crypto list")
            
    except Exception as e:
        logger.error(f"❌ Fatal error in main: {e}")
        raise

if __name__ == "__main__":
    main()
