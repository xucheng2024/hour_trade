#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy Tester
Comprehensive testing framework for strategy optimizer components
"""

import sys
import os
import numpy as np
from datetime import datetime

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from strategies.strategy_optimizer import StrategyOptimizer
from strategies.historical_data_loader import get_historical_data_loader

def test_data_loading():
    """Test historical data loading functionality"""
    print("🧪 Testing Data Loading")
    print("=" * 40)
    
    try:
        loader = get_historical_data_loader()
        data = loader.get_hist_candle_data('BTC-USDT', 0, 0, '1d')
        
        if data is not None:
            print(f"✅ Data loaded successfully")
            print(f"  Shape: {data.shape}")
            print(f"  Data type: {data.dtype}")
            print(f"  Sample open price: {data[0, 1]}")
        else:
            print("❌ Failed to load data")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def test_strategy_optimizer():
    """Test strategy optimizer functionality"""
    print("\n🧪 Testing Strategy Optimizer")
    print("=" * 40)
    
    try:
        # Test with relaxed constraints
        class RelaxedStrategyOptimizer(StrategyOptimizer):
            def _get_strategy_config(self, strategy_type: str):
                """Override with relaxed constraints"""
                if strategy_type == "1d":
                    return {
                        'limit_range': (60, 95),
                        'duration_range': 30,
                        'min_trades': 10,
                        'min_avg_earn': 1.005,
                        'data_offset': 20,
                        'time_window': 48,
                        'hour_mask': None,
                        'minute_mask': 0,
                        'second_mask': 0,
                        'buy_fee': self.custom_fees['buy_fee'],
                        'sell_fee': self.custom_fees['sell_fee']
                    }
                return super()._get_strategy_config(strategy_type)
        
        # Test optimization
        optimizer = RelaxedStrategyOptimizer()
        date_dict = {}
        result = optimizer.optimize_1d_strategy(
            instId='BTC-USDT',
            start=0,
            end=0,
            date_dict=date_dict,
            bar='1d'
        )
        
        if result and 'BTC-USDT' in result:
            crypto_result = result['BTC-USDT']
            print(f"✅ Strategy optimization successful:")
            print(f"  Best limit: {crypto_result.get('best_limit')}%")
            print(f"  Best duration: {crypto_result.get('best_duration')}")
            print(f"  Max returns: {crypto_result.get('max_returns')}")
        else:
            print(f"⚠️  Strategy optimization completed but no result")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def run_all_tests():
    """Run all tests"""
    print("🚀 Starting Strategy Testing Suite")
    print("=" * 50)
    
    test_data_loading()
    test_strategy_optimizer()
    
    print("\n" + "=" * 50)
    print("✅ All tests completed!")

if __name__ == "__main__":
    run_all_tests()
