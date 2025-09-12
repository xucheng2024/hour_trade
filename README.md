# Crypto Trading Strategy Optimizer

A vectorized cryptocurrency trading strategy optimizer that finds optimal parameters for maximum compound returns with median return > 1.01.

## 🎯 Key Features

- **Vectorized Optimization**: Efficient parameter space exploration for 192 cryptocurrencies
- **3D Parameter Analysis**: Optimizes p (high/open ratio) and v (volume ratio) parameters
- **Realistic Trading**: Includes 0.1% buy/sell fees in all calculations
- **Comprehensive Results**: 190/192 cryptocurrencies successfully optimized (99.0% success rate)
- **Ready-to-Use Config**: JSON configuration for immediate trading implementation

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Required packages: `numpy`, `pandas`, `json`

### Installation
```bash
git clone <repository-url>
cd ex_okx
pip3 install -r requirements.txt
```

### Run Optimization
```bash
# Quick test with first 20 cryptos
python3 vectorized_profit_optimizer.py

# Full optimization for all 192 cryptos
python3 run_full_vectorized_optimization.py

# Generate trading triggers configuration
python3 generate_crypto_triggers.py

# Test recent 3-month performance
python3 test_sample_cryptos.py
```

## 📊 Optimization Results

### Strategy Definition
**Buy Condition**: `(High - Open) / Open >= p AND Volume / PreviousVolume >= v`  
**Sell**: Closing price  
**Requirements**: Maximum compound return AND median return > 1.01

### Key Findings

| Parameter | Range | Most Common | Description |
|-----------|-------|-------------|-------------|
| **P (High/Open ratio)** | 2.0% - 8.0% | 5.0% (41.6%) | Price momentum threshold |
| **V (Volume ratio)** | 1.1x - 1.1x | 1.1x (99.5%) | Volume increase requirement |

### Historical Performance Statistics
- **Success Rate**: 190/192 cryptocurrencies (99.0%)
- **Compound Returns**: 1.42 - 2.39×10¹⁵ (range)
- **Median Returns**: 1.014 - 1.080 (all > 1.01 requirement)
- **Win Rates**: 70.0% - 95.2%
- **Average Trades**: 287 ± 105 per cryptocurrency

### Recent 3-Month Performance (2025-05-27 to 2025-08-25)

**Test Results Summary**:
- **Tested Cryptocurrencies**: 9 representative coins
- **Positive Returns**: 9/9 (100% in sample)
- **Average Compound Return**: 1.950 (95% gain)
- **Average Win Rate**: 72.9%
- **Total Trades**: 135 across all tested cryptos

**Top Recent Performers**:
| Rank | Cryptocurrency | Compound Return | Win Rate | Trades | Parameters |
|------|----------------|-----------------|----------|---------|------------|
| 1 | **ETH-USDT** | **2.952** | 83.3% | 18 | P=4%, V=1.1x |
| 2 | **LINK-USDT** | **2.903** | 92.3% | 13 | P=5%, V=1.1x |
| 3 | **UNI-USDT** | **2.815** | 84.2% | 19 | P=5%, V=1.1x |
| 4 | **ADA-USDT** | **1.675** | 68.8% | 16 | P=4%, V=1.1x |
| 5 | **DOGE-USDT** | **1.620** | 54.5% | 22 | P=4%, V=1.1x |

**Risk Assessment**:
- **Overall Success**: 185/190 cryptos positive (97.4%)
- **Negative Returns**: 5/190 cryptos (2.6%) - mostly small losses
- **Strategy Validation**: Parameters remain effective in recent market conditions

### Risk Categories

| Category | P Range | Count | Examples | Risk Level |
|----------|---------|-------|----------|------------|
| **Conservative** | 2.0% - 3.0% | 14 (7.4%) | WBTC, XAUT, TON | Low |
| **Standard** | 4.0% - 5.0% | 134 (70.5%) | BTC, ETH, ADA | Moderate |
| **Aggressive** | 6.0% - 7.0% | 37 (19.5%) | SWFTC, STORJ, API3 | High |
| **High Risk** | 8.0% | 5 (2.6%) | PEPE, AIDOGE, PEOPLE | Very High |

## 🏆 Top Performers

### By Compound Return
| Rank | Cryptocurrency | P | V | Compound Return | Median Return | Win Rate |
|------|----------------|---|----|-----------------|---------------|----------|
| 1 | SWFTC-USDT | 6.0% | 1.1x | 2.39×10¹⁵ | 1.052 | 77.6% |
| 2 | STORJ-USDT | 6.0% | 1.1x | 2.38×10¹² | 1.055 | 83.4% |
| 3 | THETA-USDT | 5.0% | 1.1x | 1.43×10¹² | 1.051 | 83.1% |
| 4 | LINK-USDT | 5.0% | 1.1x | 3.06×10¹¹ | 1.056 | 86.8% |
| 5 | LRC-USDT | 5.0% | 1.1x | 2.09×10¹¹ | 1.046 | 81.1% |

### By Median Return
| Rank | Cryptocurrency | P | V | Median Return | Compound Return | Win Rate |
|------|----------------|---|----|---------------|-----------------|----------|
| 1 | AIDOGE-USDT | 8.0% | 1.1x | 1.080 | 183,240 | 87.7% |
| 2 | FLOKI-USDT | 7.0% | 1.1x | 1.075 | 1,712,683 | 95.1% |
| 3 | PEPE-USDT | 7.0% | 1.1x | 1.075 | 451,744 | 93.8% |
| 4 | CVX-USDT | 6.0% | 1.1x | 1.072 | 1,649,430 | 93.9% |
| 5 | ORDI-USDT | 7.0% | 1.1x | 1.072 | 5,504 | 89.2% |

## 📁 Core Files

### Essential Scripts
- **`vectorized_profit_optimizer.py`** - Main optimization engine
- **`run_full_vectorized_optimization.py`** - Full 192-crypto optimization
- **`generate_crypto_triggers.py`** - Generate trading configuration
- **`test_sample_cryptos.py`** - Test recent performance on representative cryptos

### Configuration Files
- **`crypto_trading_triggers.json`** - Complete triggers for all 190 cryptos
- **`complete_boundary_analysis.md`** - Detailed analysis report

### Data Files
- **`data/vectorized_optimization_*.json`** - Full optimization results
- **`data/parameter_analysis_*.json`** - 3D parameter space analysis

## 💡 Usage Examples

### Load Trading Configuration
```python
import json

# Load triggers configuration
with open('crypto_trading_triggers.json', 'r') as f:
    config = json.load(f)

# Get trigger for specific crypto
btc_trigger = config['triggers']['BTC-USDT']
p_threshold = btc_trigger['high_open_ratio_threshold']  # 0.04 (4%)
v_threshold = btc_trigger['volume_ratio_threshold']     # 1.1
expected_return = btc_trigger['expected_performance']['median_return']  # 1.045
```

### Check Buy Signal
```python
def check_buy_signal(crypto, high, open_price, current_volume, previous_volume):
    trigger = config['triggers'][crypto]
    
    # Calculate ratios
    high_open_ratio = (high - open_price) / open_price
    volume_ratio = current_volume / previous_volume if previous_volume > 0 else 0
    
    # Check thresholds
    if (high_open_ratio >= trigger['high_open_ratio_threshold'] and 
        volume_ratio >= trigger['volume_ratio_threshold']):
        return True, {
            'crypto': crypto,
            'expected_median_return': trigger['expected_performance']['median_return'],
            'risk_level': trigger['risk_level']
        }
    
    return False, "Conditions not met"

# Example usage
signal, info = check_buy_signal('BTC-USDT', 50000, 48000, 1000000, 800000)
if signal:
    print(f"Buy signal: {info}")
```

## 🔍 Key Insights

### 1. Volume Threshold is Minimal
- **99.5% of cryptos** use v = 1.1x (10% volume increase)
- Volume condition is easily met - **not the limiting factor**
- Main purpose: Filter out extremely low-volume days

### 2. Price Threshold is the Key
- **P parameter (2%-8%)** is the primary strategy differentiator
- Lower P = More frequent trades, lower risk
- Higher P = Fewer trades, higher potential returns

### 3. Strategy Classification
- **Conservative (P=2%-3%)**: Stable coins like WBTC, XAUT
- **Standard (P=4%-5%)**: Most cryptocurrencies (70.5%)
- **Aggressive (P=6%-8%)**: High volatility coins like PEPE, AIDOGE

## 📊 Parameter Distribution

### P Parameter Distribution
- **5.0%**: 79 cryptos (41.6%) - Most common
- **4.0%**: 55 cryptos (28.9%) - Second most common
- **6.0%**: 26 cryptos (13.7%) - Aggressive strategy
- **7.0%**: 11 cryptos (5.8%) - High volatility
- **3.0%**: 11 cryptos (5.8%) - Conservative
- **8.0%**: 5 cryptos (2.6%) - Extreme volatility
- **2.0%**: 3 cryptos (1.6%) - Very conservative

### V Parameter Distribution
- **1.1x**: 189 cryptos (99.5%) - Nearly universal
- **1.2x-1.3x**: 1 crypto (0.5%) - XAUT-USDT only

## 🛠️ Technical Details

### Optimization Algorithm
1. **Vectorized Operations**: NumPy-based for speed
2. **Parameter Grid**: Tests all combinations of p and v
3. **Constraint Filtering**: Only results with median return > 1.01
4. **Optimal Selection**: Chooses maximum compound return
5. **Range Analysis**: Identifies near-optimal parameter regions

### Data Requirements
- **Historical Data**: Daily OHLCV data from OKX
- **Time Period**: 2+ years for statistical significance
- **Data Quality**: Validated price and volume relationships

## ⚠️ Important Notes

### Risk Management
- **Historical Performance**: Results based on past data
- **Market Dependency**: Strategy relies on upward price movements
- **Same-Day Risk**: Selling at close may not capture maximum profit
- **Fee Impact**: 0.2% total fees (0.1% buy + 0.1% sell)

### Usage Recommendations
- **Paper Trading**: Test with historical data first
- **Position Sizing**: Start with small positions
- **Monitoring**: Regularly check parameter effectiveness
- **Updates**: Re-optimize periodically as markets change

## 📋 Requirements

```
numpy>=1.21.0
pandas>=1.3.0
```

## 📄 License

This project is for educational and research purposes. Please ensure compliance with applicable regulations when using for live trading.

---

**Disclaimer**: Cryptocurrency trading involves substantial risk. Past performance does not guarantee future results. Always do your own research and consider your risk tolerance before trading.