#!/usr/bin/env python3
"""
Blacklist Manager Module
Responsible for querying blacklisted cryptocurrencies from database
"""

import os
import logging
from typing import Set, Optional
import psycopg
from psycopg.rows import dict_row

# Load environment variables first
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    def load_dotenv():
        pass
    load_dotenv()


class BlacklistManager:
    """Blacklist Manager for cryptocurrency monitoring"""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self.db_config = self._get_db_config()
    
    def _get_db_config(self) -> Optional[str]:
        """Get database URL from environment variables"""
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            return None
        return db_url
    
    def get_blacklisted_cryptos(self) -> Set[str]:
        """Get list of blacklisted cryptocurrency symbols"""
        try:
            if not self.db_config:
                self.logger.warning("⚠️ Database credentials not fully configured, skipping blacklist check")
                return set()
            
            with psycopg.connect(self.db_config) as conn:
                with conn.cursor(row_factory=dict_row) as cursor:
                    cursor.execute("""
                        SELECT crypto_symbol 
                        FROM blacklist 
                        WHERE is_active = TRUE
                    """)
                    
                    results = cursor.fetchall()
                    
                    blacklisted = {row['crypto_symbol'] for row in results}
                    self.logger.info(f"📋 Loaded {len(blacklisted)} blacklisted cryptocurrencies: {sorted(blacklisted)}")
                    return blacklisted
                    
        except psycopg.Error as e:
            self.logger.error(f"❌ Database error loading blacklist: {e}")
            return set()
        except Exception as e:
            self.logger.error(f"❌ Error loading blacklist: {e}")
            return set()
    
    def is_blacklisted(self, crypto_symbol: str) -> bool:
        """Check if a cryptocurrency is blacklisted"""
        try:
            if not self.db_config:
                return False
            
            with psycopg.connect(self.db_config) as conn:
                with conn.cursor(row_factory=dict_row) as cursor:
                    cursor.execute("""
                        SELECT crypto_symbol 
                        FROM blacklist 
                        WHERE crypto_symbol = %s AND is_active = TRUE
                    """, (crypto_symbol,))
                    
                    return cursor.fetchone() is not None
                    
        except Exception as e:
            self.logger.error(f"❌ Error checking blacklist for {crypto_symbol}: {e}")
            return False
    
    def get_blacklist_reason(self, crypto_symbol: str) -> Optional[str]:
        """Get the reason for blacklisting a cryptocurrency"""
        try:
            if not self.db_config:
                return None
            
            with psycopg.connect(self.db_config) as conn:
                with conn.cursor(row_factory=dict_row) as cursor:
                    cursor.execute("""
                        SELECT reason, blacklist_type 
                        FROM blacklist 
                        WHERE crypto_symbol = %s AND is_active = TRUE
                    """, (crypto_symbol,))
                    
                    result = cursor.fetchone()
                    if result:
                        return f"{result['blacklist_type']}: {result['reason']}"
                    return None
                    
        except Exception as e:
            self.logger.error(f"❌ Error getting blacklist reason for {crypto_symbol}: {e}")
            return None
