#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Batch Buy Strategy
Splits 100 USDT into three batches: 30, 30, 40
Buys each batch with 30 second delay between batches
"""

import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)

# Batch configuration
BATCH_AMOUNTS = [30, 30, 40]  # USDT amounts for each batch
BATCH_DELAY_SECONDS = 600  # Delay between batches


class BatchBuyStrategy:
    """Batch Buy Strategy - splits buy into multiple batches with delays"""

    def __init__(self):
        # Track active batch buys for each crypto
        # Format: instId -> {
        #   'current_batch': int,  # 0, 1, or 2 (which batch we're on)
        #   'batch_states': [bool, bool, bool],  # Whether each batch is filled
        #   'last_batch_time': float,  # Timestamp of last batch buy
        #   'limit_price': float,  # Limit price for all batches
        #   'trigger_time': float  # When the buy signal was triggered
        # }
        self.active_batches: Dict[str, Dict] = {}

        # Lock for thread safety
        self.lock = threading.RLock()

    def register_buy_signal(self, instId: str, limit_price: float) -> bool:
        """Register a buy signal and start first batch

        Args:
            instId: Instrument ID
            limit_price: Limit price for buy

        Returns:
            True if signal registered, False if already active
        """
        with self.lock:
            # Check if already have active batches
            if instId in self.active_batches:
                logger.debug(f"⏳ {instId} Batch buy already active, skipping")
                return False

            # Register new batch buy
            self.active_batches[instId] = {
                "current_batch": 0,
                "batch_states": [False, False, False],
                "last_batch_time": time.time(),
                "limit_price": limit_price,
                "trigger_time": time.time(),
            }

            logger.warning(
                f"📝 BATCH BUY SIGNAL REGISTERED: {instId}, "
                f"limit={limit_price:.6f}, batches={BATCH_AMOUNTS}"
            )
            return True

    def get_next_batch(self, instId: str) -> Optional[tuple]:
        """Get the next batch to buy if ready

        Args:
            instId: Instrument ID

        Returns:
            (batch_index, amount, limit_price) if ready, None otherwise
        """
        with self.lock:
            if instId not in self.active_batches:
                return None

            batch_info = self.active_batches[instId]
            current_batch = batch_info["current_batch"]
            batch_states = batch_info["batch_states"]

            # Check if all batches are done
            if all(batch_states):
                logger.debug(f"✅ {instId} All batches completed")
                return None

            # Check if current batch is already filled
            if batch_states[current_batch]:
                # Move to next batch
                current_batch += 1
                if current_batch >= len(BATCH_AMOUNTS):
                    return None
                batch_info["current_batch"] = current_batch

            # Check if enough time has passed since last batch
            time_since_last = time.time() - batch_info["last_batch_time"]
            if current_batch > 0 and time_since_last < BATCH_DELAY_SECONDS:
                # Not ready yet
                return None

            # Ready to buy this batch
            amount = BATCH_AMOUNTS[current_batch]
            limit_price = batch_info["limit_price"]

            return (current_batch, amount, limit_price)

    def mark_batch_filled(self, instId: str, batch_index: int):
        """Mark a batch as filled

        Args:
            instId: Instrument ID
            batch_index: Index of the batch that was filled (0, 1, or 2)
        """
        with self.lock:
            if instId not in self.active_batches:
                return

            batch_info = self.active_batches[instId]
            if batch_index < len(batch_info["batch_states"]):
                batch_info["batch_states"][batch_index] = True
                batch_info["last_batch_time"] = time.time()

                logger.warning(
                    f"✅ BATCH {batch_index + 1}/{len(BATCH_AMOUNTS)} FILLED: {instId}, "
                    f"amount={BATCH_AMOUNTS[batch_index]} USDT"
                )

                # Check if all batches are done
                if all(batch_info["batch_states"]):
                    logger.warning(
                        f"🎉 ALL BATCHES COMPLETED: {instId}, "
                        f"total={sum(BATCH_AMOUNTS)} USDT"
                    )

    def is_batch_active(self, instId: str) -> bool:
        """Check if there are active batches for this crypto

        Args:
            instId: Instrument ID

        Returns:
            True if has active batches, False otherwise
        """
        with self.lock:
            if instId not in self.active_batches:
                return False

            # Check if all batches are done
            batch_info = self.active_batches[instId]
            if all(batch_info["batch_states"]):
                return False

            return True

    def get_total_amount(self, instId: str) -> float:
        """Get total amount for all batches

        Args:
            instId: Instrument ID

        Returns:
            Total USDT amount (100)
        """
        return sum(BATCH_AMOUNTS)

    def reset_crypto(self, instId: str):
        """Reset all data for a crypto (after sell)

        Args:
            instId: Instrument ID
        """
        with self.lock:
            if instId in self.active_batches:
                del self.active_batches[instId]
                logger.debug(f"🔄 Reset batch buy data for {instId}")
