# Crypto Trading Strategy Optimizer

A comprehensive cryptocurrency trading strategy optimizer for OKX exchange, featuring vectorized profit optimization and multi-crypto analysis.

## 🎯 Key Features

- **Vectorized Optimization**: High-performance profit optimization using numpy vectorization
- **Multi-Crypto Support**: Analysis of 185+ cryptocurrencies from OKX
- **Historical Data Analysis**: Comprehensive backtesting with hourly and daily data
- **Strategy Configuration**: Flexible parameter configuration for different trading strategies
- **Risk Management**: Built-in risk controls and position sizing

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Required packages: `numpy`, `pandas`, `okx`, `scikit-learn`

### Installation
```bash
git clone <repository-url>
cd ex_okx
pip install -r requirements.txt
```

### Basic Usage
```bash
# Run vectorized optimization
python vectorized_profit_optimizer.py

# Run hourly optimization
python run_full_hourly_optimization.py

# Generate crypto triggers
python generate_crypto_triggers.py
```

## 📊 Core Components

### Data Management
- **`fetch_all_cryptos_daily.py`** - Fetch daily OHLCV data for all cryptocurrencies
- **`fetch_all_cryptos_hourly.py`** - Fetch hourly OHLCV data for all cryptocurrencies
- **`src/data/data_manager.py`** - Data loading and preprocessing utilities

### Strategy Optimization
- **`vectorized_profit_optimizer.py`** - Main optimization engine
- **`run_full_vectorized_optimization.py`** - Full optimization pipeline
- **`run_full_hourly_optimization.py`** - Hourly data optimization
- **`src/strategies/strategy_optimizer.py`** - Strategy optimization algorithms

### Configuration
- **`src/config/cryptos_selected.json`** - List of supported cryptocurrencies
- **`src/config/okx_config.py`** - OKX API configuration
- **`generate_*.py`** - Configuration generation scripts

## 📁 Project Structure

```
ex_okx/
├── src/
│   ├── analysis/           # Analysis modules
│   ├── config/            # Configuration files
│   ├── core/              # Core trading functions
│   ├── data/              # Data management
│   ├── strategies/        # Strategy implementations
│   ├── system/            # System utilities
│   └── utils/             # Utility functions
├── data/                  # Historical data storage
├── vectorized_profit_optimizer.py
├── run_full_*.py
├── generate_*.py
└── requirements.txt
```

## 💡 Usage Examples

### Basic Optimization
```python
from vectorized_profit_optimizer import VectorizedProfitOptimizer

# Initialize optimizer
optimizer = VectorizedProfitOptimizer()

# Run optimization
results = optimizer.optimize_all_strategies()

# Get best parameters
best_params = optimizer.get_best_parameters()
```

### Data Fetching
```python
from src.data.data_manager import DataManager

# Initialize data manager
dm = DataManager()

# Fetch data for specific crypto
data = dm.fetch_crypto_data('BTC-USDT', '1H')

# Process data
processed_data = dm.preprocess_data(data)
```

### Strategy Configuration
```python
from src.config.okx_config import OKXConfig

# Load configuration
config = OKXConfig()

# Get supported cryptos
cryptos = config.get_supported_cryptos()

# Configure API settings
api_config = config.get_api_config()
```

## 🔍 Key Features

### 1. Vectorized Processing
- **High Performance**: NumPy vectorization for fast computation
- **Memory Efficient**: Optimized data structures and operations
- **Scalable**: Handles large datasets efficiently

### 2. Multi-Strategy Support
- **Multiple Timeframes**: Hourly and daily analysis
- **Flexible Parameters**: Configurable strategy parameters
- **Risk Controls**: Built-in position sizing and risk management

### 3. Data Quality
- **OKX Integration**: Direct integration with OKX API
- **Data Validation**: Comprehensive data quality checks
- **Historical Coverage**: Extensive historical data support

## 📊 Optimization Results

### Performance Metrics
- **Sharpe Ratio**: Risk-adjusted returns
- **Maximum Drawdown**: Risk assessment
- **Win Rate**: Success percentage
- **Average Return**: Mean performance

### Supported Cryptocurrencies
- **Total Cryptos**: 185+ supported
- **Major Pairs**: BTC, ETH, BNB, ADA, SOL, etc.
- **Altcoins**: Wide selection of altcoin pairs
- **Stablecoins**: USDT, USDC pairs

## 🛠️ Technical Details

### Optimization Algorithm
1. **Parameter Space**: Define search space for strategy parameters
2. **Vectorized Evaluation**: Fast computation using NumPy
3. **Multi-Objective**: Optimize for multiple performance metrics
4. **Validation**: Cross-validation and robustness testing

### Data Processing
- **OHLCV Data**: Open, High, Low, Close, Volume
- **Time Series**: Proper time series handling
- **Missing Data**: Robust handling of missing values
- **Data Quality**: Validation and cleaning

## ⚠️ Risk Management

### Built-in Controls
- **Position Sizing**: Configurable position limits
- **Stop Loss**: Automatic stop loss implementation
- **Risk Limits**: Maximum drawdown controls
- **Diversification**: Multi-crypto portfolio approach

### Usage Recommendations
- **Paper Trading**: Test strategies with historical data
- **Small Positions**: Start with small position sizes
- **Regular Monitoring**: Monitor performance regularly
- **Risk Assessment**: Understand the risks involved

## 📋 Requirements

```
numpy>=1.21.0
pandas>=1.3.0
scikit-learn>=1.0.0
okx>=1.0.0
plotly>=5.0.0
matplotlib>=3.5.0
seaborn>=0.11.0
```

## 📄 License

This project is for educational and research purposes. Please ensure compliance with applicable regulations when using for live trading.

## 🔧 Recent Updates

### Core Optimization (2025-09-16)
- **Vectorized Processing**: Implemented high-performance optimization
- **Multi-Crypto Support**: Added support for 185+ cryptocurrencies
- **Data Management**: Comprehensive data fetching and processing
- **Strategy Framework**: Flexible strategy configuration system

---

**Disclaimer**: Cryptocurrency trading involves substantial risk. Past performance does not guarantee future results. Always do your own research and consider your risk tolerance before trading.