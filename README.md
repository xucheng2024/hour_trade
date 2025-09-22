# OKX Cryptocurrency Trading System

A comprehensive cryptocurrency trading system featuring advanced V-pattern reversal strategies and profit maximization algorithms.

## 🎯 Core Features

- **V-Pattern Reversal Strategy**: Advanced pattern recognition for reversal trading
- **Profit Maximization**: AI-powered parameter optimization for maximum returns
- **Historical Data Management**: OKX API integration for market data collection
- **Risk Management**: Sophisticated stop-loss and take-profit mechanisms
- **Vectorized Computing**: High-performance calculations for strategy optimization

## 🚀 System Architecture

### Data Collection
- **Hourly Data**: `fetch_all_cryptos_hourly.py` - Collects 1H OHLCV data
- **Daily Data**: `fetch_all_cryptos_daily.py` - Collects 1D OHLCV data
- **Storage**: Data stored in compressed NPZ format in `data/` directory

### V-Pattern Research Module 🔥
```
v_reversal_research/
├── data_loader.py              # Market data integration
├── v_pattern_detector.py       # V-shaped pattern detection
├── v_strategy_backtester.py    # Strategy backtesting engine
├── profit_maximizer.py         # 🎯 AI profit maximization
├── vectorized_optimizer.py     # High-speed parameter optimization
├── run_v_analysis.py           # Basic V-pattern analysis
├── run_fast_optimization.py    # Vectorized optimization
├── run_profit_maximization.py  # 💰 Maximum profit optimization
└── holding_time_analysis.py    # Optimal holding time analysis
```

### Legacy Strategy Optimization
- **Vectorized Optimization**: `run_full_vectorized_optimization.py`
- **Parameter Search**: Automated grid search for optimal trading parameters
- **Configuration Generation**: Automated config file generation for best parameters

## 💰 V-Pattern Reversal Strategy

### Core Concept
The V-pattern strategy identifies rapid price reversals characterized by:
- Sharp decline followed by quick recovery
- Specific depth and recovery requirements
- Time-bound pattern completion

### Optimized Parameters (ETH-USDT)
- **Pattern Detection**:
  - Depth range: 3%-10%
  - Recovery requirement: 60%
  - Maximum pattern time: 24 hours
- **Trading Strategy**:
  - Stop Loss: 8%
  - Take Profit: 15%
  - **Optimal Holding Time: 48 hours** 🎯
- **Performance**: 408.87% return (3 months), 65.2% win rate

### Legacy Intraday Mean Reversion Strategy
- **Entry**: Buy when hourly low ≤ daily_open × (1 - b%)
- **Stop Loss**: Exit when price ≤ entry_price × (1 - l%)  
- **Take Profit**: Exit when price ≥ entry_price × (1 + p%)
- **End of Day**: Exit at close if neither SL/TP triggered

## 🔧 Quick Start

### Installation
```bash
pip install -r requirements.txt
```

### Data Collection
```bash
# Fetch hourly data for all cryptocurrencies
python fetch_all_cryptos_hourly.py

# Fetch daily data for all cryptocurrencies  
python fetch_all_cryptos_daily.py
```

### V-Pattern Strategy Optimization 🚀
```bash
# Quick V-pattern analysis
python v_reversal_research/run_v_analysis.py

# Fast vectorized optimization
python v_reversal_research/run_fast_optimization.py

# AI-powered profit maximization (RECOMMENDED)
python v_reversal_research/run_profit_maximization.py

# Optimal holding time analysis
python v_reversal_research/holding_time_analysis.py
```

### Legacy Strategy Optimization
```bash
# Run vectorized optimization
python run_full_vectorized_optimization.py

# Generate optimal configurations
python generate_full_hourly_config.py
```

## ⚡ Technical Features

- **AI Profit Maximization**: Advanced parameter optimization using vectorized algorithms
- **V-Pattern Recognition**: Sophisticated pattern detection for reversal trading
- **High Performance**: Vectorized calculations with numpy for 64,800+ parameter combinations
- **Scalable**: Processes 184+ cryptocurrencies efficiently
- **Configurable**: Flexible parameter ranges and trading rules
- **Data Efficient**: Compressed storage format reduces disk usage

## 🎯 Key Performance Metrics

### V-Pattern Strategy Results
- **ETH-USDT**: 408.87% return (3 months)
- **Win Rate**: 65.2%
- **Profit Factor**: 2.86
- **Optimal Holding**: 48 hours
- **Max Drawdown**: Controlled with 8% stop-loss

### Optimization Speed
- **64,800 parameter combinations** tested per symbol
- **~450 seconds** for 2-symbol optimization
- **Vectorized processing** for maximum efficiency

## 📈 Data Requirements

- Hourly OHLC data in OKX format (`data/{SYMBOL}_1H.npz`)
- Minimum 6 months of historical data per symbol (for optimization)
- Currently supports 184+ cryptocurrency pairs
- Automated train/test split (training on historical data, testing on recent 3 months)

## 🛡️ Risk Management

### Built-in Safety Features
- **Stop Loss**: Configurable 3%-10% levels
- **Take Profit**: Optimized 8%-25% targets
- **Time-based Exits**: Maximum holding periods to limit exposure
- **Position Sizing**: Recommended 2-3% per trade for 48-hour strategies

## ⚠️ Risk Disclaimer

Past performance does not guarantee future results. The 408.87% return is based on historical backtesting and may not reflect future performance. This system is for research and educational purposes. Always implement proper risk management and start with small position sizes in live trading.