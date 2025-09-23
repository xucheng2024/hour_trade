#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V-shaped Reversal Pattern Detection
V-shaped reversal pattern detector
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class VPattern:
    """V-shaped reversal pattern data structure"""
    symbol: str
    start_idx: int          # Decline start position
    bottom_idx: int         # Bottom position
    recovery_idx: int       # Recovery position
    start_price: float      # Start price
    bottom_price: float     # Bottom price
    recovery_price: float   # Recovery price
    depth_pct: float        # V depth percentage
    recovery_time: int      # Recovery time (hours)
    total_time: int         # Total time (hours)
    start_time: pd.Timestamp
    bottom_time: pd.Timestamp
    recovery_time_stamp: pd.Timestamp
    volume_spike: float     # Bottom volume spike multiplier

class VPatternDetector:
    """V-shaped reversal pattern detector"""
    
    def __init__(self, 
                 min_depth_pct: float = 0.05,      # Minimum decline depth 5%
                 max_depth_pct: float = 0.30,      # Maximum decline depth 30%
                 min_recovery_pct: float = 0.80,   # Minimum recovery ratio 80%
                 max_total_time: int = 48,         # Maximum total time 48 hours
                 min_total_time: int = 6,          # Minimum total time 6 hours
                 max_recovery_time: int = 24):     # Maximum recovery time 24 hours
        """
        Initialize V-shaped reversal detector
        
        Args:
            min_depth_pct: Minimum decline depth percentage
            max_depth_pct: Maximum decline depth percentage  
            min_recovery_pct: Minimum recovery ratio
            max_total_time: Maximum total time (hours)
            min_total_time: Minimum total time (hours)
            max_recovery_time: Maximum recovery time (hours)
        """
        self.min_depth_pct = min_depth_pct
        self.max_depth_pct = max_depth_pct
        self.min_recovery_pct = min_recovery_pct
        self.max_total_time = max_total_time
        self.min_total_time = min_total_time
        self.max_recovery_time = max_recovery_time
        
        logger.info(f"V-Pattern Detector initialized:")
        logger.info(f"  Depth range: {min_depth_pct:.1%} - {max_depth_pct:.1%}")
        logger.info(f"  Recovery requirement: {min_recovery_pct:.1%}")
        logger.info(f"  Time constraints: {min_total_time}h - {max_total_time}h (recovery ≤ {max_recovery_time}h)")
    
    def detect_patterns(self, df: pd.DataFrame) -> List[VPattern]:
        """
        Detect V-shaped reversal patterns
        
        Args:
            df: DataFrame containing OHLCV data
            
        Returns:
            List of detected V-shaped patterns
        """
        patterns = []
        symbol = df['symbol'].iloc[0] if 'symbol' in df.columns else 'UNKNOWN'
        
        # Find local peaks as potential starting points
        high_points = self._find_local_peaks(df['high'].values, window=3)
        
        for start_idx in high_points:
            # Find V-shaped patterns after this peak
            pattern = self._search_v_pattern_from_start(df, start_idx, symbol)
            if pattern:
                patterns.append(pattern)
        
        # Remove duplicates and filter overlapping patterns
        patterns = self._filter_overlapping_patterns(patterns)
        
        logger.info(f"Detected {len(patterns)} V-patterns for {symbol}")
        return patterns
    
    def _find_local_peaks(self, prices: np.ndarray, window: int = 3) -> List[int]:
        """Find local peaks"""
        peaks = []
        for i in range(window, len(prices) - window):
            if all(prices[i] >= prices[i-j] for j in range(1, window+1)) and \
               all(prices[i] >= prices[i+j] for j in range(1, window+1)):
                peaks.append(i)
        return peaks
    
    def _search_v_pattern_from_start(self, df: pd.DataFrame, start_idx: int, symbol: str) -> Optional[VPattern]:
        """Search for V-shaped pattern from given starting point"""
        if start_idx >= len(df) - self.min_total_time:
            return None
        
        start_price = df['high'].iloc[start_idx]
        start_time = df['timestamp'].iloc[start_idx]
        
        # Search within maximum time window
        end_search_idx = min(start_idx + self.max_total_time, len(df))
        search_window = df.iloc[start_idx:end_search_idx]
        
        # Find bottom
        bottom_candidates = self._find_bottom_candidates(search_window, start_price)
        
        for bottom_rel_idx, bottom_price in bottom_candidates:
            bottom_idx = start_idx + bottom_rel_idx
            depth_pct = (start_price - bottom_price) / start_price
            
            # Check if depth is within reasonable range
            if not (self.min_depth_pct <= depth_pct <= self.max_depth_pct):
                continue
            
            # Find recovery point
            recovery_pattern = self._find_recovery_point(df, start_idx, bottom_idx, start_price, bottom_price, symbol)
            if recovery_pattern:
                return recovery_pattern
        
        return None
    
    def _find_bottom_candidates(self, window_df: pd.DataFrame, start_price: float) -> List[Tuple[int, float]]:
        """Find bottom candidate points"""
        candidates = []
        
        # Find local lows
        lows = window_df['low'].values
        for i in range(2, len(lows) - 2):
            # Local minimum conditions
            if lows[i] <= lows[i-1] and lows[i] <= lows[i+1] and \
               lows[i] <= lows[i-2] and lows[i] <= lows[i+2]:
                
                depth_pct = (start_price - lows[i]) / start_price
                if self.min_depth_pct <= depth_pct <= self.max_depth_pct:
                    candidates.append((i, lows[i]))
        
        # Sort by depth, prioritize deeper bottoms
        candidates.sort(key=lambda x: x[1])  # Sort by price ascending
        return candidates
    
    def _find_recovery_point(self, df: pd.DataFrame, start_idx: int, bottom_idx: int, 
                           start_price: float, bottom_price: float, symbol: str) -> Optional[VPattern]:
        """Find recovery point"""
        recovery_threshold = bottom_price + (start_price - bottom_price) * self.min_recovery_pct
        
        # Search for recovery starting from bottom
        search_start = bottom_idx + 1
        max_search_end = min(bottom_idx + self.max_recovery_time, len(df))
        
        for recovery_idx in range(search_start, max_search_end):
            recovery_price = df['high'].iloc[recovery_idx]
            
            if recovery_price >= recovery_threshold:
                # Found recovery point, verify time constraints
                total_time = recovery_idx - start_idx
                recovery_time = recovery_idx - bottom_idx
                
                if self.min_total_time <= total_time <= self.max_total_time and \
                   recovery_time <= self.max_recovery_time:
                    
                    # Calculate volume spike
                    volume_spike = self._calculate_volume_spike(df, bottom_idx)
                    
                    return VPattern(
                        symbol=symbol,
                        start_idx=start_idx,
                        bottom_idx=bottom_idx,
                        recovery_idx=recovery_idx,
                        start_price=start_price,
                        bottom_price=bottom_price,
                        recovery_price=recovery_price,
                        depth_pct=(start_price - bottom_price) / start_price,
                        recovery_time=recovery_time,
                        total_time=total_time,
                        start_time=df['timestamp'].iloc[start_idx],
                        bottom_time=df['timestamp'].iloc[bottom_idx],
                        recovery_time_stamp=df['timestamp'].iloc[recovery_idx],
                        volume_spike=volume_spike
                    )
        
        return None
    
    def _calculate_volume_spike(self, df: pd.DataFrame, bottom_idx: int) -> float:
        """Calculate bottom volume spike multiplier"""
        if 'volume' not in df.columns:
            return 1.0
        
        # Calculate average volume 10 hours before bottom
        start_avg = max(0, bottom_idx - 10)
        avg_volume = df['volume'].iloc[start_avg:bottom_idx].mean()
        bottom_volume = df['volume'].iloc[bottom_idx]
        
        if avg_volume > 0:
            return bottom_volume / avg_volume
        return 1.0
    
    def _filter_overlapping_patterns(self, patterns: List[VPattern]) -> List[VPattern]:
        """Filter overlapping patterns, keep the best quality ones"""
        if len(patterns) <= 1:
            return patterns
        
        # Sort by start time
        patterns.sort(key=lambda p: p.start_idx)
        
        filtered = []
        for pattern in patterns:
            # Check if overlapping with existing patterns
            overlap = False
            for existing in filtered:
                if self._patterns_overlap(pattern, existing):
                    # If overlapping, compare quality, keep the better one
                    if self._pattern_quality_score(pattern) > self._pattern_quality_score(existing):
                        filtered.remove(existing)
                        filtered.append(pattern)
                    overlap = True
                    break
            
            if not overlap:
                filtered.append(pattern)
        
        return filtered
    
    def _patterns_overlap(self, p1: VPattern, p2: VPattern) -> bool:
        """Check if two patterns overlap"""
        return not (p1.recovery_idx < p2.start_idx or p2.recovery_idx < p1.start_idx)
    
    def _pattern_quality_score(self, pattern: VPattern) -> float:
        """Calculate pattern quality score, higher score means better quality"""
        # Based on depth, recovery speed, volume spike and other factors
        depth_score = min(pattern.depth_pct / 0.15, 1.0)  # 15% depth is full score
        speed_score = max(0, 1.0 - pattern.recovery_time / self.max_recovery_time)  # Faster recovery gets higher score
        volume_score = min(pattern.volume_spike / 3.0, 1.0)  # 3x volume spike is full score
        
        return depth_score * 0.4 + speed_score * 0.4 + volume_score * 0.2
    
    def analyze_patterns(self, patterns: List[VPattern]) -> Dict:
        """Analyze detected pattern statistics"""
        if not patterns:
            return {"count": 0}
        
        depths = [p.depth_pct for p in patterns]
        recovery_times = [p.recovery_time for p in patterns]
        total_times = [p.total_time for p in patterns]
        volume_spikes = [p.volume_spike for p in patterns]
        
        analysis = {
            "count": len(patterns),
            "depth_stats": {
                "mean": np.mean(depths),
                "std": np.std(depths),
                "min": np.min(depths),
                "max": np.max(depths)
            },
            "recovery_time_stats": {
                "mean": np.mean(recovery_times),
                "std": np.std(recovery_times),
                "min": np.min(recovery_times),
                "max": np.max(recovery_times)
            },
            "total_time_stats": {
                "mean": np.mean(total_times),
                "std": np.std(total_times),
                "min": np.min(total_times),
                "max": np.max(total_times)
            },
            "volume_spike_stats": {
                "mean": np.mean(volume_spikes),
                "std": np.std(volume_spikes),
                "min": np.min(volume_spikes),
                "max": np.max(volume_spikes)
            }
        }
        
        return analysis


def print_pattern_summary(patterns: List[VPattern]):
    """Print pattern summary"""
    if not patterns:
        print("❌ No V-patterns detected")
        return
    
    print(f"\n🎯 Detected {len(patterns)} V-shaped reversal patterns:")
    print("=" * 80)
    print(f"{'Symbol':<12} {'Start Time':<20} {'Depth':<8} {'Recovery':<8} {'Total':<8} {'Volume':<8}")
    print("-" * 80)
    
    for pattern in patterns:
        print(f"{pattern.symbol:<12} {pattern.start_time.strftime('%Y-%m-%d %H:%M'):<20} "
              f"{pattern.depth_pct:>6.1%}   {pattern.recovery_time:>5}h   "
              f"{pattern.total_time:>5}h   {pattern.volume_spike:>6.1f}x")


if __name__ == "__main__":
    # Test pattern detector
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Testing V-Pattern Detector")
    
    # Can load actual data for testing here
    # from data_loader import load_sample_data
    # data = load_sample_data()
    # 
    # detector = VPatternDetector()
    # for symbol, df in data.items():
    #     patterns = detector.detect_patterns(df)
    #     print_pattern_summary(patterns)

