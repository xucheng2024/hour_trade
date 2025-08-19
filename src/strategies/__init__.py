"""
Trading strategies module.
Contains various trading strategies and limit calculation algorithms.
"""



from .historical_data_loader import get_historical_data_loader, HistoricalDataLoader


from .strategy_optimizer import get_strategy_optimizer, StrategyOptimizer

# ==================== COMPATIBILITY FUNCTIONS ====================
# These functions maintain backward compatibility

def best_limit(instId: str, start: int, end: int, bar: str):
    """Calculate best buy limit price - backward compatibility"""
    result = get_strategy_optimizer().optimize_1d_strategy(instId, start, end, {}, bar)
    if result and instId in result:
        best_limit_val = float(result[instId]['best_limit']) / 100
        max_median = float(result[instId]['max_value'])
        return best_limit_val, max_median
    return None, None

def hour_cryptos(instId: str, start: int, end: int, date_dict: dict, bar: str):
    """1-hour limit duration strategy - backward compatibility"""
    return get_strategy_optimizer().optimize_1h_strategy(instId, start, end, date_dict, bar)

__all__ = [
    # Core modules
    'HistoricalDataLoader',
    'StrategyOptimizer',
    
    # Singleton getters
    'get_historical_data_loader',
    'get_strategy_optimizer',
    
    # Compatibility functions
    'best_limit',
    'hour_cryptos'
]
