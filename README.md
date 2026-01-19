# OKX Cryptocurrency Trading System

![GitHub](https://img.shields.io/badge/GitHub-xucheng2024%2Fhour__trade-blue?logo=github)
![Python](https://img.shields.io/badge/Python-3.11+-green?logo=python)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Neon-blue?logo=postgresql)
![OKX](https://img.shields.io/badge/OKX-API-orange)

A comprehensive cryptocurrency trading system for OKX exchange featuring:
- **Real-time WebSocket Trading** - Live market data and automated order execution
- **Limit Order Strategy** - Smart entry at optimal price points (90-97% of current price)
- **Automated Selling** - Market orders executed at next hour close
- **Risk Management** - Configurable limits per crypto pair with auto-cancellation
- **Cloud Database** - Neon PostgreSQL for reliable data storage
- **Web Dashboard** - Real-time trading records viewer

## 🚀 Quick Start

```bash
# 1. Clone repository
git clone https://github.com/xucheng2024/hour_trade.git
cd hour_trade

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your OKX API credentials and DATABASE_URL

# 4. Initialize database
python init_database.py

# 5. Run trading system
python websocket_limit_trading.py
```

## 📊 System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  OKX Exchange (WebSocket)                │
└───────────────────┬─────────────────────────────────────┘
                    │
    ┌───────────────┴───────────────┐
    │                               │
    ▼                               ▼
┌─────────────┐               ┌─────────────┐
│   Ticker    │               │   Candle    │
│  WebSocket  │               │  WebSocket  │
│ (Prices)    │               │ (1H Bars)   │
└──────┬──────┘               └──────┬──────┘
       │                             │
       └──────────┬──────────────────┘
                  ▼
      ┌─────────────────────┐
      │  Trading Logic      │
      │  - Limit Buy Orders │
      │  - Market Sell      │
      │  - Auto Cancel      │
      └─────────┬───────────┘
                │
                ▼
      ┌─────────────────────┐
      │  Neon PostgreSQL    │
      │  - Order Tracking   │
      │  - Trade History    │
      └─────────────────────┘
```

## 🎯 Core Features

### 1. WebSocket Real-Time Trading (`websocket_limit_trading.py`)

**Buy Logic**:
- Monitors 36 crypto pairs real-time via WebSocket
- Places **limit buy orders** when price drops to configured threshold (e.g., 95% of current price)
- Auto-cancels unfilled orders after 1 minute
- Sound notifications on order execution

**Sell Logic**:
- Monitors 1-hour candlestick charts
- Executes **market sell order** when current hour closes (`confirm='1'`)
- Automatic profit tracking with sell_price recording

**Key Parameters**:
```python
TRADING_AMOUNT_USDT = 100        # Per trade amount
SIMULATION_MODE = True           # Test mode (no real orders)
STRATEGY_NAME = "hourly_limit_ws"
```

### 2. Trading Strategy Configuration (`valid_crypto_limits.json`)

36 cryptocurrencies with optimized entry points:
- **BABYDOGE-USDT**: 95% entry (81.6% mean return)
- **VRA-USDT**: 97% entry (78.9% mean return)
- **DOGE-USDT**: 93% entry (32% mean return)
- **SOL-USDT**: 93% entry (31.8% mean return)
- And 32 more pairs...

### 3. Web Dashboard (`trading_web_viewer.py`)

```bash
python trading_web_viewer.py
# Access: http://localhost:5000
```

Features:
- Real-time trade records grouped by crypto
- Profit/loss calculation per pair
- Order status tracking
- Modern responsive UI

### 4. Vercel API Deployment (`api/index.py`)

Deploy trading dashboard to Vercel:
```bash
vercel --prod
```

Endpoints:
- `GET /` - Web dashboard (HTML)
- `GET /api/orders` - Trading data (JSON)
- `GET /api/health` - Health check

## 🗄️ Database Schema

### Main Table: `orders`

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    instId VARCHAR(50) NOT NULL,           -- e.g., BTC-USDT
    flag VARCHAR(50) NOT NULL,             -- Strategy name
    ordId VARCHAR(100) NOT NULL,           -- Order ID
    create_time BIGINT NOT NULL,           -- Timestamp (ms)
    orderType VARCHAR(20),                 -- limit/market
    state TEXT,                            -- sold out/active/canceled
    price VARCHAR(50),                     -- Buy price
    size VARCHAR(50),                      -- Order size
    sell_time BIGINT,                      -- Planned sell time
    side VARCHAR(10),                      -- buy/sell
    sell_price VARCHAR(50),                -- Actual sell price
    created_at TIMESTAMP DEFAULT NOW()
);
```

## 🔧 Configuration

### Environment Variables (`.env`)

```bash
# Database
DATABASE_URL=postgresql://user:pass@host/db?sslmode=require

# OKX API (Production)
OKX_API_KEY=your_api_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_TESTNET=false

# Trading
TRADING_AMOUNT_USDT=100
SIMULATION_MODE=true
```

### Trading Limits (`valid_crypto_limits.json`)

```json
{
  "cryptos": {
    "BTC-USDT": {
      "limit_percent": 95.0,
      "consistency": 100.0,
      "mean_return_timeslices": 50.0
    }
  }
}
```

## 📈 Trading Logic Flow

```mermaid
graph TD
    A[Start WebSocket] --> B[Subscribe to Tickers]
    B --> C{Price <= Limit?}
    C -->|Yes| D[Place Limit Buy Order]
    C -->|No| B
    D --> E[Record in Database]
    E --> F[Start 1min Timeout Check]
    F --> G{Order Filled?}
    G -->|No| H[Cancel Order]
    G -->|Yes| I[Monitor 1H Candles]
    I --> J{Hour Closed?}
    J -->|Yes| K[Place Market Sell]
    J -->|No| I
    K --> L[Update Database]
    L --> M[Remove from Active Orders]
```

## 🛡️ Security Features

- ✅ Environment variable protection (`.env` not committed)
- ✅ API key authentication (HMAC-SHA256)
- ✅ Simulation mode for testing
- ✅ Auto-cancellation of stale orders
- ✅ Database connection encryption (SSL)

## 🚢 Deployment Options

### Local Development
```bash
python websocket_limit_trading.py
```

### Vercel (Dashboard Only)
```bash
vercel --prod
```

### Docker (Optional)
```dockerfile
FROM python:3.11
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "websocket_limit_trading.py"]
```

## 📦 Project Structure

```
hour_trade/
├── websocket_limit_trading.py    # Main trading bot
├── trading_web_viewer.py          # Local web dashboard
├── init_database.py               # Database initialization
├── valid_crypto_limits.json       # Trading configuration (36 pairs)
├── api/
│   └── index.py                   # Vercel API handler
├── src/
│   ├── core/
│   │   ├── okx_functions.py       # Trading functions
│   │   ├── okx_ws_buy.py          # WebSocket buy logic
│   │   └── okx_ws_manage.py       # WebSocket management
│   ├── utils/
│   │   └── db_connection.py       # PostgreSQL connection
│   └── crypto_remote/             # Automation modules
│       ├── monitor_delist.py      # Delisting protection
│       └── fetch_filled_orders.py # Order tracking
├── requirements.txt
├── vercel.json
└── .env.example
```

## 🔍 Monitoring & Logs

```bash
# View trading logs
tail -f websocket_limit_trading.log

# Check database records
python -c "from src.utils.db_connection import *; print(execute_query('SELECT COUNT(*) FROM orders'))"

# View web dashboard
python trading_web_viewer.py
```

## ⚠️ Risk Disclaimer

- This system is for **educational purposes only**
- Cryptocurrency trading involves **substantial risk**
- Past performance does **not guarantee future results**
- You can **lose your entire investment**
- Always test with **SIMULATION_MODE=true** first
- Consult a licensed financial advisor before trading

## 📚 Documentation

- [GitHub Setup Guide](GITHUB_SETUP.md) - Git workflow and security
- [Database README](DATABASE_README.md) - Neon PostgreSQL setup
- [Database Solution](DATABASE_SOLUTION.md) - Migration from SQLite/Supabase
- [crypto_remote README](src/crypto_remote/README.md) - Automation system

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

## 📄 License

This project is for educational and personal use. Ensure compliance with:
- OKX API Terms of Service
- Local trading regulations
- Data privacy laws

## 🔗 Links

- **GitHub**: https://github.com/xucheng2024/hour_trade
- **OKX API Docs**: https://www.okx.com/docs-v5/en/
- **Neon PostgreSQL**: https://neon.tech/

---

**Built with** ❤️ **using Python, WebSockets, and PostgreSQL**

**Last Updated**: 2026-01-14
