# Quick Start Guide 🚀

## For New Users Cloning from GitHub

### Step 1: Clone Repository

```bash
git clone https://github.com/xucheng2024/hour_trade.git
cd hour_trade
```

### Step 2: Install Dependencies

```bash
# Install Python packages
pip install -r requirements.txt

# Or use virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 3: Configure Environment

```bash
# Copy template
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required variables in `.env`**:
```bash
DATABASE_URL=postgresql://your_connection_string
OKX_API_KEY=your_api_key
OKX_SECRET=your_secret_key
OKX_PASSPHRASE=your_passphrase
SIMULATION_MODE=true  # Start with simulation mode!
```

### Step 4: Initialize Database

```bash
python init_database.py
```

### Step 5: Run Trading System

```bash
# Start WebSocket trading bot
python websocket_limit_trading.py
```

**Expected output**:
```
Starting hourly_limit_ws trading system
Loaded 36 crypto limits
Ticker WebSocket opened
Subscribed to 36 tickers
Candle WebSocket opened
Subscribed to 36 1H candles
WebSocket connections started, waiting for messages...
```

### Step 6: View Dashboard (Optional)

Open a new terminal:

```bash
# Start web dashboard
python trading_web_viewer.py

# Access at: http://localhost:5000
```

## For Repository Owner (Push to GitHub)

### First Time Setup

```bash
cd /Users/mac/Downloads/stocks/hour_trade

# Run automated push script
./push_to_github.sh
```

**Or manually**:

```bash
# Check status (verify .env is NOT listed)
git status

# Add all files
git add .

# Commit
git commit -m "Initial commit: OKX Trading System"

# Add remote (if not exists)
git remote add origin https://github.com/xucheng2024/hour_trade.git

# Push to GitHub
git branch -M main
git push -u origin main
```

### Subsequent Updates

```bash
# Check changes
git status

# Add modified files
git add .

# Commit with message
git commit -m "Update trading logic"

# Push to GitHub
git push
```

## Testing the System

### 1. Simulation Mode (Safe Testing)

```bash
# In .env file
SIMULATION_MODE=true
TRADING_AMOUNT_USDT=10
```

This will:
- ✅ Connect to WebSocket
- ✅ Monitor prices
- ✅ Record orders in database
- ❌ NOT place real orders on OKX

### 2. Check Logs

```bash
# View real-time logs
tail -f websocket_limit_trading.log

# Search for specific crypto
grep "BTC-USDT" websocket_limit_trading.log
```

### 3. Query Database

```bash
python -c "
from src.utils.db_connection import execute_query
orders = execute_query('SELECT * FROM orders LIMIT 10')
for order in orders:
    print(order)
"
```

## Common Commands

### Start Trading Bot

```bash
# Foreground (see output)
python websocket_limit_trading.py

# Background (Linux/Mac)
nohup python websocket_limit_trading.py > output.log 2>&1 &

# Check if running
ps aux | grep websocket_limit_trading
```

### Stop Trading Bot

```bash
# Find process ID
ps aux | grep websocket_limit_trading

# Kill process
kill <PID>

# Or use Ctrl+C if running in foreground
```

### View Trading Records

```bash
# Start web dashboard
python trading_web_viewer.py

# Open browser: http://localhost:5000
```

### Update Configuration

```bash
# Edit crypto limits
nano valid_crypto_limits.json

# Restart trading bot for changes to take effect
```

## Troubleshooting

### Issue: "DATABASE_URL not found"

**Solution**: Create `.env` file with DATABASE_URL

```bash
cp .env.example .env
nano .env  # Add your DATABASE_URL
```

### Issue: "OKX API credentials not found"

**Solution**: Add API credentials to `.env`

```bash
# In .env file
OKX_API_KEY=your_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
```

### Issue: "WebSocket connection failed"

**Solution**: Check internet connection and OKX API status

```bash
# Test connection
curl -I https://www.okx.com

# Check OKX API status
curl https://www.okx.com/api/v5/system/status
```

### Issue: "Port 5000 already in use"

**Solution**: Kill existing process or use different port

```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9

# Or change port in trading_web_viewer.py
app.run(port=5001)
```

## Production Deployment

### Enable Real Trading

⚠️ **Only after thorough testing in simulation mode!**

```bash
# In .env file
SIMULATION_MODE=false
TRADING_AMOUNT_USDT=100
```

### Run as Service (Linux)

```bash
# Create systemd service
sudo nano /etc/systemd/system/hour-trade.service

# Enable and start
sudo systemctl enable hour-trade
sudo systemctl start hour-trade

# Check status
sudo systemctl status hour-trade
```

### Monitor Production

```bash
# View logs
sudo journalctl -u hour-trade -f

# Check database
python trading_web_viewer.py
```

## Resources

- **GitHub**: https://github.com/xucheng2024/hour_trade
- **OKX API Docs**: https://www.okx.com/docs-v5/en/
- **Neon PostgreSQL**: https://neon.tech/
- **Full Documentation**: See README.md

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python websocket_limit_trading.py` | Start trading bot |
| `python trading_web_viewer.py` | Start web dashboard |
| `python init_database.py` | Initialize database |
| `git status` | Check git status |
| `git push` | Push to GitHub |
| `tail -f *.log` | View logs |

---

**Need Help?** Check DEPLOYMENT.md for detailed deployment guide

**Last Updated**: 2026-01-14
