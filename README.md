# OKX Trading Bot

A comprehensive cryptocurrency trading bot system for the OKX exchange platform with advanced data management, dynamic cryptocurrency selection, and strategy optimization capabilities.

## 🎯 Key Features

- **Dynamic Crypto Selection**: Automatically generates cryptocurrency lists from OKX API
- **Advanced Strategy Optimization**: Vectorized backtesting with realistic fee calculations
- **Multi-Timeframe Support**: Daily and hourly data analysis
- **Comprehensive Data Management**: Efficient storage and retrieval of historical data
- **Real-time Trading Ready**: WebSocket integration and order management
- **Performance Analytics**: Detailed returns analysis and strategy validation

## 🚀 Quick Start

### Prerequisites
- **Python**: 3.8 or higher
- **OKX Account**: API credentials for data access
- **Dependencies**: See `requirements.txt`

### Installation

1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd ex_okx
   pip3 install -r requirements.txt
   ```

2. **Generate Cryptocurrency List** (First time setup)
   ```bash
   # Dynamically generate crypto list from OKX API
   python3 src/data/crypto_list_generator.py
   ```

3. **Fetch Historical Data**
   ```bash
   # Get daily data for all cryptocurrencies
   python3 fetch_all_cryptos_daily.py
   
   # Get hourly data (optional, for analysis)
   python3 fetch_all_cryptos_hourly.py
   ```

4. **Generate Trading Configuration**
   ```bash
   # Generate optimized D0 strategy configuration
   python3 generate_d0_baseline_config.py
   ```

5. **Run Analysis**
   ```bash
   # Analyze returns and validate strategies
   python3 src/analysis/returns_analyzer.py
   ```

## 📊 Current Data Status

- **Supported Cryptocurrencies**: 194 active USDT pairs (from OKX API)
- **D0 Strategy Qualified**: 140 cryptocurrencies meeting strict requirements (≥30 trades, ≥1% returns)
- **Daily Data**: 244 cryptocurrency files with complete historical data
- **Hourly Data**: 55 cryptocurrency files for detailed analysis
- **Data Coverage**: 2+ years of historical data for most cryptocurrencies
- **Update Frequency**: Dynamic generation ensures up-to-date crypto lists
- **Last Config Update**: 2025-09-12 (config_d0_baseline.json)

## 🏗️ Project Structure

```
ex_okx/
├── data/                           # Historical data storage
│   ├── *-USDT_1D.npz              # Daily candlestick data (244 files)
│   ├── *-USDT_1H.npz              # Hourly candlestick data (55 files)
│   └── *.json                     # Analysis results and logs
├── src/
│   ├── core/                      # Core trading functionality
│   │   ├── okx_functions.py      # OKX API integration
│   │   ├── okx_order_manage.py   # Order management
│   │   ├── okx_ws_buy.py         # WebSocket buy operations
│   │   └── okx_ws_manage.py      # WebSocket management
│   ├── strategies/                # Trading strategies
│   │   ├── strategy_optimizer.py  # Vectorized strategy optimization
│   │   └── historical_data_loader.py # Data preprocessing
│   ├── analysis/                  # Performance analysis
│   │   ├── returns_analyzer.py   # Return calculations
│   │   └── strategy_earnings_calculator.py # Earnings analysis
│   ├── data/                      # Data management
│   │   ├── data_manager.py       # Historical data fetching
│   │   └── crypto_list_generator.py # Dynamic crypto list generation
│   ├── system/                    # System utilities
│   │   └── okx_sqlite_create_table.py # Database setup
│   ├── utils/                     # Utility functions
│   │   ├── delist.py             # Delisting management
│   │   └── sub_account.py        # Sub-account utilities
│   └── config/                    # Configuration files
│       ├── cryptos_selected.json  # Dynamic cryptocurrency list (194 coins)
│       ├── cryptos_selected_criteria.json # Selection criteria
│       └── okx_config.py         # OKX API configuration
├── fetch_all_cryptos_daily.py     # Daily data fetcher
├── fetch_all_cryptos_hourly.py    # Hourly data fetcher
├── generate_d0_baseline_config.py # D0 baseline config generator
├── config_d0_baseline.json        # 🏆 Optimized D0 strategy config (140 qualified cryptos)
├── high_price_change_trading_config.json # High volatility config
└── requirements.txt               # Python dependencies
```

## 🔧 Configuration

### Dynamic Cryptocurrency Selection

The system automatically generates cryptocurrency lists from the OKX API with intelligent filtering:

**Selection Criteria:**
- **USDT pairs only** (spot trading)
- **Listed for 720+ days** (2+ years of stable trading history)
- **State is 'live'** (currently active and tradable)
- **Market data available** (can fetch candlestick data)
- **Minimum trading volume** (ensures liquidity)

**Current Status:**
- **Total Available**: 194 USDT pairs from OKX API
- **D0 Qualified**: 140 pairs meeting strict trading requirements
- **Filter Rate**: 72% pass rate for D0 strategy

**To update the crypto list:**
```bash
python3 src/data/crypto_list_generator.py
```

### Strategy Configuration

The system supports multiple trading strategies with optimized parameters:

**D0 Strategy (Same-day Trading):**
- **Duration**: 0 days (buy and sell same day)
- **Limit Range**: 60-99% of current price
- **Min Trades**: 30 (statistical significance)
- **Min Returns**: 1% minimum return requirement
- **Qualified Cryptos**: 140 out of 194 (72% pass rate)
- **Performance**: Optimized for maximum returns with strict filtering

**Configuration Files:**
- `config_d0_baseline.json`: Primary D0 strategy configuration (140 qualified cryptos)
- `high_price_change_trading_config.json`: High volatility strategy

### 🏆 Top Performing D0 Strategies

**Latest Performance (Generated: 2025-09-12):**

| Rank | Cryptocurrency | Avg Return/Trade | Total Returns | Trades | Best Limit |
|------|----------------|------------------|---------------|--------|------------|
| 1    | RIO-USDT       | 24.37%          | 4942.85x      | 39     | 92%        |
| 2    | ORBS-USDT      | 21.09%          | 1438.71x      | 38     | 82%        |
| 3    | LINK-USDT      | 15.85%          | 199.70x       | 36     | 80%        |
| 4    | DGB-USDT       | 15.69%          | 219.69x       | 37     | 86%        |
| 5    | SWFTC-USDT     | 15.20%          | 187.89x       | 37     | 90%        |

**Strategy Statistics:**
- **Total Analyzed**: 192 cryptocurrencies
- **Qualified**: 140 (72% pass rate)
- **Average Trades**: 35.6 per crypto
- **Limit Range**: 60%-98% of opening price
- **Unique Limit Values**: 32 different optimal limits

## 📈 Strategy Optimization

### Core Optimization Engine

The `StrategyOptimizer` class provides:

- **Vectorized Operations**: NumPy-based for fast computation
- **Realistic Fee Calculation**: 0.1% buy/sell fees included
- **Multi-Strategy Support**: D0, D1, D2+ day strategies
- **Statistical Validation**: Minimum trade requirements
- **Performance Metrics**: Comprehensive returns analysis

### Key Features

- **Dynamic Parameter Testing**: Tests multiple limit percentages and durations
- **Fee-Aware Calculations**: Includes realistic trading costs
- **Risk Management**: Minimum trade count and return requirements
- **Data Validation**: Ensures data quality and completeness

### Usage Example

```python
from src.strategies.strategy_optimizer import get_strategy_optimizer

# Initialize optimizer
optimizer = get_strategy_optimizer(buy_fee=0.001, sell_fee=0.001)

# Set strategy parameters
optimizer.set_strategy_parameters(
    "1d",
    limit_range=(70, 90),
    duration_range=15,
    min_trades=20,
    min_avg_earn=1.01
)

# Optimize strategy
result = optimizer.optimize_1d_strategy(
    instId="BTC-USDT",
    start=0,
    end=0,
    date_dict={},
    bar='1d'
)
```

## 📊 Data Management

### Historical Data System

**Data Storage:**
- **Format**: Compressed NumPy arrays (`.npz`)
- **Structure**: `[timestamp, open, high, low, close, volume, volCcy, volCcyQuote, confirm]`
- **Efficiency**: Fast loading and memory-efficient storage

**Data Fetching:**
- **Rate Limiting**: Respects OKX API limits
- **Error Handling**: Automatic retry and recovery
- **Progress Tracking**: Real-time status updates
- **Duplicate Prevention**: Automatic deduplication

**Data Validation:**
- **Chronological Order**: Ensures proper time sequence
- **Completeness Check**: Validates data integrity
- **Range Validation**: Confirms data coverage

### Data Update Workflow

1. **Generate Crypto List**: `python3 generate_crypto_list.py`
2. **Fetch Daily Data**: `python3 fetch_all_cryptos_daily.py`
3. **Fetch Hourly Data**: `python3 fetch_all_cryptos_hourly.py` (optional)
4. **Validate Data**: Automatic integrity checks

## 🔍 Analysis and Monitoring

### Returns Analysis

The system provides comprehensive analysis tools:

- **Performance Metrics**: Returns, win rates, drawdowns
- **Strategy Comparison**: Multi-strategy analysis
- **Risk Assessment**: Volatility and correlation analysis
- **Backtesting**: Historical strategy validation

### Real-time Monitoring

- **WebSocket Integration**: Real-time price feeds
- **Order Management**: Automated trade execution
- **Portfolio Tracking**: Position and P&L monitoring
- **Alert System**: Price and performance notifications

## 🛠️ Development

### Code Quality

- **Type Hints**: Full type annotation support
- **Error Handling**: Comprehensive exception management
- **Logging**: Structured logging with multiple levels
- **Testing**: Unit and integration test support

### Best Practices

- **Modular Design**: Clean separation of concerns
- **Configuration Management**: Centralized settings
- **API Rate Limiting**: Respectful API usage
- **Data Validation**: Input sanitization and validation

### Development Workflow

1. **Setup Environment**: Install dependencies and configure API keys
2. **Data Collection**: Generate crypto list and fetch historical data
3. **Strategy Development**: Create and test new strategies
4. **Optimization**: Use optimizer to find best parameters
5. **Validation**: Backtest and validate strategies
6. **Deployment**: Deploy validated strategies

## 📋 Requirements

### Core Dependencies

```
# Trading & Finance
ccxt==4.5.0
python-okx==0.4.0
pandas==2.3.1
numpy==2.3.2

# Data Processing
python-dateutil==2.9.0.post0
pytz==2025.2

# Real-time & Performance
websockets==15.0.1
redis==6.4.0

# Visualization
matplotlib==3.10.5
plotly==6.3.0
mplfinance==0.12.10b0

# Development Tools
black==25.1.0
flake8==7.3.0
pytest==8.4.1
```

### System Requirements

- **Python**: 3.8+
- **Memory**: 4GB+ RAM recommended
- **Storage**: 2GB+ for historical data
- **Network**: Stable internet for API access

## 🚨 Important Notes

### API Usage

- **Rate Limits**: Respect OKX API rate limits
- **API Keys**: Configure in `src/config/okx_config.py`
- **Demo Mode**: Use flag="1" for testing

### Data Management

- **Backup**: Regularly backup historical data
- **Updates**: Run data fetching scripts periodically
- **Validation**: Always validate data before trading

### Risk Management

- **Testing**: Always test strategies with historical data
- **Paper Trading**: Use demo mode for initial testing
- **Position Sizing**: Implement proper risk management
- **Monitoring**: Continuously monitor strategy performance

## 📞 Support

For questions, issues, or contributions:

1. **Documentation**: Check source code comments and docstrings
2. **Issues**: Report bugs and feature requests
3. **Contributions**: Submit pull requests for improvements
4. **Community**: Join discussions and share strategies

## 📄 License

This project is for educational and research purposes. Please ensure compliance with OKX terms of service and applicable regulations when using for live trading.

---

**Disclaimer**: This software is provided for educational purposes only. Cryptocurrency trading involves substantial risk of loss. Past performance does not guarantee future results. Always do your own research and consider your risk tolerance before trading.