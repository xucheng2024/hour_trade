#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V-shaped Reversal Pattern Detection
V型反转模式检测器
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class VPattern:
    """V型反转模式数据结构"""
    symbol: str
    start_idx: int          # 下跌开始位置
    bottom_idx: int         # 底部位置
    recovery_idx: int       # 恢复位置
    start_price: float      # 开始价格
    bottom_price: float     # 底部价格
    recovery_price: float   # 恢复价格
    depth_pct: float        # V的深度百分比
    recovery_time: int      # 恢复时间(小时)
    total_time: int         # 总时间(小时)
    start_time: pd.Timestamp
    bottom_time: pd.Timestamp
    recovery_time_stamp: pd.Timestamp
    volume_spike: float     # 底部成交量放大倍数

class VPatternDetector:
    """V型反转模式检测器"""
    
    def __init__(self, 
                 min_depth_pct: float = 0.05,      # 最小下跌深度5%
                 max_depth_pct: float = 0.30,      # 最大下跌深度30%
                 min_recovery_pct: float = 0.80,   # 最小恢复比例80%
                 max_total_time: int = 48,         # 最大总时间48小时
                 min_total_time: int = 6,          # 最小总时间6小时
                 max_recovery_time: int = 24):     # 最大恢复时间24小时
        """
        初始化V型反转检测器
        
        Args:
            min_depth_pct: 最小下跌深度百分比
            max_depth_pct: 最大下跌深度百分比  
            min_recovery_pct: 最小恢复比例
            max_total_time: 最大总时间(小时)
            min_total_time: 最小总时间(小时)
            max_recovery_time: 最大恢复时间(小时)
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
        检测V型反转模式
        
        Args:
            df: 包含OHLCV数据的DataFrame
            
        Returns:
            检测到的V型模式列表
        """
        patterns = []
        symbol = df['symbol'].iloc[0] if 'symbol' in df.columns else 'UNKNOWN'
        
        # 寻找局部高点作为潜在起点
        high_points = self._find_local_peaks(df['high'].values, window=3)
        
        for start_idx in high_points:
            # 寻找这个高点之后的V型模式
            pattern = self._search_v_pattern_from_start(df, start_idx, symbol)
            if pattern:
                patterns.append(pattern)
        
        # 去重和过滤重叠模式
        patterns = self._filter_overlapping_patterns(patterns)
        
        logger.info(f"Detected {len(patterns)} V-patterns for {symbol}")
        return patterns
    
    def _find_local_peaks(self, prices: np.ndarray, window: int = 3) -> List[int]:
        """寻找局部高点"""
        peaks = []
        for i in range(window, len(prices) - window):
            if all(prices[i] >= prices[i-j] for j in range(1, window+1)) and \
               all(prices[i] >= prices[i+j] for j in range(1, window+1)):
                peaks.append(i)
        return peaks
    
    def _search_v_pattern_from_start(self, df: pd.DataFrame, start_idx: int, symbol: str) -> Optional[VPattern]:
        """从给定起点搜索V型模式"""
        if start_idx >= len(df) - self.min_total_time:
            return None
        
        start_price = df['high'].iloc[start_idx]
        start_time = df['timestamp'].iloc[start_idx]
        
        # 在最大时间窗口内搜索
        end_search_idx = min(start_idx + self.max_total_time, len(df))
        search_window = df.iloc[start_idx:end_search_idx]
        
        # 寻找底部
        bottom_candidates = self._find_bottom_candidates(search_window, start_price)
        
        for bottom_rel_idx, bottom_price in bottom_candidates:
            bottom_idx = start_idx + bottom_rel_idx
            depth_pct = (start_price - bottom_price) / start_price
            
            # 检查深度是否在合理范围内
            if not (self.min_depth_pct <= depth_pct <= self.max_depth_pct):
                continue
            
            # 寻找恢复点
            recovery_pattern = self._find_recovery_point(df, start_idx, bottom_idx, start_price, bottom_price, symbol)
            if recovery_pattern:
                return recovery_pattern
        
        return None
    
    def _find_bottom_candidates(self, window_df: pd.DataFrame, start_price: float) -> List[Tuple[int, float]]:
        """寻找底部候选点"""
        candidates = []
        
        # 寻找局部低点
        lows = window_df['low'].values
        for i in range(2, len(lows) - 2):
            # 局部最低点条件
            if lows[i] <= lows[i-1] and lows[i] <= lows[i+1] and \
               lows[i] <= lows[i-2] and lows[i] <= lows[i+2]:
                
                depth_pct = (start_price - lows[i]) / start_price
                if self.min_depth_pct <= depth_pct <= self.max_depth_pct:
                    candidates.append((i, lows[i]))
        
        # 按深度排序，优先考虑较深的底部
        candidates.sort(key=lambda x: x[1])  # 按价格升序排序
        return candidates
    
    def _find_recovery_point(self, df: pd.DataFrame, start_idx: int, bottom_idx: int, 
                           start_price: float, bottom_price: float, symbol: str) -> Optional[VPattern]:
        """寻找恢复点"""
        recovery_threshold = bottom_price + (start_price - bottom_price) * self.min_recovery_pct
        
        # 从底部开始搜索恢复
        search_start = bottom_idx + 1
        max_search_end = min(bottom_idx + self.max_recovery_time, len(df))
        
        for recovery_idx in range(search_start, max_search_end):
            recovery_price = df['high'].iloc[recovery_idx]
            
            if recovery_price >= recovery_threshold:
                # 找到恢复点，验证时间约束
                total_time = recovery_idx - start_idx
                recovery_time = recovery_idx - bottom_idx
                
                if self.min_total_time <= total_time <= self.max_total_time and \
                   recovery_time <= self.max_recovery_time:
                    
                    # 计算成交量放大
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
        """计算底部成交量放大倍数"""
        if 'volume' not in df.columns:
            return 1.0
        
        # 计算底部前10小时的平均成交量
        start_avg = max(0, bottom_idx - 10)
        avg_volume = df['volume'].iloc[start_avg:bottom_idx].mean()
        bottom_volume = df['volume'].iloc[bottom_idx]
        
        if avg_volume > 0:
            return bottom_volume / avg_volume
        return 1.0
    
    def _filter_overlapping_patterns(self, patterns: List[VPattern]) -> List[VPattern]:
        """过滤重叠的模式，保留质量最好的"""
        if len(patterns) <= 1:
            return patterns
        
        # 按开始时间排序
        patterns.sort(key=lambda p: p.start_idx)
        
        filtered = []
        for pattern in patterns:
            # 检查是否与已有模式重叠
            overlap = False
            for existing in filtered:
                if self._patterns_overlap(pattern, existing):
                    # 如果重叠，比较质量，保留更好的
                    if self._pattern_quality_score(pattern) > self._pattern_quality_score(existing):
                        filtered.remove(existing)
                        filtered.append(pattern)
                    overlap = True
                    break
            
            if not overlap:
                filtered.append(pattern)
        
        return filtered
    
    def _patterns_overlap(self, p1: VPattern, p2: VPattern) -> bool:
        """检查两个模式是否重叠"""
        return not (p1.recovery_idx < p2.start_idx or p2.recovery_idx < p1.start_idx)
    
    def _pattern_quality_score(self, pattern: VPattern) -> float:
        """计算模式质量分数，分数越高质量越好"""
        # 基于深度、恢复速度、成交量放大等因素
        depth_score = min(pattern.depth_pct / 0.15, 1.0)  # 深度15%为满分
        speed_score = max(0, 1.0 - pattern.recovery_time / self.max_recovery_time)  # 恢复越快分数越高
        volume_score = min(pattern.volume_spike / 3.0, 1.0)  # 成交量放大3倍为满分
        
        return depth_score * 0.4 + speed_score * 0.4 + volume_score * 0.2
    
    def analyze_patterns(self, patterns: List[VPattern]) -> Dict:
        """分析检测到的模式统计信息"""
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
    """打印模式摘要"""
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
    # 测试模式检测器
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Testing V-Pattern Detector")
    
    # 这里可以加载实际数据进行测试
    # from data_loader import load_sample_data
    # data = load_sample_data()
    # 
    # detector = VPatternDetector()
    # for symbol, df in data.items():
    #     patterns = detector.detect_patterns(df)
    #     print_pattern_summary(patterns)

