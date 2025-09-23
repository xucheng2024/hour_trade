#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V-shaped Reversal Strategy Backtester
V-shaped reversal strategy backtesting system
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta

from v_pattern_detector import VPattern, VPatternDetector

logger = logging.getLogger(__name__)

@dataclass
class Trade:
    """Trade record"""
    symbol: str
    pattern: VPattern
    entry_time: pd.Timestamp
    entry_price: float
    exit_time: pd.Timestamp
    exit_price: float
    holding_hours: int
    return_pct: float
    reason: str  # Exit reason

@dataclass
class BacktestResult:
    """Backtest results"""
    symbol: str
    total_patterns: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_return: float
    avg_return_per_trade: float
    avg_holding_hours: float
    max_return: float
    min_return: float
    sharpe_ratio: float
    trades: List[Trade]

class VReversalBacktester:
    """V-shaped reversal strategy backtester"""
    
    def __init__(self, 
                 holding_hours: int = 20,           # Holding time 20 hours
                 min_pattern_quality: float = 0.3,  # Minimum pattern quality score
                 transaction_cost: float = 0.001):  # Transaction cost 0.1%
        """
        Initialize backtester
        
        Args:
            holding_hours: Fixed holding time (hours)
            min_pattern_quality: Minimum pattern quality score
            transaction_cost: Single-side transaction cost
        """
        self.holding_hours = holding_hours
        self.min_pattern_quality = min_pattern_quality
        self.transaction_cost = transaction_cost
        
        logger.info(f"V-Reversal Backtester initialized:")
        logger.info(f"  Holding period: {holding_hours} hours")
        logger.info(f"  No stop loss or take profit - fixed holding only")
        logger.info(f"  Min quality: {min_pattern_quality:.1f}")
        logger.info(f"  Transaction cost: {transaction_cost:.1%}")
    
    def backtest_symbol(self, df: pd.DataFrame, patterns: List[VPattern]) -> BacktestResult:
        """
        Backtest a single cryptocurrency
        
        Args:
            df: Price data
            patterns: Detected V-shaped patterns
            
        Returns:
            Backtest results
        """
        symbol = df['symbol'].iloc[0] if 'symbol' in df.columns else 'UNKNOWN'
        trades = []
        
        # Filter high-quality patterns
        quality_patterns = [p for p in patterns if self._calculate_pattern_quality(p) >= self.min_pattern_quality]
        
        logger.info(f"Backtesting {symbol}: {len(quality_patterns)}/{len(patterns)} quality patterns")
        
        for pattern in quality_patterns:
            trade = self._simulate_trade(df, pattern)
            if trade:
                trades.append(trade)
        
        # Calculate result statistics
        result = self._calculate_backtest_result(symbol, patterns, trades)
        return result
    
    def _calculate_pattern_quality(self, pattern: VPattern) -> float:
        """Calculate pattern quality score"""
        # Based on depth, recovery speed, volume spike and other factors
        depth_score = min(pattern.depth_pct / 0.15, 1.0)  # 15% depth is full score
        speed_score = max(0, 1.0 - pattern.recovery_time / 24)  # Recovery within 24 hours is full score
        volume_score = min(pattern.volume_spike / 3.0, 1.0)  # 3x volume spike is full score
        
        return depth_score * 0.4 + speed_score * 0.4 + volume_score * 0.2
    
    def _simulate_trade(self, df: pd.DataFrame, pattern: VPattern) -> Optional[Trade]:
        """
        Simulate a single trade
        
        Args:
            df: Price data
            pattern: V-shaped pattern
            
        Returns:
            Trade record or None
        """
        # Entry timing: After V-shaped recovery confirmation
        entry_idx = pattern.recovery_idx + 1  # Enter next hour after recovery confirmation
        
        if entry_idx >= len(df):
            return None
        
        entry_time = df['timestamp'].iloc[entry_idx]
        entry_price = df['open'].iloc[entry_idx]  # Enter at open price
        
        # Calculate planned exit time
        planned_exit_idx = entry_idx + self.holding_hours
        
        # Fixed time exit, no stop loss or take profit
        exit_info = self._find_exit_point(df, entry_idx, planned_exit_idx)
        
        if not exit_info:
            return None
        
        exit_idx, exit_price, exit_reason = exit_info
        exit_time = df['timestamp'].iloc[exit_idx]
        holding_hours = exit_idx - entry_idx
        
        # Calculate return (deducting transaction costs)
        gross_return = (exit_price - entry_price) / entry_price
        net_return = gross_return - 2 * self.transaction_cost  # Buy and sell twice transaction cost
        
        return Trade(
            symbol=pattern.symbol,
            pattern=pattern,
            entry_time=entry_time,
            entry_price=entry_price,
            exit_time=exit_time,
            exit_price=exit_price,
            holding_hours=holding_hours,
            return_pct=net_return,
            reason=exit_reason
        )
    
    def _find_exit_point(self, df: pd.DataFrame, entry_idx: int, planned_exit_idx: int) -> Optional[Tuple[int, float, str]]:
        """
        Find exit point - only use fixed time exit
        
        Returns:
            (exit index, exit price, exit reason) or None
        """
        max_search_idx = min(planned_exit_idx, len(df) - 1)
        
        # Fixed time exit
        if max_search_idx < len(df):
            exit_price = df['close'].iloc[max_search_idx]
            return max_search_idx, exit_price, "time_exit"
        
        return None
    
    def _calculate_backtest_result(self, symbol: str, patterns: List[VPattern], 
                                 trades: List[Trade]) -> BacktestResult:
        """Calculate backtest result statistics"""
        if not trades:
            return BacktestResult(
                symbol=symbol,
                total_patterns=len(patterns),
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_return=0.0,
                avg_return_per_trade=0.0,
                avg_holding_hours=0.0,
                max_return=0.0,
                min_return=0.0,
                sharpe_ratio=0.0,
                trades=[]
            )
        
        returns = [t.return_pct for t in trades]
        holding_hours = [t.holding_hours for t in trades]
        
        winning_trades = sum(1 for r in returns if r > 0)
        losing_trades = len(returns) - winning_trades
        win_rate = winning_trades / len(returns)
        
        # Cumulative return (compound interest)
        total_return = np.prod([1 + r for r in returns]) - 1
        
        avg_return = np.mean(returns)
        avg_holding = np.mean(holding_hours)
        
        # Sharpe ratio (assuming risk-free rate is 0)
        if np.std(returns) > 0:
            sharpe_ratio = avg_return / np.std(returns) * np.sqrt(365 * 24 / avg_holding)
        else:
            sharpe_ratio = 0.0
        
        return BacktestResult(
            symbol=symbol,
            total_patterns=len(patterns),
            total_trades=len(trades),
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            avg_return_per_trade=avg_return,
            avg_holding_hours=avg_holding,
            max_return=max(returns),
            min_return=min(returns),
            sharpe_ratio=sharpe_ratio,
            trades=trades
        )
    
    def backtest_multiple_symbols(self, data_dict: Dict[str, pd.DataFrame], 
                                 detector: VPatternDetector) -> Dict[str, BacktestResult]:
        """
        Backtest multiple cryptocurrencies
        
        Args:
            data_dict: Cryptocurrency data dictionary
            detector: V-shaped pattern detector
            
        Returns:
            Backtest results dictionary
        """
        results = {}
        
        for symbol, df in data_dict.items():
            logger.info(f"Backtesting {symbol}...")
            
            # Detect patterns
            patterns = detector.detect_patterns(df)
            
            # Backtest
            result = self.backtest_symbol(df, patterns)
            results[symbol] = result
            
            logger.info(f"  {symbol}: {result.total_trades} trades, "
                       f"win rate {result.win_rate:.1%}, "
                       f"total return {result.total_return:.1%}")
        
        return results
    
    def generate_summary_report(self, results: Dict[str, BacktestResult]) -> Dict:
        """Generate summary report"""
        if not results:
            return {"message": "No results to summarize"}
        
        all_trades = []
        for result in results.values():
            all_trades.extend(result.trades)
        
        if not all_trades:
            return {"message": "No trades executed"}
        
        # Summary statistics
        total_patterns = sum(r.total_patterns for r in results.values())
        total_trades = len(all_trades)
        winning_trades = sum(1 for t in all_trades if t.return_pct > 0)
        
        returns = [t.return_pct for t in all_trades]
        holding_hours = [t.holding_hours for t in all_trades]
        
        # Group by exit reason
        exit_reasons = {}
        for trade in all_trades:
            reason = trade.reason
            if reason not in exit_reasons:
                exit_reasons[reason] = {"count": 0, "avg_return": 0.0, "returns": []}
            exit_reasons[reason]["count"] += 1
            exit_reasons[reason]["returns"].append(trade.return_pct)
        
        for reason in exit_reasons:
            exit_reasons[reason]["avg_return"] = np.mean(exit_reasons[reason]["returns"])
        
        summary = {
            "overview": {
                "total_symbols": len(results),
                "total_patterns": total_patterns,
                "total_trades": total_trades,
                "pattern_to_trade_ratio": total_trades / total_patterns if total_patterns > 0 else 0,
                "overall_win_rate": winning_trades / total_trades,
                "avg_return_per_trade": np.mean(returns),
                "avg_holding_hours": np.mean(holding_hours),
                "total_return": np.prod([1 + r for r in returns]) - 1,
                "sharpe_ratio": np.mean(returns) / np.std(returns) * np.sqrt(365 * 24 / np.mean(holding_hours)) if np.std(returns) > 0 else 0
            },
            "exit_analysis": exit_reasons,
            "symbol_results": {symbol: {
                "trades": r.total_trades,
                "win_rate": r.win_rate,
                "total_return": r.total_return,
                "avg_return": r.avg_return_per_trade
            } for symbol, r in results.items()}
        }
        
        return summary


def print_backtest_summary(results: Dict[str, BacktestResult]):
    """Print backtest results summary"""
    if not results:
        print("❌ No backtest results")
        return
    
    print(f"\n📊 V-Reversal Strategy Backtest Results")
    print("=" * 100)
    print(f"{'Symbol':<12} {'Patterns':<9} {'Trades':<7} {'Win Rate':<9} {'Avg Return':<11} {'Total Return':<12} {'Sharpe':<8}")
    print("-" * 100)
    
    for symbol, result in results.items():
        print(f"{symbol:<12} {result.total_patterns:>8} {result.total_trades:>6} "
              f"{result.win_rate:>8.1%} {result.avg_return_per_trade:>10.2%} "
              f"{result.total_return:>11.2%} {result.sharpe_ratio:>7.2f}")
    
    # Summary statistics
    all_patterns = sum(r.total_patterns for r in results.values())
    all_trades = sum(r.total_trades for r in results.values())
    if all_trades > 0:
        all_trade_returns = []
        for result in results.values():
            all_trade_returns.extend([t.return_pct for t in result.trades])
        
        overall_win_rate = sum(1 for r in all_trade_returns if r > 0) / len(all_trade_returns)
        overall_avg_return = np.mean(all_trade_returns)
        overall_total_return = np.prod([1 + r for r in all_trade_returns]) - 1
        
        print("-" * 100)
        print(f"{'OVERALL':<12} {all_patterns:>8} {all_trades:>6} "
              f"{overall_win_rate:>8.1%} {overall_avg_return:>10.2%} "
              f"{overall_total_return:>11.2%} {'--':>7}")


if __name__ == "__main__":
    # Test backtesting system
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Testing V-Reversal Backtester")
    
    # Can load actual data for testing here
    # from data_loader import load_sample_data
    # from v_pattern_detector import VPatternDetector
    # 
    # data = load_sample_data()
    # detector = VPatternDetector()
    # backtester = VReversalBacktester()
    # 
    # results = backtester.backtest_multiple_symbols(data, detector)
    # print_backtest_summary(results)
