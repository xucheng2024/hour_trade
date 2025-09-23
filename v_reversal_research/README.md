# V-shaped Reversal Strategy Research

V-shaped reversal strategy research module - Detecting and trading V-shaped reversal patterns based on hourly data

## 📊 Strategy Overview

The V-shaped reversal strategy aims to capture short-term V-shaped reversal patterns in cryptocurrency markets:

1. **Detection Phase**: Identify V-shaped price patterns that fall rapidly and then recover quickly
2. **Confirmation Phase**: Confirm the pattern after price recovers to a certain level
3. **Trading Phase**: Buy after recovery confirmation, hold for 20 hours, then sell

## 🎯 Strategy Parameters

### V-pattern Detection Parameters
- **Minimum decline depth**: 3-25% (configurable)
- **Minimum recovery ratio**: 70% (recovery from bottom to 70% of starting point)
- **Maximum total time**: 48 hours (from start of decline to recovery completion)
- **Maximum recovery time**: 24 hours (time from bottom to recovery)

### Trading Parameters
- **Entry timing**: Next hour after V-pattern recovery confirmation
- **Holding time**: 20 hours (fixed)
- **Exit method**: Fixed time exit only, no stop loss or take profit
- **Minimum pattern quality**: 0.2 (comprehensive score based on depth, speed, and volume)

## 📁 File Structure

```
v_reversal_research/
├── __init__.py                    # Module initialization
├── data_loader.py                 # Data loader
├── v_pattern_detector.py          # V-pattern detector
├── v_strategy_backtester.py       # Strategy backtesting system
├── run_v_analysis.py             # Analysis runner
└── README.md                     # Documentation
```

## 🚀 Quick Start

### Running Analysis

```bash
# Enter V-shaped reversal research directory
cd v_reversal_research

# Run complete analysis
python run_v_analysis.py

# Or run quick test directly
python -c "from run_v_analysis import quick_test; quick_test()"
```

### Options
1. **Quick test**: 3 cryptocurrencies, 3 months data
2. **Full analysis**: 5 cryptocurrencies, 6 months data  
3. **Custom analysis**: Custom cryptocurrencies and time range

## 📈 Analysis Process

### 1. Data Loading
- Load hourly candlestick data from existing OKX data infrastructure
- Add technical indicators (moving averages, volatility, etc.)
- Data preprocessing and format standardization

### 2. V-pattern Detection
- Find local highs as decline starting points
- Identify qualified bottom positions
- Verify recovery speed and extent
- Calculate pattern quality score

### 3. Strategy Backtesting
- Simulate buying after V-pattern recovery confirmation
- Fixed holding for 20 hours then exit
- Calculate trading returns and holding time
- No stop loss or take profit, purely testing V-shaped reversal effectiveness

### 4. Result Analysis
- Win rate and average return statistics
- Sharpe ratio calculation
- Return analysis by different exit reasons
- Performance comparison across cryptocurrencies

## 📊 Output Results

### Console Output
- V-pattern detection results
- Strategy backtesting performance statistics
- Detailed trading analysis reports

### JSON Result Files
Saved in `../data/v_reversal_analysis_TIMESTAMP.json`, containing:
- Detector and backtester configuration
- Details of all detected V-patterns
- Trading records and performance statistics
- Summary analysis results

## 🔧 Core Algorithms

### V-pattern Detection Algorithm
1. **Local High Identification**: Use sliding window to find local price highs
2. **Bottom Search**: Find local lows after highs that meet depth requirements
3. **Recovery Verification**: Check if price recovers to threshold within specified time
4. **Quality Scoring**: Comprehensive scoring based on depth, speed, and volume
5. **Overlap Filtering**: Remove overlapping patterns, keep highest quality ones

### Quality Scoring Formula
```
Quality Score = Depth Score × 0.4 + Speed Score × 0.4 + Volume Score × 0.2

Where:
- Depth Score = min(decline depth / 15%, 1.0)
- Speed Score = max(0, 1.0 - recovery time / 24 hours)  
- Volume Score = min(bottom volume spike / 3.0, 1.0)
```

## 📝 Usage Example

```python
from v_reversal_research.data_loader import VReversalDataLoader
from v_reversal_research.v_pattern_detector import VPatternDetector
from v_reversal_research.v_strategy_backtester import VReversalBacktester

# Load data
loader = VReversalDataLoader()
data = loader.load_multiple_symbols(['BTC-USDT', 'ETH-USDT'], months=3)

# Detect V-patterns
detector = VPatternDetector()
patterns = detector.detect_patterns(data['BTC-USDT'])

# Backtest strategy (fixed 20-hour holding, no stop loss or take profit)
backtester = VReversalBacktester(holding_hours=20)
results = backtester.backtest_multiple_symbols(data, detector)
```

## ⚠️ Important Notes

1. **Data Dependency**: Requires sufficient historical hourly candlestick data
2. **Parameter Sensitivity**: V-pattern detection parameters significantly affect results, recommend multiple tests
3. **Market Environment**: Strategy performance may vary significantly across different market conditions
4. **Trading Fees**: 0.1% one-way trading fees already considered
5. **Slippage Impact**: Actual trading may have slippage affecting returns

## 🔄 Future Improvements

- [ ] Add more technical indicators for detection assistance
- [ ] Implement dynamic parameter optimization
- [ ] Add market environment classification analysis
- [ ] Support more timeframe analysis
- [ ] Add risk management module
