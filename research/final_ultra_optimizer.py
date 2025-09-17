#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final Ultra Optimizer - 集成训练/测试分割的超高性能优化器
解决数据泄露问题，提供真实可信的OOS收益率
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import warnings
import time
from datetime import datetime, timedelta
import json
import os

warnings.filterwarnings('ignore')
logger = logging.getLogger(__name__)

@dataclass
class BacktestParams:
    """回测参数"""
    buy_threshold: float
    stop_loss: float
    take_profit: float

@dataclass
class OptimizationResult:
    """优化结果"""
    symbol: str
    best_params: BacktestParams
    train_return: float
    test_return: float
    train_days: int
    test_days: int
    train_period: Tuple[pd.Timestamp, pd.Timestamp]
    test_period: Tuple[pd.Timestamp, pd.Timestamp]
    consistency_ratio: float

class FinalUltraOptimizer:
    """
    最终超高性能优化器
    集成训练/测试分割，解决数据泄露问题
    """
    
    def __init__(self, data: pd.DataFrame, test_days: int = 90):
        """
        初始化最终优化器
        
        Args:
            data: 完整市场数据
            test_days: 测试期天数（默认90天）
        """
        self.data = data.copy()
        self.test_days = test_days
        self.symbols = data['symbol'].unique()
        self.prepare_data_with_split()
        
        logger.info(f"🚀 Final Ultra Optimizer initialized with {len(self.data)} records for {len(self.symbols)} symbols")
        logger.info(f"📅 Test period: {test_days} days")
    
    def prepare_data_with_split(self):
        """预处理数据并进行训练/测试分割"""
        logger.info("🔄 Preparing data with train/test split...")
        
        self.train_data = {}
        self.test_data = {}
        
        for symbol in self.symbols:
            df = self.data[self.data['symbol'] == symbol].copy()
            
            if len(df) == 0:
                continue
            
            # 确保时间格式
            if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
                df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # 按时间排序
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # 时间分割
            latest_time = df['timestamp'].max()
            split_time = latest_time - pd.Timedelta(days=self.test_days)
            
            train_df = df[df['timestamp'] < split_time].copy()
            test_df = df[df['timestamp'] >= split_time].copy()
            
            if len(train_df) < 500 or len(test_df) < 50:
                logger.warning(f"Insufficient data for {symbol}: train={len(train_df)}, test={len(test_df)}")
                continue
            
            # 预处理训练数据
            train_processed = self._process_data_for_symbol(train_df)
            test_processed = self._process_data_for_symbol(test_df)
            
            self.train_data[symbol] = train_processed
            self.test_data[symbol] = test_processed
            
            logger.info(f"✅ {symbol}: Train {len(train_df)} records, Test {len(test_df)} records")
        
        logger.info(f"✅ Data preparation complete for {len(self.train_data)} symbols")
    
    def _process_data_for_symbol(self, df: pd.DataFrame) -> Dict:
        """处理单个币种的数据为向量化格式"""
        # 提取日期和计算日开盘价
        df['date'] = df['timestamp'].dt.tz_localize('UTC').dt.date
        df['hour_in_day'] = df.groupby('date').cumcount()
        
        # 计算每日开盘价
        daily_opens = df.groupby('date')['open'].first()
        df['daily_open'] = df['date'].map(daily_opens)
        
        # 转换为numpy数组
        return {
            'dates': df['date'].values,
            'hours_in_day': df['hour_in_day'].values,
            'opens': df['open'].values,
            'highs': df['high'].values,
            'lows': df['low'].values,
            'closes': df['close'].values,
            'daily_opens': df['daily_open'].values,
            'timestamps': df['timestamp'].values,
            'unique_dates': df['date'].unique(),
            'period_start': df['timestamp'].min(),
            'period_end': df['timestamp'].max()
        }
    
    def ultra_fast_backtest(self, symbol: str, b: float, l: float, p: float, use_test_data: bool = False) -> float:
        """
        超快速回测
        
        Args:
            symbol: 币种
            b, l, p: 参数
            use_test_data: 是否使用测试数据
            
        Returns:
            总收益率
        """
        data_source = self.test_data if use_test_data else self.train_data
        
        if symbol not in data_source:
            return 0.0
        
        data = data_source[symbol]
        dates = data['dates']
        hours_in_day = data['hours_in_day']
        lows = data['lows']
        highs = data['highs']
        closes = data['closes']
        daily_opens = data['daily_opens']
        unique_dates = data['unique_dates']
        
        total_return = 1.0
        
        # 向量化处理每个交易日
        for date in unique_dates:
            day_mask = dates == date
            day_hours = hours_in_day[day_mask]
            day_lows = lows[day_mask]
            day_highs = highs[day_mask]
            day_closes = closes[day_mask]
            day_open = daily_opens[day_mask][0]
            
            if len(day_hours) <= 1:
                continue
            
            # 计算关键价位
            B = day_open * (1 - b)
            SL = day_open * (1 - l)
            TP = day_open * (1 + p)
            
            # 向量化寻找买入点
            after_open_mask = day_hours > 0
            if not after_open_mask.any():
                continue
            
            after_open_lows = day_lows[after_open_mask]
            buy_signals = after_open_lows <= B
            
            if not buy_signals.any():
                continue
            
            # 找到首次买入点
            buy_idx = np.argmax(buy_signals)
            entry_price = B
            
            # 检查买入后的数据
            post_buy_start = buy_idx + 1
            if post_buy_start >= len(after_open_lows):
                exit_price = day_closes[-1]
            else:
                # 向量化检查止损止盈
                post_lows = day_lows[after_open_mask][post_buy_start:]
                post_highs = day_highs[after_open_mask][post_buy_start:]
                
                sl_hits = post_lows <= SL
                tp_hits = post_highs >= TP
                
                sl_indices = np.where(sl_hits)[0]
                tp_indices = np.where(tp_hits)[0]
                
                if len(sl_indices) > 0 and len(tp_indices) > 0:
                    if sl_indices[0] <= tp_indices[0]:
                        exit_price = SL
                    else:
                        exit_price = TP
                elif len(sl_indices) > 0:
                    exit_price = SL
                elif len(tp_indices) > 0:
                    exit_price = TP
                else:
                    exit_price = day_closes[-1]
            
            # 累计收益
            trade_return = exit_price / entry_price
            total_return *= trade_return
        
        return total_return - 1
    
    def optimize_single_symbol_with_split(self, symbol: str, param_ranges: Dict[str, np.ndarray]) -> OptimizationResult:
        """
        单币种优化（带训练/测试分割）
        
        Args:
            symbol: 币种
            param_ranges: 参数范围
            
        Returns:
            优化结果
        """
        if symbol not in self.train_data or symbol not in self.test_data:
            return None
        
        logger.info(f"🔍 Optimizing {symbol} with train/test split...")
        
        b_range = param_ranges['buy_threshold']
        l_range = param_ranges['stop_loss']
        p_range = param_ranges['take_profit']
        
        best_params = None
        best_train_return = -float('inf')
        total_tests = 0
        
        # 在训练数据上寻找最优参数
        for b in b_range:
            for l in l_range:
                if l < b * 0.5:
                    continue
                for p in p_range:
                    train_return = self.ultra_fast_backtest(symbol, b, l, p, use_test_data=False)
                    total_tests += 1
                    
                    if train_return > best_train_return:
                        best_train_return = train_return
                        best_params = BacktestParams(
                            buy_threshold=b,
                            stop_loss=l,
                            take_profit=p
                        )
        
        if best_params is None:
            logger.error(f"No valid parameters found for {symbol}")
            return None
        
        # 在测试数据上验证最优参数
        test_return = self.ultra_fast_backtest(
            symbol, 
            best_params.buy_threshold, 
            best_params.stop_loss, 
            best_params.take_profit, 
            use_test_data=True
        )
        
        # 计算一致性比率
        consistency_ratio = test_return / best_train_return if best_train_return != 0 else 0
        
        # 获取时间段信息
        train_data = self.train_data[symbol]
        test_data = self.test_data[symbol]
        
        train_days = (train_data['period_end'] - train_data['period_start']).days + 1
        test_days = (test_data['period_end'] - test_data['period_start']).days + 1
        
        result = OptimizationResult(
            symbol=symbol,
            best_params=best_params,
            train_return=best_train_return,
            test_return=test_return,
            train_days=train_days,
            test_days=test_days,
            train_period=(train_data['period_start'], train_data['period_end']),
            test_period=(test_data['period_start'], test_data['period_end']),
            consistency_ratio=consistency_ratio
        )
        
        logger.info(f"✅ {symbol} - Train: {best_train_return:.2%} ({train_days}d), Test: {test_return:.2%} ({test_days}d), Consistency: {consistency_ratio:.2f}")
        
        return result
    
    def batch_optimize_with_split(self, symbols: Optional[List[str]] = None, 
                                param_ranges: Optional[Dict[str, np.ndarray]] = None) -> Dict[str, OptimizationResult]:
        """
        批量优化（带训练/测试分割）
        
        Args:
            symbols: 币种列表（None表示全部）
            param_ranges: 参数范围
            
        Returns:
            优化结果字典
        """
        if symbols is None:
            symbols = list(self.train_data.keys())
        
        if param_ranges is None:
            param_ranges = self.create_default_param_ranges()
        
        logger.info(f"🚀 Starting batch optimization with train/test split for {len(symbols)} symbols")
        
        start_time = time.time()
        results = {}
        
        for symbol in symbols:
            try:
                result = self.optimize_single_symbol_with_split(symbol, param_ranges)
                if result:
                    results[symbol] = result
                else:
                    logger.warning(f"Failed to optimize {symbol}")
            except Exception as e:
                logger.error(f"Error optimizing {symbol}: {e}")
                continue
        
        duration = time.time() - start_time
        successful = len(results)
        
        logger.info(f"🎉 Batch optimization completed in {duration:.1f} seconds")
        logger.info(f"✅ {successful}/{len(symbols)} symbols optimized successfully")
        
        return results
    
    def create_default_param_ranges(self) -> Dict[str, np.ndarray]:
        """创建默认参数范围"""
        return {
            'buy_threshold': np.array([0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02]),
            'stop_loss': np.array([0.005, 0.0075, 0.01, 0.0125, 0.015, 0.02]),
            'take_profit': np.array([0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05])
        }
    
    def save_results(self, results: Dict[str, OptimizationResult], filename: Optional[str] = None) -> str:
        """保存优化结果"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"final_ultra_optimization_{timestamp}.json"
        
        # 转换为可序列化格式
        serializable_results = {}
        
        for symbol, result in results.items():
            serializable_results[symbol] = {
                'symbol': result.symbol,
                'best_parameters': {
                    'buy_threshold': result.best_params.buy_threshold,
                    'stop_loss': result.best_params.stop_loss,
                    'take_profit': result.best_params.take_profit,
                    'buy_threshold_pct': result.best_params.buy_threshold * 100,
                    'stop_loss_pct': result.best_params.stop_loss * 100,
                    'take_profit_pct': result.best_params.take_profit * 100
                },
                'train_performance': {
                    'return': result.train_return,
                    'days': result.train_days,
                    'period_start': result.train_period[0].isoformat(),
                    'period_end': result.train_period[1].isoformat(),
                    'annualized_return': (1 + result.train_return) ** (365 / result.train_days) - 1 if result.train_days > 0 else 0
                },
                'test_performance': {
                    'return': result.test_return,
                    'days': result.test_days,
                    'period_start': result.test_period[0].isoformat(),
                    'period_end': result.test_period[1].isoformat(),
                    'annualized_return': (1 + result.test_return) ** (365 / result.test_days) - 1 if result.test_days > 0 else 0
                },
                'consistency_ratio': result.consistency_ratio
            }
        
        # 添加汇总统计
        if results:
            test_returns = [r.test_return for r in results.values()]
            train_returns = [r.train_return for r in results.values()]
            consistency_ratios = [r.consistency_ratio for r in results.values()]
            
            summary = {
                'optimization_info': {
                    'timestamp': datetime.now().isoformat(),
                    'total_symbols': len(results),
                    'test_days': self.test_days,
                    'method': 'Final Ultra Optimizer with Train/Test Split'
                },
                'summary_statistics': {
                    'train_performance': {
                        'average_return': float(np.mean(train_returns)),
                        'median_return': float(np.median(train_returns)),
                        'best_return': float(np.max(train_returns)),
                        'worst_return': float(np.min(train_returns))
                    },
                    'test_performance': {
                        'average_return': float(np.mean(test_returns)),
                        'median_return': float(np.median(test_returns)),
                        'best_return': float(np.max(test_returns)),
                        'worst_return': float(np.min(test_returns))
                    },
                    'consistency_analysis': {
                        'average_consistency': float(np.mean(consistency_ratios)),
                        'positive_test_returns': int(sum(1 for r in test_returns if r > 0))
                    }
                },
                'detailed_results': serializable_results
            }
        else:
            summary = {'detailed_results': serializable_results}
        
        # 保存文件
        try:
            project_root = os.path.dirname(os.path.dirname(__file__))
            filepath = os.path.join(project_root, 'data', filename)
            
            with open(filepath, 'w') as f:
                json.dump(summary, f, indent=2)
            
            logger.info(f"💾 Results saved to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            return ""

def print_final_results(results: Dict[str, OptimizationResult], top_n: int = 10):
    """打印最终优化结果"""
    if not results:
        print("No results to display")
        return
    
    # 按测试收益排序
    sorted_results = sorted(results.values(), key=lambda x: x.test_return, reverse=True)
    
    print("\n" + "="*80)
    print("🎯 FINAL ULTRA OPTIMIZER RESULTS (With Train/Test Split)")
    print("="*80)
    
    # 统计信息
    test_returns = [r.test_return for r in results.values()]
    train_returns = [r.train_return for r in results.values()]
    
    print(f"📊 SUMMARY STATISTICS:")
    print(f"   Total symbols: {len(results)}")
    print(f"   Average test return: {np.mean(test_returns):.2%}")
    print(f"   Best test return: {np.max(test_returns):.2%}")
    print(f"   Positive test returns: {sum(1 for r in test_returns if r > 0)}/{len(test_returns)}")
    
    print(f"\n🏆 TOP {min(top_n, len(sorted_results))} TEST PERFORMERS")
    print("="*80)
    print(f"{'Rank':<4} {'Symbol':<12} {'Train':<8} {'Test':<8} {'Ratio':<6} {'b%':<5} {'l%':<5} {'p%':<5} {'Test Days'}")
    print("-"*80)
    
    for i, result in enumerate(sorted_results[:top_n], 1):
        print(f"{i:<4} {result.symbol:<12} {result.train_return:>6.1%} {result.test_return:>6.1%} "
              f"{result.consistency_ratio:>5.2f} {result.best_params.buy_threshold*100:>4.1f} "
              f"{result.best_params.stop_loss*100:>4.1f} {result.best_params.take_profit*100:>4.1f} "
              f"{result.test_days:>8}")
    
    print(f"\n💡 KEY INSIGHTS:")
    print(f"   - Test returns are based on out-of-sample data (last {sorted_results[0].test_days if sorted_results else 90} days)")
    print(f"   - These are realistic performance expectations")
    print(f"   - No data leakage - parameters optimized on historical data only")
