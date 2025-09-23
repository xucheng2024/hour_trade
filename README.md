# OKX Cryptocurrency Trading System

A cryptocurrency research and trading toolkit for OKX data collection and legacy strategy optimization.

## Core Features
- Historical Data Management: OKX API integration for market data collection
- Legacy Strategy Optimization: Vectorized utilities and parameter search
- Risk Management: Stop-loss/Take-profit mechanisms

## System Architecture

### Data Collection
- Hourly Data: `fetch_all_cryptos_hourly.py` - Collects 1H OHLCV data
- Daily Data: `fetch_all_cryptos_daily.py` - Collects 1D OHLCV data
- Storage: Data stored in compressed NPZ format in `data/` directory

### Legacy Strategy Optimization
- Vectorized Optimization: `run_full_vectorized_optimization.py`
- Parameter Search: Automated grid search for optimal trading parameters
- Configuration Generation: `generate_full_hourly_config.py`

## Quick Start

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

### Optimization
```bash
# Run vectorized optimization
python run_full_vectorized_optimization.py

# Generate optimal configurations
python generate_full_hourly_config.py
```

## Data Requirements
- Hourly OHLC data in OKX format (`data/{SYMBOL}_1H.npz`)
- Sufficient historical data per symbol
- Automated train/test split supported by optimization scripts

## Risk Disclaimer
Past performance does not guarantee future results. Use proper risk management.