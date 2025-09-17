"""
Research module for cryptocurrency trading strategy optimization.
Final ultra-high performance system with proper train/test methodology.

Usage:
    python -m research.run_final_optimization
"""

from .data_loader import CryptoDataLoader
from .final_ultra_optimizer import FinalUltraOptimizer, OptimizationResult, BacktestParams, print_final_results

__all__ = [
    'CryptoDataLoader',
    'FinalUltraOptimizer',
    'OptimizationResult', 
    'BacktestParams',
    'print_final_results'
]
