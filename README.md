# OKX Trading Bot

A comprehensive cryptocurrency trading bot system for the OKX exchange platform with advanced data management and strategy optimization capabilities.

## 🎯 Strategy Optimization Results

**Key Finding**: Duration 0 (same-day buy/sell) strategy is optimal with **13.32x returns (2,240% annual)** over 300 days.

**Core Insights**: 
- D0 strategy achieves 1,232% total returns with 69.4% win rate
- Multi-crypto rotation provides 61% trading day coverage  
- Fund flexibility during idle periods provides better opportunity cost than locked capital
- Day-level price volatility far exceeds hour-level movements

## Requirements

- **Python**: 3.6 or higher (required for f-string support)
- **Dependencies**: See `requirements.txt`

## Quick Start

1. **Install Python 3.6+**
   ```bash
   # Check your Python version
   python3 --version
   ```

2. **Install dependencies**
   ```bash
   pip3 install -r requirements.txt
   ```

3. **Fetch Historical Data** (Required before running strategies)
   ```bash
   # Get daily data for all cryptocurrencies
   python3 fetch_all_cryptos_daily.py
   
   # Get hourly data for all cryptocurrencies (if needed for analysis)
   python3 fetch_all_cryptos_hourly.py
   ```

4. **Generate Optimized Trading Configuration**
   ```bash
   # Generate D0 strategy configuration with optimal limits
   python3 generate_configs_improved.py
   ```

5. **Run Strategy Analysis**
   ```bash
   # Test and analyze trading strategies
   python3 src/testing/strategy_tester.py
   ```



## Data Management

### Historical Data Scripts

The project includes two powerful data fetching scripts:

#### `fetch_all_cryptos_daily.py`
- **Purpose**: Fetches daily (1D) candlestick data for all cryptocurrencies
- **Features**: 
  - Automatic pagination to get complete historical data
  - Duplicate detection and removal
  - Chronological ordering
  - Progress tracking and error handling
- **Output**: Saves data as `.npz` files in `data/` directory
- **Rate Limiting**: 0.5 second intervals between requests

#### `fetch_all_cryptos_hourly.py`
- **Purpose**: Fetches hourly (1H) candlestick data for all cryptocurrencies
- **Features**: Same as daily script but for hourly timeframe
- **Rate Limiting**: 1.0 second intervals between requests (more conservative for hourly data)

### Current Data Status

- **Supported Cryptocurrencies**: 29 coins (BTC, ETH, XRP, BNB, ADA, TRX, LINK, BCH, LTC, XLM, DOT, ETC, UNI, SOL, AVAX, HBAR, DOGE, SHIB, TON, AAVE, NEAR, CRO, WBTC, LEO, APT, ICP, SUI, ONDO, PEPE)
- **Daily Data**: 54,584+ records across all cryptocurrencies  
- **Hourly Data**: 817,777+ records across all cryptocurrencies (for analysis)
- **Data Format**: Compatible with strategy optimizer and analysis tools

### Data Structure

Each cryptocurrency generates two files:
- `{CRYPTO}_1D.npz` - Daily candlestick data
- `{CRYPTO}_1H.npz` - Hourly candlestick data

Data columns: `[timestamp, open, high, low, close, volume, volCcy, volCcyQuote, confirm]`

## Project Structure

```
ex_okx/
├── data/                           # Historical data storage (29 cryptos × 2 timeframes)
│   ├── *-USDT_1D.npz              # Daily candlestick data
│   └── *-USDT_1H.npz              # Hourly candlestick data
├── src/
│   ├── core/                      # Core trading functionality
│   │   ├── okx_functions.py      # OKX API integration
│   │   ├── okx_order_manage.py   # Order management
│   │   ├── okx_ws_buy.py         # WebSocket buy operations
│   │   └── okx_ws_manage.py      # WebSocket management
│   ├── strategies/                # Trading strategies
│   │   ├── strategy_optimizer.py  # Strategy parameter optimization (optimized)
│   │   └── historical_data_loader.py # Data preprocessing
│   ├── analysis/                  # Performance analysis
│   │   ├── returns_analyzer.py   # Return calculations
│   │   └── strategy_earnings_calculator.py # Earnings analysis
│   ├── data/                      # Data management
│   │   └── data_manager.py       # Historical data fetching
│   ├── system/                    # System utilities
│   │   └── okx_sqlite_create_table.py # Database setup
│   ├── utils/                     # Utility functions
│   │   ├── delist.py             # Delisting management
│   │   └── sub_account.py        # Sub-account utilities
│   └── config/                    # Configuration files
│       ├── cryptos_selected.json  # Cryptocurrency selection (29 coins)
│       └── okx_config.py         # OKX API configuration
├── fetch_all_cryptos_daily.py     # Daily data fetcher
├── fetch_all_cryptos_hourly.py    # Hourly data fetcher (for analysis)
├── generate_configs_improved.py   # Strategy configuration generator  
├── config_d0_baseline.json        # 🏆 D0 strategy config (optimal)
├── data_fetch.log                  # Data fetching logs
└── requirements.txt                # Python dependencies
```

## Configuration

### Cryptocurrency Selection
Edit `src/config/cryptos_selected.json` to select cryptocurrencies for trading and data fetching.

### OKX API Configuration
Configure API keys and endpoints in `src/config/okx_config.py`.

## Strategy Optimization

### Core Scripts

#### `generate_configs_improved.py`
- **Purpose**: Generates optimized trading configurations for different strategies
- **Features**: 
  - Tests multiple limit percentages (60-99%) for each crypto
  - Supports Duration 0 (same-day), 1, 2, 3+ day strategies
  - Outputs JSON configuration files with best parameters
- **Usage**: `python3 generate_configs_improved.py`
- **Output**: `config_d0_baseline.json` (recommended optimal configuration)

#### `src/strategies/strategy_optimizer.py`
- **Purpose**: Core optimization engine with vectorized backtesting
- **Key Features**:
  - Vectorized NumPy operations for fast computation
  - Proper fee calculation (0.1% buy/sell)
  - Support for same-day trading (Duration 0)
  - Realistic compound return calculation including losses
- **Recent Fixes**: Removed hour-based logic, fixed fee calculation, enabled D0 trading

#### `src/testing/strategy_tester.py`
- **Purpose**: Backtest and validate trading strategies
- **Features**:
  - Load optimized configurations
  - Test different holding durations
  - Performance comparison and analysis

### Strategy Configuration Files

#### **Optimal Configuration** 🏆
- **`config_d0_baseline.json`**: **Primary** trading configuration (D0 strategy)
- **Performance**: 13.32x returns (2,240% annual) over 300 days
- **Features**: 
  - Individual crypto limit percentages (78-96%)
  - Same-day buy/sell optimization
  - Multi-crypto rotation capability
  - 69.4% win rate with excellent risk management
- **Format**: Contains `best_limit` for each cryptocurrency pair

### The Strategy Optimizer System

The `StrategyOptimizer` class:
- Loads historical data from `.npz` files
- Tests limit ranges (60-99%) and duration ranges (0-29 days)
- Uses vectorized operations for efficient backtesting
- Calculates realistic returns including transaction fees
- Generates comprehensive performance metrics

## Database

- **SQLite Database**: `okx.db` for storing order history and market data
- **Historical Data**: Compressed NumPy arrays (`.npz`) for efficient storage and access

## Logging

- **Console Output**: Real-time progress and status updates
- **File Logs**: Detailed logs in `data_fetch.log`
- **Data Validation**: Automatic integrity checks and error reporting

## Development

### Best Practices
- Use `python3` for all Python commands
- Follow the modular structure in `src/`
- Check data integrity before running strategies
- Monitor API rate limits during data fetching

### Recommended Workflow
1. **Data Collection**: `python3 fetch_all_cryptos_daily.py` (primary)
2. **Strategy Optimization**: `python3 generate_configs_improved.py`
3. **Configuration Review**: Check `config_d0_baseline.json` output 
4. **Backtesting**: Use `src/testing/strategy_tester.py` for validation
5. **Live Trading**: Implement with D0 strategy parameters

### Key Insights from Analysis
- **Duration 0** (same-day trading) consistently outperforms longer holding periods
- **D0 strategy** achieves 13.32x returns (2,240% annual) with 69.4% win rate
- **Individual limits** per crypto (78-96%) work better than uniform limits  
- **Multi-crypto rotation** provides 61% trading day coverage
- **Day-level volatility** far exceeds hour-level movements
- **Idle time** with flexible capital > **locked capital** in longer duration trades
- **Fee calculation** is critical - use realistic 0.1% buy/sell fees

### Data Updates
- Run data fetching scripts periodically to maintain current data
- Scripts automatically detect existing data and skip already fetched periods
- Use rate limiting to respect OKX API constraints

### Testing
- Test strategies with historical data before live trading
- Validate data completeness and chronological order
- Use the strategy optimizer for parameter tuning
- **Recommended**: Use `config_d0_baseline.json` for optimal results

## Support

For detailed project information and development notes, check the project documentation and source code comments.
