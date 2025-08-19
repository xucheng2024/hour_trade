#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strategy Backtest Analyzer
Simulate and analyze the performance of daily trading strategies over past N days
"""

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

class StrategyBacktestAnalyzer:
    """Simulate and analyze N-day strategy performance for each cryptocurrency"""
    
    def __init__(self, investment_amount: float = 100.0, trading_fee: float = 0.001, days: int = 30):
        """
        Initialize the analyzer
        
        Args:
            investment_amount: Investment amount per cryptocurrency in USDT
            trading_fee: Trading fee per trade (0.1% = 0.001)
            days: Number of days to analyze (default: 30)
        """
        self.investment_amount = investment_amount
        self.trading_fee = trading_fee
        self.days = days
        self.optimizer = get_strategy_optimizer(buy_fee=trading_fee, sell_fee=trading_fee)
        
    def run_backtest(self) -> Dict[str, Any]:
        """
        Run N-day strategy backtest simulation
        
        Returns:
            Dictionary with backtest results for each cryptocurrency
        """
        print(f"🎯 Running {self.days}-day strategy backtest simulation")
        print(f"💰 Investment amount per crypto: ${self.investment_amount}")
        print(f"💸 Trading fee: {self.trading_fee * 100:.1f}%")
        print(f"📅 Backtest period: Past {self.days} days")
        
        # Load cryptocurrency list
        cryptos = load_crypto_list()
        if not cryptos:
            print("❌ No cryptocurrencies found in the list")
            return {}
        
        print(f"🔍 Analyzing {len(cryptos)} cryptocurrencies")
        
        # Results storage
        results = {
            'backtest_period': {
                'description': f'{self.days}-day strategy backtest simulation',
                'timestamp': datetime.now().isoformat()
            },
            'investment_amount': self.investment_amount,
            'trading_fee': self.trading_fee,
            'cryptocurrencies': {},
            'summary': {
                'total_analyzed': 0,
                'successful_analysis': 0,
                'failed_analysis': 0,
                'total_investment': 0.0,
                'total_final_value': 0.0,
                'total_profit_loss': 0.0,
                'total_return_percentage': 0.0,
                'best_performers': [],
                'worst_performers': [],
                'profitable_cryptos': 0,
                'losing_cryptos': 0
            }
        }
        
        # Analyze each cryptocurrency
        for i, crypto in enumerate(cryptos, 1):
            print(f"\n📈 Analyzing {i}/{len(cryptos)}: {crypto}")
            
            try:
                crypto_result = self._run_crypto_backtest(crypto)
                
                if crypto_result:
                    results['cryptocurrencies'][crypto] = crypto_result
                    results['summary']['successful_analysis'] += 1
                    
                    # Update summary statistics
                    final_value = crypto_result['final_value']
                    profit_loss = crypto_result['profit_loss']
                    return_pct = crypto_result['return_percentage']
                    
                    results['summary']['total_final_value'] += final_value
                    results['summary']['total_profit_loss'] += profit_loss
                    
                    if profit_loss > 0:
                        results['summary']['profitable_cryptos'] += 1
                    else:
                        results['summary']['losing_cryptos'] += 1
                    
                    # Track best and worst performers
                    if not results['summary']['best_performers'] or return_pct > results['summary']['best_performers'][0]['return']:
                        results['summary']['best_performers'].insert(0, {
                            'crypto': crypto,
                            'return': return_pct,
                            'profit_loss': profit_loss
                        })
                        results['summary']['best_performers'] = results['summary']['best_performers'][:5]  # Keep top 5
                    
                    if not results['summary']['worst_performers'] or return_pct < results['summary']['worst_performers'][0]['return']:
                        results['summary']['worst_performers'].insert(0, {
                            'crypto': crypto,
                            'return': return_pct,
                            'profit_loss': profit_loss
                        })
                        results['summary']['worst_performers'] = results['summary']['worst_performers'][:5]  # Keep bottom 5
                    
                    print(f"✅ {crypto}: {return_pct:+.2f}% (${profit_loss:+.2f})")
                else:
                    results['summary']['failed_analysis'] += 1
                    print(f"❌ {crypto}: Analysis failed")
                    
            except Exception as e:
                print(f"❌ {crypto}: Error - {e}")
                results['summary']['failed_analysis'] += 1
                
            results['summary']['total_analyzed'] += 1
        
        # Calculate final summary
        results['summary']['total_investment'] = len(results['cryptocurrencies']) * self.investment_amount
        if results['summary']['total_investment'] > 0:
            results['summary']['total_return_percentage'] = (
                (results['summary']['total_final_value'] - results['summary']['total_investment']) / 
                results['summary']['total_investment'] * 100
            )
        
        # Print summary
        self._print_summary(results)
        
        return results
    
    def _analyze_crypto_past_days(self, crypto: str) -> Dict[str, Any]:
        """
        Analyze a single cryptocurrency using past N days of data
        
        Args:
            crypto: Cryptocurrency symbol
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Load trading configuration
            config_file = os.path.join(os.path.dirname(__file__), '..', 'config', 'trading_config.json')
            
            if not os.path.exists(config_file):
                print(f"❌ Trading configuration not found: {config_file}")
                return None
            
            with open(config_file, 'r', encoding='utf-8') as f:
                trading_config = json.load(f)
            
            # Get configuration for this cryptocurrency
            crypto_config = trading_config.get('cryptocurrencies', {}).get(crypto)
            if not crypto_config:
                print(f"❌ No configuration found for {crypto}")
                return None
            
            limit = crypto_config.get('limit', '0')
            duration = crypto_config.get('duration', '0')
            
            print(f"   Using config: limit={limit}%, duration={duration} days")
            
            # Use past 30 days data with fixed parameters from config
            date_dict = {}
            
            # Test the configured strategy on past N days data
            # We simulate trading using the existing config parameters
            result = self._simulate_strategy_with_params(
                crypto=crypto,
                limit_ratio=int(limit),
                duration=int(duration),
                start=self.days,  # Use past N days
                end=0      # Up to now
            )
            
            if not result:
                return None
            
            # Extract key metrics from the nested result structure
            crypto_result = result.get(crypto, {})
            best_limit = crypto_result.get('best_limit', '0')
            best_duration = crypto_result.get('best_duration', '0')
            max_returns = float(crypto_result.get('max_returns', '0.0'))
            trade_count = int(crypto_result.get('trade_count', '0'))
            trades_per_month = float(crypto_result.get('trades_per_month', '0.0'))
            
            # Calculate returns based on investment amount
            initial_value = self.investment_amount
            final_value = initial_value * max_returns
            profit_loss = final_value - initial_value
            return_percentage = (max_returns - 1) * 100
            
            return {
                'crypto': crypto,
                'initial_value': initial_value,
                'final_value': final_value,
                'profit_loss': profit_loss,
                'return_percentage': return_percentage,
                'best_limit': best_limit,
                'best_duration': best_duration,
                'max_returns': max_returns,
                'trade_count': trade_count,
                'trades_per_month': trades_per_month,
                'analysis_success': True
            }
            
        except Exception as e:
            print(f"Error analyzing {crypto}: {e}")
            return None
    
    def _simulate_strategy_with_params(self, crypto: str, limit_ratio: int, duration: int, 
                                     start: int, end: int) -> Dict[str, Any]:
        """
        Simulate trading strategy with fixed parameters on historical data
        
        Args:
            crypto: Cryptocurrency symbol
            limit_ratio: Buy limit percentage (e.g., 70 means buy at 70% of open price)
            duration: Holding duration in days
            start: Start offset (30 for past 30 days)
            end: End offset (0 for up to now)
            
        Returns:
            Simulation results
        """
        try:
            # Get fresh 30-day data from OKX API
            data = self._get_fresh_30day_data(crypto)
            if data is None or len(data) == 0:
                print(f"   ❌ No fresh data available for {crypto}")
                return None
            
            # Extract price data
            open_prices = data[:, 1].astype(np.float64)
            low_prices = data[:, 3].astype(np.float64) 
            close_prices = data[:, 4].astype(np.float64)
            
            print(f"   📊 Data: {len(data)} days, prices: {open_prices[0]:.2f} - {open_prices[-1]:.2f}")
            
            # Simulate trades
            trades = []
            total_return = 1.0
            
            for i in range(len(data) - duration):
                # Calculate buy price at limit ratio
                buy_price = open_prices[i] * (limit_ratio / 100.0)
                
                # Check if low price on day i allows buying at our limit
                if low_prices[i] <= buy_price:
                    # We can buy at our limit price
                    # Sell after duration days
                    sell_idx = i + duration
                    if sell_idx < len(close_prices):
                        sell_price = close_prices[sell_idx]
                        
                        # Calculate return including fees
                        buy_fee = buy_price * self.trading_fee
                        sell_fee = sell_price * self.trading_fee
                        net_buy_price = buy_price + buy_fee
                        net_sell_price = sell_price - sell_fee
                        
                        trade_return = net_sell_price / net_buy_price
                        total_return *= trade_return
                        
                        trades.append({
                            'day': i,
                            'buy_price': buy_price,
                            'sell_price': sell_price,
                            'return': trade_return
                        })
            
            if not trades:
                print(f"   ❌ No trades executed for {crypto}")
                return None
            
            # Calculate metrics
            trade_count = len(trades)
            days_analyzed = len(data)
            trades_per_month = (trade_count / days_analyzed) * 30
            
            print(f"   ✅ Executed {trade_count} trades, total return: {total_return:.4f}x")
            
            return {
                crypto: {
                    'best_limit': str(limit_ratio),
                    'best_duration': str(duration),
                    'max_returns': total_return,
                    'trade_count': trade_count,
                    'trades_per_month': round(trades_per_month, 2)
                }
            }
            
        except Exception as e:
            print(f"   ❌ Simulation error for {crypto}: {e}")
            return None
    
    def _get_fresh_30day_data(self, crypto: str) -> np.ndarray:
        """
        Get fresh 30-day data from OKX API
        
        Args:
            crypto: Cryptocurrency symbol
            
        Returns:
            Fresh 30-day candlestick data
        """
        try:
            # Import OKX API
            import sys
            import os
            sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
            
            from okx.MarketData import MarketAPI
            from datetime import datetime, timedelta
            import time
            
            # Calculate timestamp for 30 days ago
            end_time = datetime.now()
            start_time = end_time - timedelta(days=30)
            
            # Convert to milliseconds timestamp
            start_ts = int(start_time.timestamp() * 1000)
            end_ts = int(end_time.timestamp() * 1000)
            
            print(f"   📡 Fetching fresh data from API for {crypto}")
            
            # Initialize MarketAPI (public API, no credentials needed)
            marketDataAPI = MarketAPI(flag="0")  # 0 for live, 1 for demo
            
            # Get candlestick data from OKX API
            # Note: OKX API uses 'after' for older data, 'before' for newer data
            result = marketDataAPI.get_candlesticks(
                instId=crypto,
                bar="1D",  # Daily candles
                limit=str(self.days)  # Get last N candles
            )
            
            if result['code'] != '0':
                print(f"   ❌ API error for {crypto}: {result['msg']}")
                return None
            
            data = result['data']
            if not data:
                print(f"   ❌ No API data for {crypto}")
                return None
            
            # Convert API response to numpy array
            # OKX API returns: [ts, open, high, low, close, vol, volCcy, volCcyQuote, confirm]
            candles = []
            for candle in data:
                try:
                    candles.append([
                        float(candle[0]),  # timestamp
                        float(candle[1]),  # open
                        float(candle[2]),  # high
                        float(candle[3]),  # low
                        float(candle[4]),  # close
                        float(candle[5]),  # vol
                        float(candle[6]),  # volCcy
                        float(candle[7]),  # volCcyQuote
                        float(candle[8])   # confirm
                    ])
                except (ValueError, IndexError) as e:
                    print(f"   ❌ Data conversion error for {crypto}: {e}")
                    return None
            
            # Convert to numpy array and reverse (OKX returns newest first)
            np_data = np.array(candles)[::-1]  # Reverse to get oldest first
            
            print(f"   ✅ Fetched {len(np_data)} days of fresh data")
            return np_data
            
        except Exception as e:
            print(f"   ❌ Fresh data fetch error for {crypto}: {e}")
            # Fallback to local data
            print(f"   🔄 Falling back to local data")
            data = self.optimizer.data_loader.get_hist_candle_data(crypto, 0, 0, "1d")
            if data is not None and len(data) > 30:
                return data[-30:]  # Last 30 days from local data
            return data
    
    def _print_summary(self, results: Dict[str, Any]):
        """Print analysis summary"""
        print("\n" + "="*60)
        print(f"📊 DAILY STRATEGY ANALYSIS SUMMARY (PAST {self.days} DAYS)")
        print("="*60)
        
        summary = results['summary']
        
        print(f"📈 Total Analyzed: {summary['total_analyzed']}")
        print(f"✅ Successful: {summary['successful_analysis']}")
        print(f"❌ Failed: {summary['failed_analysis']}")
        print(f"💰 Total Investment: ${summary['total_investment']:,.2f}")
        print(f"💵 Total Final Value: ${summary['total_final_value']:,.2f}")
        print(f"📊 Total P&L: ${summary['total_profit_loss']:+,.2f}")
        print(f"📈 Total Return: {summary['total_return_percentage']:+.2f}%")
        print(f"🟢 Profitable: {summary['profitable_cryptos']}")
        print(f"🔴 Losing: {summary['losing_cryptos']}")
        
        if summary['best_performers']:
            print(f"\n🏆 TOP 5 PERFORMERS:")
            for i, performer in enumerate(summary['best_performers'], 1):
                print(f"   {i}. {performer['crypto']}: {performer['return']:+.2f}% (${performer['profit_loss']:+.2f})")
        
        if summary['worst_performers']:
            print(f"\n📉 WORST 5 PERFORMERS:")
            for i, performer in enumerate(summary['worst_performers'], 1):
                print(f"   {i}. {performer['crypto']}: {performer['return']:+.2f}% (${performer['profit_loss']:+.2f})")
        
        print("="*60)
    
    def print_results(self, results: Dict[str, Any]):
        """Print results to console"""
        print("\n" + "="*60)
        print(f"📊 BACKTEST RESULTS ({self.days} DAYS)")
        print("="*60)
        
        for crypto, data in results['cryptocurrencies'].items():
            if data.get('analysis_success', False):
                print(f"\n📈 {crypto}:")
                print(f"   💰 Final Value: ${data.get('final_value', 0):.2f}")
                print(f"   📊 P&L: ${data.get('profit_loss', 0):+.2f}")
                print(f"   📈 Return: {data.get('return_percentage', 0):+.2f}%")
                print(f"   🔄 Trades: {data.get('trade_count', 0)}")
                print(f"   ⏱️  Best Duration: {data.get('best_duration', 'N/A')}")
                print(f"   🎯 Best Limit: {data.get('best_limit', 'N/A')}")

def main():
    """Main function to run the backtest"""
    print("🚀 Starting Strategy Backtest Analysis")
    
    # Initialize analyzer with $100 investment per crypto and 30 days
    analyzer = StrategyBacktestAnalyzer(investment_amount=100.0, days=30)
    
    # Run backtest
    results = analyzer.run_backtest()
    
    # Print results to console
    if results:
        analyzer.print_results(results)
    
    print("\n✅ Backtest completed!")

if __name__ == "__main__":
    main()
