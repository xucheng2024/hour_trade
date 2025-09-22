# OKX Cryptocurrency Trading System

A comprehensive cryptocurrency trading system for data collection, strategy optimization, and automated trading.

## 🎯 Core Features

- **Historical Data Management**: OKX API integration for market data collection
- **Real-time Trading**: WebSocket connections and order management
- **Risk Management**: Sophisticated stop-loss and take-profit mechanisms
- **Data Storage**: Efficient NPZ format for large datasets

## 🚀 System Architecture

### Data Collection
- **Hourly Data**: `fetch_all_cryptos_hourly.py` - Collects 1H OHLCV data
- **Daily Data**: `fetch_all_cryptos_daily.py` - Collects 1D OHLCV data
- **Storage**: Data stored in compressed NPZ format in `data/` directory

### Strategy Optimization
- **Vectorized Optimization**: `run_full_vectorized_optimization.py`
- **Parameter Search**: Automated grid search for optimal trading parameters
- **Configuration Generation**: Automated config file generation for best parameters

## 📊 Trading Strategy

### Intraday Mean Reversion Strategy
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

### Strategy Optimization
```bash
# Run vectorized optimization
python run_full_vectorized_optimization.py

# Generate optimal configurations
python generate_full_hourly_config.py
```

## ⚡ Technical Features

- **High Performance**: Vectorized calculations with numpy
- **Scalable**: Processes 184+ cryptocurrencies efficiently
- **Configurable**: Flexible parameter ranges and trading rules
- **Data Efficient**: Compressed storage format reduces disk usage

## 📈 Data Requirements

- Hourly OHLC data in OKX format (`data/{SYMBOL}_1H.npz`)
- Minimum 3 months of historical data per symbol
- Currently supports 184+ cryptocurrency pairs

## ⚠️ Risk Disclaimer

Past performance does not guarantee future results. This system is for research and educational purposes. Always implement proper risk management in live trading.