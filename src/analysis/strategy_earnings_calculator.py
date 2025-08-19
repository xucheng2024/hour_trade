#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy Earnings Calculator
Calculate potential earnings from daily and hourly strategies over the past year
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import numpy as np
import pandas as pd

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.strategies.strategy_optimizer import get_strategy_optimizer
from src.data.data_manager import load_crypto_list

class StrategyEarningsCalculator:
    """Calculate potential earnings from trading strategies over time periods"""
    
    def __init__(self, initial_capital: float = 100.0, trading_fee: float = 0.001):
        """
        Initialize the calculator
        
        Args:
            initial_capital: Starting capital in USDT
            trading_fee: Trading fee per trade (0.1% = 0.001)
        """
        self.initial_capital = initial_capital
        self.trading_fee = trading_fee
        self.optimizer = get_strategy_optimizer(buy_fee=trading_fee, sell_fee=trading_fee)
        
    def calculate_strategy_earnings(self, strategy_type: str = 'daily', 
                                  time_period: str = '1y') -> Dict[str, Any]:
        """
        Calculate earnings for a specific strategy over a time period
        
        Args:
            strategy_type: 'daily' or 'hourly'
            time_period: '1y', '6m', '3m', '1m'
            
        Returns:
            Dictionary with earnings analysis results
        """
        print(f"💰 Calculating {strategy_type} strategy earnings over {time_period}")
        
        # Load cryptocurrency list
        cryptos = load_crypto_list()
        if not cryptos:
            print("❌ No cryptocurrencies found in the list")
            return {}
        
        # Calculate time period
        end_date = datetime.now()
        start_date = self._get_start_date(end_date, time_period)
        
        print(f"📅 Analysis period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        print(f"🔍 Analyzing {len(cryptos)} cryptocurrencies")
        
        # Results storage
        results = {
            'strategy_type': strategy_type,
            'time_period': time_period,
            'analysis_period': {
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'days': (end_date - start_date).days
            },
            'initial_capital': self.initial_capital,
            'trading_fee': self.trading_fee,
            'cryptocurrencies': {},
            'summary': {
                'total_analyzed': 0,
                'successful_trades': 0,
                'no_trade_opportunities': 0,
                'failed_analysis': 0,
                'total_earnings': 0.0,
                'final_capital': 0.0,
                'total_return_percentage': 0.0,
                'annualized_return': 0.0,
                'best_performers': [],
                'worst_performers': []
            }
        }
        
        # Analyze each cryptocurrency
        for i, crypto in enumerate(cryptos, 1):
            print(f"\n📈 Analyzing {i}/{len(cryptos)}: {crypto}")
            
            try:
                if strategy_type == 'daily':
                    crypto_result = self._analyze_daily_strategy(crypto, start_date, end_date)
                else:
                    crypto_result = self._analyze_hourly_strategy(crypto, start_date, end_date)
                
                if crypto_result:
                    results['cryptocurrencies'][crypto] = crypto_result
                    results['summary']['total_analyzed'] += 1
                    
                    if crypto_result['status'] == 'success':
                        results['summary']['successful_trades'] += 1
                        results['summary']['total_earnings'] += crypto_result['annual_earnings']
                        
                        if results['strategy_type'] == 'daily':
                            print(f"  ✅ Success: Limit={crypto_result['best_limit']}%, "
                                  f"Duration={crypto_result['best_duration']} days, "
                                  f"Total trades: {crypto_result.get('trade_count', 0)}, "
                                  f"Monthly trades: {crypto_result['trades_per_month']:.1f}, "
                                  f"Annual earnings: {int(crypto_result['annual_earnings'])} USDT")
                        else:  # hourly
                            print(f"  ✅ Success: Limit={crypto_result['best_limit']}%, "
                                  f"Duration={crypto_result['best_duration']} hours, "
                                  f"Total trades: {crypto_result.get('trade_count', 0)}, "
                                  f"Monthly trades: {crypto_result['trades_per_month']:.1f}, "
                                  f"Annual earnings: {int(crypto_result['annual_earnings'])} USDT")
                    elif crypto_result['status'] == 'no_opportunities':
                        results['summary']['no_trade_opportunities'] += 1
                        print(f"  ⚠️  No trading opportunities found")
                    else:
                        results['summary']['failed_analysis'] += 1
                        print(f"  ❌ Analysis failed: {crypto_result.get('error', 'Unknown error')}")
                else:
                    results['cryptocurrencies'][crypto] = {
                        'status': 'failed',
                        'error': 'No result returned'
                    }
                    results['summary']['failed_analysis'] += 1
                    print(f"  ❌ No result returned")
                    
            except Exception as e:
                results['cryptocurrencies'][crypto] = {
                    'status': 'error',
                    'error': str(e)
                }
                results['summary']['failed_analysis'] += 1
                print(f"  ❌ Error: {e}")
        
        # Calculate final summary
        self._calculate_final_summary(results)
        
        return results
    
    def _analyze_daily_strategy(self, crypto: str, start_date: datetime, 
                               end_date: datetime) -> Dict[str, Any]:
        """Analyze daily strategy for a specific cryptocurrency using historical trade simulation"""
        try:
            # Get best strategy parameters and trade statistics
            result = self._optimize_with_relaxed_params(crypto, '1d')
            
            if result and crypto in result:
                crypto_result = result[crypto]
                best_limit = int(crypto_result.get('best_limit', 0))
                best_duration = int(crypto_result.get('best_duration', 0))
                max_returns = float(crypto_result.get('max_returns', 0))
                
                if max_returns > 1.0:
                    # Get trade frequency directly from optimizer results
                    trade_count = int(crypto_result.get('trade_count', 0))
                    trades_per_month = float(crypto_result.get('trades_per_month', 0))
                    
                    if trade_count > 0:
                        # Calculate annual earnings using optimizer's results
                        trades_per_year = trades_per_month * 12
                        profit_per_trade = self.initial_capital * (max_returns - 1.0)
                        annual_earnings = trades_per_year * profit_per_trade
                        
                        return {
                            'status': 'success',
                            'best_limit': best_limit,
                            'best_duration': best_duration,
                            'max_returns': max_returns,
                            'trade_count': trade_count,
                            'trades_per_month': trades_per_month,
                            'trades_per_year': trades_per_year,
                            'profit_per_trade': profit_per_trade,
                            'annual_earnings': annual_earnings,
                            'projected_final_capital': self.initial_capital + annual_earnings
                        }
                    else:
                        return {
                            'status': 'no_opportunities',
                            'reason': 'No actual trading opportunities found in historical data'
                        }
                else:
                    return {
                        'status': 'no_opportunities',
                        'reason': 'Returns too low for profitable trading',
                        'max_returns': max_returns
                    }
            else:
                return {
                    'status': 'no_opportunities',
                    'reason': 'No valid strategy parameters found'
                }
                
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _analyze_hourly_strategy(self, crypto: str, start_date: datetime, 
                                end_date: datetime) -> Dict[str, Any]:
        """Analyze hourly strategy for a specific cryptocurrency using historical trade simulation"""
        try:
            # Use relaxed parameters for better coverage
            result = self._optimize_with_relaxed_params(crypto, '1h')
            
            if result and crypto in result:
                crypto_result = result[crypto]
                best_limit = int(crypto_result.get('best_limit', 0))
                best_duration = int(crypto_result.get('best_duration', 0))
                max_returns = float(crypto_result.get('max_returns', 0))
                
                if max_returns > 1.0:
                    # Get trade frequency directly from optimizer results
                    trade_count = int(crypto_result.get('trade_count', 0))
                    trades_per_month = float(crypto_result.get('trades_per_month', 0))
                    
                    if trade_count > 0:
                        # Calculate annual earnings using optimizer's results
                        trades_per_year = trades_per_month * 12
                        profit_per_trade = self.initial_capital * (max_returns - 1.0)
                        annual_earnings = trades_per_year * profit_per_trade
                        
                        return {
                            'status': 'success',
                            'best_limit': best_limit,
                            'best_duration': best_duration,
                            'max_returns': max_returns,
                            'trade_count': trade_count,
                            'trades_per_month': trades_per_month,
                            'trades_per_year': trades_per_year,
                            'profit_per_trade': profit_per_trade,
                            'annual_earnings': annual_earnings,
                            'projected_final_capital': self.initial_capital + annual_earnings
                        }
                    else:
                        return {
                            'status': 'no_opportunities',
                            'reason': 'No actual trading opportunities found in historical data'
                        }
                else:
                    return {
                        'status': 'no_opportunities',
                        'reason': 'Returns too low for profitable trading',
                        'max_returns': max_returns
                    }
            else:
                return {
                    'status': 'no_opportunities',
                    'reason': 'No valid strategy parameters found'
                }
                
        except Exception as e:
            return {
                'status': 'failed',
                'error': str(e)
            }
    
    def _simulate_historical_trades(self, crypto: str, limit_ratio: int, duration: int, 
                                  timeframe: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Simulate historical trades using actual strategy parameters"""
        try:
            import os
            import numpy as np
            import pandas as pd
            
            # Load historical data for the cryptocurrency
            if timeframe == '1d':
                bar = '1D'
            else:
                bar = '1H'
            
            # Load data from file
            data_file = f"data/{crypto}_{bar}.npz"
            if not os.path.exists(data_file):
                return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
            
            # Load and process data
            data = np.load(data_file)
            if 'data' in data:
                candles = data['data']
            else:
                candles = data['arr_0']  # Default numpy save format
            
            # Convert to datetime and filter by date range
            timestamps = pd.to_datetime(candles[:, 0], unit='ms')
            mask = (timestamps >= start_date) & (timestamps <= end_date)
            filtered_candles = candles[mask]
            
            if len(filtered_candles) == 0:
                return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
            
            # Extract OHLC data
            opens = filtered_candles[:, 2].astype(float)
            highs = filtered_candles[:, 3].astype(float)
            lows = filtered_candles[:, 4].astype(float)
            closes = filtered_candles[:, 5].astype(float)
            
            # Simulate trades based on strategy parameters
            trades = []
            i = 0
            
            while i < len(filtered_candles) - duration:
                # Check if buy condition is met (price drops to limit ratio)
                current_open = opens[i]
                buy_price = current_open * (limit_ratio / 100)
                
                # Check if low price reached buy price
                if lows[i] <= buy_price:
                    # Simulate buy at buy_price
                    # Check if sell condition is met after duration
                    if i + duration < len(filtered_candles):
                        sell_price = closes[i + duration]
                        trade_return = sell_price / buy_price
                        trades.append(trade_return)
                        i += duration + 1  # Skip to next potential trade (avoid overlap)
                    else:
                        break
                else:
                    i += 1
            
            if trades:
                successful_trades = [t for t in trades if t > 1.0]
                success_rate = len(successful_trades) / len(trades) if trades else 0
                avg_return = np.mean(trades) if trades else 0
                
                return {
                    'total_trades': len(trades),
                    'successful_trades': len(successful_trades),
                    'avg_return': avg_return,
                    'success_rate': success_rate
                }
            else:
                return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
                
        except Exception as e:
            print(f"Error simulating trades for {crypto}: {e}")
            return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
    
    def _optimize_with_relaxed_params(self, crypto: str, strategy_type: str) -> Dict[str, Any]:
        """Optimize strategy with relaxed parameters for better coverage"""
        class RelaxedStrategyOptimizer:
            def __init__(self, base_optimizer, strategy_type):
                self.base_optimizer = base_optimizer
                self.strategy_type = strategy_type
                
            def optimize(self, instId, start, end, date_dict, bar):
                # Override config with relaxed parameters
                original_method = self.base_optimizer._get_strategy_config
                
                def relaxed_config(strategy_type):
                    if strategy_type == self.strategy_type:
                        return {
                            'limit_range': (60, 99),
                            'duration_range': 30,
                            'min_trades': 20,        # Reduced for better coverage
                            'min_avg_earn': 1.001,   # Very low minimum for coverage
                            'data_offset': 20,       # Reduced for better coverage
                            'time_window': 1,
                            'hour_mask': None,
                            'minute_mask': None,
                            'second_mask': None,
                            'buy_fee': 0.001,
                            'sell_fee': 0.001
                        }
                    return original_method(strategy_type)
                
                self.base_optimizer._get_strategy_config = relaxed_config
                
                if self.strategy_type == '1d':
                    result = self.base_optimizer.optimize_1d_strategy(instId, start, end, date_dict, bar)
                else:
                    result = self.base_optimizer.optimize_1h_strategy(instId, start, end, date_dict, bar)
                
                self.base_optimizer._get_strategy_config = original_method
                return result
        
        relaxed_optimizer = RelaxedStrategyOptimizer(self.optimizer, strategy_type)
        return relaxed_optimizer.optimize(crypto, 0, 0, {}, strategy_type)
    
    def _simulate_historical_trades(self, crypto: str, limit_ratio: int, duration: int, 
                                  timeframe: str, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Simulate historical trades using actual strategy parameters"""
        try:
            # Load historical data for the cryptocurrency
            from src.data.data_manager import OKXDataManager
            data_manager = OKXDataManager()
            
            # Get historical candlestick data
            if timeframe == '1d':
                bar = '1D'
            else:
                bar = '1H'
            
            # Load data from file (assuming data exists)
            data_file = f"data/{crypto}_{bar}.npz"
            if not os.path.exists(data_file):
                return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
            
            # Load and process data
            data = np.load(data_file)
            if 'data' in data:
                candles = data['data']
            else:
                candles = data['arr_0']  # Default numpy save format
            
            # Convert to datetime and filter by date range
            timestamps = pd.to_datetime(candles[:, 0], unit='ms')
            mask = (timestamps >= start_date) & (timestamps <= end_date)
            filtered_candles = candles[mask]
            
            if len(filtered_candles) == 0:
                return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
            
            # Extract OHLC data
            opens = filtered_candles[:, 2].astype(float)
            highs = filtered_candles[:, 3].astype(float)
            lows = filtered_candles[:, 4].astype(float)
            closes = filtered_candles[:, 5].astype(float)
            
            # Simulate trades based on strategy parameters
            trades = []
            i = 0
            
            while i < len(filtered_candles) - duration:
                # Check if buy condition is met (price drops to limit ratio)
                current_open = opens[i]
                buy_price = current_open * (limit_ratio / 100)
                
                # Check if low price reached buy price
                if lows[i] <= buy_price:
                    # Simulate buy at buy_price
                    # Check if sell condition is met after duration
                    if i + duration < len(filtered_candles):
                        sell_price = closes[i + duration]
                        trade_return = sell_price / buy_price
                        trades.append(trade_return)
                        i += duration + 1  # Skip to next potential trade
                    else:
                        break
                else:
                    i += 1
            
            if trades:
                successful_trades = [t for t in trades if t > 1.0]
                success_rate = len(successful_trades) / len(trades) if trades else 0
                avg_return = np.mean(trades) if trades else 0
                
                return {
                    'total_trades': len(trades),
                    'successful_trades': len(successful_trades),
                    'avg_return': avg_return,
                    'success_rate': success_rate
                }
            else:
                return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
                
        except Exception as e:
            print(f"Error simulating trades for {crypto}: {e}")
            return {'total_trades': 0, 'successful_trades': 0, 'avg_return': 0, 'success_rate': 0}
    
    def _get_start_date(self, end_date: datetime, time_period: str) -> datetime:
        """Calculate start date based on time period"""
        if time_period == '1y':
            return end_date - timedelta(days=365)
        elif time_period == '6m':
            return end_date - timedelta(days=180)
        elif time_period == '3m':
            return end_date - timedelta(days=90)
        elif time_period == '1m':
            return end_date - timedelta(days=30)
        else:
            return end_date - timedelta(days=365)  # Default to 1 year
    
    def _calculate_final_summary(self, results: Dict[str, Any]) -> None:
        """Calculate final summary statistics"""
        successful_cryptos = []
        
        for crypto, data in results['cryptocurrencies'].items():
            if data['status'] == 'success':
                successful_cryptos.append((crypto, data['annual_earnings']))
        
        if successful_cryptos:
            # Sort by earnings (descending)
            successful_cryptos.sort(key=lambda x: x[1], reverse=True)
            
            # Top performers
            results['summary']['best_performers'] = [
                {'crypto': crypto, 'earnings': earnings} 
                for crypto, earnings in successful_cryptos[:10]
            ]
            
            # Worst performers
            results['summary']['worst_performers'] = [
                {'crypto': crypto, 'earnings': earnings} 
                for crypto, earnings in successful_cryptos[-10:]
            ]
        
        # Calculate average earnings and final capital
        if results['summary']['successful_trades'] > 0:
            results['summary']['average_annual_earnings'] = results['summary']['total_earnings'] / results['summary']['successful_trades']
            results['summary']['final_capital'] = self.initial_capital + results['summary']['average_annual_earnings']
            results['summary']['total_return_percentage'] = (results['summary']['average_annual_earnings'] / self.initial_capital) * 100
        else:
            results['summary']['average_annual_earnings'] = 0
            results['summary']['final_capital'] = self.initial_capital
            results['summary']['total_return_percentage'] = 0
        
        # Calculate annualized return
        days = results['analysis_period']['days']
        if days > 0:
            results['summary']['annualized_return'] = ((results['summary']['final_capital'] / self.initial_capital) ** (365 / days) - 1) * 100
        
        # Print summary
        print(f"\n📊 Earnings Summary:")
        print(f"  Initial Capital: {int(self.initial_capital)} USDT")
        print(f"  Average Annual Earnings: {int(results['summary']['average_annual_earnings'])} USDT")
        print(f"  Projected Final Capital: {int(results['summary']['final_capital'])} USDT")
        print(f"  Total Return: {results['summary']['total_return_percentage']:.2f}%")
        print(f"  Annualized Return: {results['summary']['annualized_return']:.2f}%")
        print(f"  Successful Strategies: {results['summary']['successful_trades']}")
        print(f"  No Opportunities: {results['summary']['no_trade_opportunities']}")
        print(f"  Failed Analysis: {results['summary']['failed_analysis']}")
        print(f"  Note: Final capital based on average earnings from {results['summary']['successful_trades']} strategies")
        
        if results['summary']['best_performers']:
            print(f"\n🏆 Top 5 Performers:")
            for i, performer in enumerate(results['summary']['best_performers'][:5], 1):
                print(f"  {i}. {performer['crypto']}: {int(performer['earnings'])} USDT")
    
    def save_results(self, results: Dict[str, Any], filename: str = None) -> str:
        """Save analysis results to file"""
        # Create data directory if it doesn't exist
        data_dir = 'data'
        os.makedirs(data_dir, exist_ok=True)
        
        # Generate filename with timestamp
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            strategy_type = results['strategy_type']
            time_period = results['time_period']
            filename = f"strategy_earnings_{strategy_type}_{time_period}_{timestamp}.json"
        
        filepath = os.path.join(data_dir, filename)
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            print(f"\n💾 Results saved to: {filepath}")
            return filepath
        except Exception as e:
            print(f"\n❌ Error saving results: {e}")
            return ""

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Calculate strategy earnings over time periods')
    parser.add_argument('--strategy', choices=['daily', 'hourly'], default='daily',
                       help='Strategy type (daily or hourly)')
    parser.add_argument('--period', choices=['1y', '6m', '3m', '1m'], default='1y',
                       help='Time period for analysis')
    parser.add_argument('--capital', type=float, default=10000.0,
                       help='Initial capital in USDT')
    parser.add_argument('--fee', type=float, default=0.001,
                       help='Trading fee per trade (0.1% = 0.001)')
    
    args = parser.parse_args()
    
    print("🚀 Strategy Earnings Calculator")
    print("=" * 50)
    
    # Initialize calculator
    calculator = StrategyEarningsCalculator(
        initial_capital=args.capital,
        trading_fee=args.fee
    )
    
    # Calculate earnings
    results = calculator.calculate_strategy_earnings(
        strategy_type=args.strategy,
        time_period=args.period
    )
    
    # Save results
    if results:
        calculator.save_results(results)
    
    print("\n" + "=" * 50)
    print("✅ Strategy Earnings Analysis Completed!")
    
    return results

if __name__ == "__main__":
    main()
