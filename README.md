# OKX Cryptocurrency Trading System

A comprehensive cryptocurrency trading system with advanced strategy optimization.

## 🎯 Core Features

- **Historical Data Management**: OKX API integration for market data
- **Strategy Optimization**: Ultra-fast parameter optimization with train/test split
- **Real-time Trading**: WebSocket connections and order management
- **Risk Management**: Sophisticated stop-loss and take-profit mechanisms

## 🚀 Strategy Optimization System

### Key Innovation: Intraday Mean Reversion Strategy
- **Entry**: Buy when hourly low ≤ daily_open × (1 - b%)
- **Stop Loss**: Exit when price ≤ daily_open × (1 - l%)  
- **Take Profit**: Exit when price ≥ daily_open × (1 + p%)
- **End of Day**: Exit at close if neither SL/TP triggered

### Research Module
```
research/
├── data_loader.py              # Market data integration
├── final_ultra_optimizer.py    # 🎯 Core optimization engine
├── run_final_optimization.py   # 🚀 Main execution script
└── README.md                   # Detailed documentation

run_strategy_optimization.py    # 📋 Convenient wrapper script
```

## 📊 Performance Results

Recent optimization results (91-day out-of-sample testing):

| Symbol | Test Return | Optimal Parameters (b%, l%, p%) | Annualized |
|--------|-------------|----------------------------------|------------|
| ACA-USDT | 51.53% | 5.0, 2.5, 10.5 | 471.2% |
| 1INCH-USDT | 87.38% | 2.0, 1.0, 4.0 | 801.1% |
| BTC-USDT | 26.5% | 1.5, 0.8, 5.0 | 243.1% |

- **Average Return**: 55.1% (91 days)
- **Success Rate**: 100% (all tested symbols profitable)
- **Method**: Strict train/test split, no data leakage

## 🔧 Quick Start

### Installation
```bash
pip install -r requirements.txt
```

### Run Strategy Optimization
```bash
# Method 1: Use wrapper script
python run_strategy_optimization.py

# Method 2: Run research module directly  
python -m research.run_final_optimization
```

### Options
1. Quick test (3 symbols, ~30 seconds)
2. Medium test (10 symbols, ~2 minutes)  
3. Full optimization (184 symbols, ~10 minutes)

## ⚡ Technical Features

- **Ultra-fast**: Vectorized calculations with numpy
- **Scalable**: Processes 184+ cryptocurrencies efficiently
- **Rigorous**: Proper train/test methodology prevents overfitting
- **Comprehensive**: Tests 4,350+ parameter combinations per symbol

## 📈 Data Requirements

- Hourly OHLC data in OKX format (`data/{SYMBOL}_1H.npz`)
- Minimum 3 months of historical data per symbol
- Currently supports 184+ cryptocurrency pairs

## ⚠️ Risk Disclaimer

Past performance does not guarantee future results. This system is for research and educational purposes. Always implement proper risk management in live trading.