#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
V-Pattern Parameter Optimizer
V型模式参数优化器 - 根据历史数据优化检测参数
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, NamedTuple
from dataclasses import dataclass
import logging
from datetime import datetime, timedelta
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

from v_pattern_detector import VPatternDetector, VPattern
from v_strategy_backtester import VReversalBacktester, BacktestResult

logger = logging.getLogger(__name__)

@dataclass
class OptimalParams:
    """优化后的参数"""
    symbol: str
    min_depth_pct: float
    max_depth_pct: float
    min_recovery_pct: float
    max_total_time: int
    max_recovery_time: int
    train_score: float
    train_patterns: int
    train_trades: int
    train_win_rate: float
    train_total_return: float

@dataclass
class ValidationResult:
    """验证结果"""
    symbol: str
    optimal_params: OptimalParams
    test_score: float
    test_patterns: int
    test_trades: int
    test_win_rate: float
    test_total_return: float
    test_sharpe_ratio: float
    consistency_ratio: float  # 测试/训练表现比率

class VPatternParameterOptimizer:
    """V型模式参数优化器"""
    
    def __init__(self, 
                 test_months: int = 3,           # 测试期3个月
                 min_train_months: int = 6,      # 最少训练期6个月
                 max_workers: int = 4):          # 并行工作线程数
        """
        初始化参数优化器
        
        Args:
            test_months: 测试期月数
            min_train_months: 最少训练期月数
            max_workers: 并行处理线程数
        """
        self.test_months = test_months
        self.min_train_months = min_train_months
        self.max_workers = max_workers
        
        # 定义参数优化范围
        self.param_grid = {
            'min_depth_pct': [0.02, 0.03, 0.04, 0.05],           # 2%-5%
            'max_depth_pct': [0.15, 0.20, 0.25, 0.30],           # 15%-30%
            'min_recovery_pct': [0.60, 0.70, 0.80, 0.90],        # 60%-90%
            'max_total_time': [24, 36, 48, 60],                  # 24-60小时
            'max_recovery_time': [12, 18, 24, 30]                # 12-30小时
        }
        
        logger.info(f"Parameter Optimizer initialized:")
        logger.info(f"  Test period: {test_months} months")
        logger.info(f"  Min training period: {min_train_months} months")
        logger.info(f"  Parameter combinations: {self._count_param_combinations()}")
        logger.info(f"  Max workers: {max_workers}")
    
    def _count_param_combinations(self) -> int:
        """计算参数组合总数"""
        count = 1
        for values in self.param_grid.values():
            count *= len(values)
        return count
    
    def split_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        分割训练和测试数据
        
        Args:
            df: 完整数据
            
        Returns:
            (训练数据, 测试数据)
        """
        if 'timestamp' not in df.columns:
            raise ValueError("DataFrame must contain 'timestamp' column")
        
        # 确保时间格式
        if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # 按时间排序
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # 计算分割点
        latest_time = df['timestamp'].max()
        split_time = latest_time - pd.Timedelta(days=self.test_months * 30)
        
        train_df = df[df['timestamp'] < split_time].copy()
        test_df = df[df['timestamp'] >= split_time].copy()
        
        # 验证数据量
        train_months = (train_df['timestamp'].max() - train_df['timestamp'].min()).days / 30
        test_months = (test_df['timestamp'].max() - test_df['timestamp'].min()).days / 30
        
        if train_months < self.min_train_months:
            raise ValueError(f"Insufficient training data: {train_months:.1f} months < {self.min_train_months}")
        
        logger.info(f"Data split: Train {len(train_df)} records ({train_months:.1f}m), "
                   f"Test {len(test_df)} records ({test_months:.1f}m)")
        
        return train_df, test_df
    
    def _evaluate_params(self, params: Dict, train_df: pd.DataFrame) -> Tuple[float, int, int, float, float]:
        """
        评估参数组合在训练数据上的表现
        
        Args:
            params: 参数字典
            train_df: 训练数据
            
        Returns:
            (评分, 模式数, 交易数, 胜率, 总收益)
        """
        try:
            # 创建检测器
            detector = VPatternDetector(
                min_depth_pct=params['min_depth_pct'],
                max_depth_pct=params['max_depth_pct'],
                min_recovery_pct=params['min_recovery_pct'],
                max_total_time=params['max_total_time'],
                max_recovery_time=params['max_recovery_time']
            )
            
            # 检测模式
            patterns = detector.detect_patterns(train_df)
            
            if len(patterns) == 0:
                return 0.0, 0, 0, 0.0, 0.0
            
            # 回测
            backtester = VReversalBacktester(holding_hours=20, min_pattern_quality=0.1)
            result = backtester.backtest_symbol(train_df, patterns)
            
            if result.total_trades == 0:
                return 0.0, len(patterns), 0, 0.0, 0.0
            
            # 计算综合评分
            # 基于胜率、平均收益、交易次数的综合评分
            win_rate_score = result.win_rate
            return_score = max(0, result.avg_return_per_trade / 0.05)  # 5%为满分
            frequency_score = min(1.0, result.total_trades / 20)  # 20笔交易为满分
            
            # 综合评分
            score = win_rate_score * 0.4 + return_score * 0.4 + frequency_score * 0.2
            
            return score, len(patterns), result.total_trades, result.win_rate, result.total_return
            
        except Exception as e:
            logger.warning(f"Error evaluating params {params}: {e}")
            return 0.0, 0, 0, 0.0, 0.0
    
    def optimize_single_symbol(self, symbol: str, df: pd.DataFrame) -> Optional[OptimalParams]:
        """
        优化单个币种的参数
        
        Args:
            symbol: 币种符号
            df: 价格数据
            
        Returns:
            最优参数或None
        """
        logger.info(f"Optimizing parameters for {symbol}...")
        
        try:
            # 分割数据
            train_df, test_df = self.split_data(df)
            
            # 生成所有参数组合
            param_names = list(self.param_grid.keys())
            param_values = list(self.param_grid.values())
            param_combinations = list(itertools.product(*param_values))
            
            logger.info(f"Testing {len(param_combinations)} parameter combinations for {symbol}")
            
            best_score = 0.0
            best_params = None
            best_stats = None
            
            # 逐个测试参数组合
            for i, combination in enumerate(param_combinations):
                params = dict(zip(param_names, combination))
                
                # 添加约束检查
                if params['min_depth_pct'] >= params['max_depth_pct']:
                    continue
                if params['max_recovery_time'] > params['max_total_time']:
                    continue
                
                score, patterns, trades, win_rate, total_return = self._evaluate_params(params, train_df)
                
                if score > best_score:
                    best_score = score
                    best_params = params
                    best_stats = (patterns, trades, win_rate, total_return)
                
                if (i + 1) % 50 == 0:
                    logger.info(f"  {symbol}: Tested {i+1}/{len(param_combinations)} combinations, "
                               f"best score: {best_score:.3f}")
            
            if best_params is None:
                logger.warning(f"No valid parameters found for {symbol}")
                return None
            
            patterns, trades, win_rate, total_return = best_stats
            
            optimal_params = OptimalParams(
                symbol=symbol,
                min_depth_pct=best_params['min_depth_pct'],
                max_depth_pct=best_params['max_depth_pct'],
                min_recovery_pct=best_params['min_recovery_pct'],
                max_total_time=best_params['max_total_time'],
                max_recovery_time=best_params['max_recovery_time'],
                train_score=best_score,
                train_patterns=patterns,
                train_trades=trades,
                train_win_rate=win_rate,
                train_total_return=total_return
            )
            
            logger.info(f"✅ {symbol} optimization complete: "
                       f"Score {best_score:.3f}, "
                       f"Patterns {patterns}, "
                       f"Trades {trades}, "
                       f"Win rate {win_rate:.1%}")
            
            return optimal_params
            
        except Exception as e:
            logger.error(f"Error optimizing {symbol}: {e}")
            return None
    
    def validate_optimized_params(self, optimal_params: OptimalParams, df: pd.DataFrame) -> Optional[ValidationResult]:
        """
        在测试数据上验证优化后的参数
        
        Args:
            optimal_params: 优化后的参数
            df: 完整数据
            
        Returns:
            验证结果或None
        """
        try:
            # 分割数据
            train_df, test_df = self.split_data(df)
            
            # 使用优化后的参数创建检测器
            detector = VPatternDetector(
                min_depth_pct=optimal_params.min_depth_pct,
                max_depth_pct=optimal_params.max_depth_pct,
                min_recovery_pct=optimal_params.min_recovery_pct,
                max_total_time=optimal_params.max_total_time,
                max_recovery_time=optimal_params.max_recovery_time
            )
            
            # 在测试数据上检测模式
            test_patterns = detector.detect_patterns(test_df)
            
            if len(test_patterns) == 0:
                logger.warning(f"No patterns detected in test data for {optimal_params.symbol}")
                return None
            
            # 回测
            backtester = VReversalBacktester(holding_hours=20, min_pattern_quality=0.1)
            test_result = backtester.backtest_symbol(test_df, test_patterns)
            
            if test_result.total_trades == 0:
                logger.warning(f"No trades executed in test data for {optimal_params.symbol}")
                return None
            
            # 计算测试评分
            win_rate_score = test_result.win_rate
            return_score = max(0, test_result.avg_return_per_trade / 0.05)
            frequency_score = min(1.0, test_result.total_trades / 20)
            test_score = win_rate_score * 0.4 + return_score * 0.4 + frequency_score * 0.2
            
            # 计算一致性比率
            consistency_ratio = test_score / optimal_params.train_score if optimal_params.train_score > 0 else 0
            
            validation_result = ValidationResult(
                symbol=optimal_params.symbol,
                optimal_params=optimal_params,
                test_score=test_score,
                test_patterns=len(test_patterns),
                test_trades=test_result.total_trades,
                test_win_rate=test_result.win_rate,
                test_total_return=test_result.total_return,
                test_sharpe_ratio=test_result.sharpe_ratio,
                consistency_ratio=consistency_ratio
            )
            
            return validation_result
            
        except Exception as e:
            logger.error(f"Error validating {optimal_params.symbol}: {e}")
            return None
    
    def optimize_multiple_symbols(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, OptimalParams]:
        """
        优化多个币种的参数
        
        Args:
            data_dict: 币种数据字典
            
        Returns:
            优化结果字典
        """
        logger.info(f"Starting parameter optimization for {len(data_dict)} symbols")
        
        optimized_params = {}
        
        for symbol, df in data_dict.items():
            optimal_params = self.optimize_single_symbol(symbol, df)
            if optimal_params:
                optimized_params[symbol] = optimal_params
        
        logger.info(f"✅ Parameter optimization completed for {len(optimized_params)}/{len(data_dict)} symbols")
        return optimized_params
    
    def run_full_optimization_and_validation(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, ValidationResult]:
        """
        运行完整的优化和验证流程
        
        Args:
            data_dict: 币种数据字典
            
        Returns:
            验证结果字典
        """
        logger.info(f"🚀 Starting full optimization and validation for {len(data_dict)} symbols")
        
        # 1. 参数优化
        optimized_params = self.optimize_multiple_symbols(data_dict)
        
        if not optimized_params:
            logger.error("No parameters optimized successfully")
            return {}
        
        # 2. 验证
        logger.info(f"📊 Validating optimized parameters on test data...")
        validation_results = {}
        
        for symbol, params in optimized_params.items():
            if symbol in data_dict:
                validation_result = self.validate_optimized_params(params, data_dict[symbol])
                if validation_result:
                    validation_results[symbol] = validation_result
        
        logger.info(f"✅ Validation completed for {len(validation_results)}/{len(optimized_params)} symbols")
        return validation_results
    
    def save_optimization_results(self, validation_results: Dict[str, ValidationResult], 
                                filename: Optional[str] = None) -> str:
        """保存优化结果"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"v_pattern_optimization_{timestamp}.json"
        
        # 准备可序列化的结果
        serializable_results = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_months": self.test_months,
                "min_train_months": self.min_train_months,
                "total_symbols": len(validation_results),
                "param_grid": self.param_grid
            },
            "results": {}
        }
        
        for symbol, result in validation_results.items():
            serializable_results["results"][symbol] = {
                "optimal_parameters": {
                    "min_depth_pct": result.optimal_params.min_depth_pct,
                    "max_depth_pct": result.optimal_params.max_depth_pct,
                    "min_recovery_pct": result.optimal_params.min_recovery_pct,
                    "max_total_time": result.optimal_params.max_total_time,
                    "max_recovery_time": result.optimal_params.max_recovery_time
                },
                "training_performance": {
                    "score": result.optimal_params.train_score,
                    "patterns": result.optimal_params.train_patterns,
                    "trades": result.optimal_params.train_trades,
                    "win_rate": result.optimal_params.train_win_rate,
                    "total_return": result.optimal_params.train_total_return
                },
                "test_performance": {
                    "score": result.test_score,
                    "patterns": result.test_patterns,
                    "trades": result.test_trades,
                    "win_rate": result.test_win_rate,
                    "total_return": result.test_total_return,
                    "sharpe_ratio": result.test_sharpe_ratio,
                    "consistency_ratio": result.consistency_ratio
                }
            }
        
        # 保存到data目录
        import os
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_dir = os.path.join(parent_dir, 'data')
        results_path = os.path.join(data_dir, filename)
        
        with open(results_path, 'w') as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Optimization results saved to: {results_path}")
        return results_path


def print_optimization_summary(validation_results: Dict[str, ValidationResult]):
    """打印优化结果摘要"""
    if not validation_results:
        print("❌ No optimization results")
        return
    
    print(f"\n🎯 V-Pattern Parameter Optimization Results")
    print("=" * 100)
    print(f"{'Symbol':<12} {'Train Score':<11} {'Test Score':<10} {'Consistency':<11} "
          f"{'Test Win%':<9} {'Test Return':<11} {'Test Trades':<11}")
    print("-" * 100)
    
    for symbol, result in validation_results.items():
        print(f"{symbol:<12} {result.optimal_params.train_score:>10.3f} "
              f"{result.test_score:>9.3f} {result.consistency_ratio:>10.2f} "
              f"{result.test_win_rate:>8.1%} {result.test_total_return:>10.2%} "
              f"{result.test_trades:>10}")
    
    # 汇总统计
    all_results = list(validation_results.values())
    avg_train_score = np.mean([r.optimal_params.train_score for r in all_results])
    avg_test_score = np.mean([r.test_score for r in all_results])
    avg_consistency = np.mean([r.consistency_ratio for r in all_results])
    avg_test_win_rate = np.mean([r.test_win_rate for r in all_results])
    avg_test_return = np.mean([r.test_total_return for r in all_results])
    total_test_trades = sum([r.test_trades for r in all_results])
    
    print("-" * 100)
    print(f"{'AVERAGE':<12} {avg_train_score:>10.3f} {avg_test_score:>9.3f} "
          f"{avg_consistency:>10.2f} {avg_test_win_rate:>8.1%} "
          f"{avg_test_return:>10.2%} {total_test_trades:>10}")


if __name__ == "__main__":
    # 测试参数优化器
    logging.basicConfig(level=logging.INFO)
    
    print("🚀 Testing V-Pattern Parameter Optimizer")
    
    # 这里可以加载实际数据进行测试
    # from data_loader import VReversalDataLoader
    # 
    # loader = VReversalDataLoader()
    # data = loader.load_multiple_symbols(['BTC-USDT', 'ETH-USDT'], months=9)
    # 
    # optimizer = VPatternParameterOptimizer()
    # results = optimizer.run_full_optimization_and_validation(data)
    # print_optimization_summary(results)

