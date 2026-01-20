# Deployment Guide

## 🚀 Push to GitHub

Repository: **https://github.com/xucheng2024/hour_trade**

### Method 1: Using Script (Recommended)

```bash
# Run the automated push script
./push_to_github.sh
```

### Method 2: Manual Commands

```bash
# 1. Initialize git (if first time)
git init

# 2. Add all files
git add .

# 3. Check what will be committed (IMPORTANT: Verify no .env file!)
git status

# 4. Create commit
git commit -m "Initial commit: OKX Trading System"

# 5. Add remote repository
git remote add origin https://github.com/xucheng2024/hour_trade.git

# 6. Push to GitHub
git branch -M main
git push -u origin main
```

### ⚠️ Security Checklist

Before pushing, verify:
- [ ] `.env` file is NOT in the commit (check `git status`)
- [ ] No API keys in source code
- [ ] `.gitignore` is properly configured
- [ ] Only `.env.example` is included (not `.env`)

## 🌐 Vercel Deployment (Web Dashboard)

### Prerequisites
- Vercel account
- GitHub repository connected

### Steps

1. **Install Vercel CLI**
```bash
npm install -g vercel
```

2. **Login to Vercel**
```bash
vercel login
```

3. **Deploy**
```bash
cd /Users/mac/Downloads/stocks/hour_trade
vercel --prod
```

4. **Configure Environment Variables**

In Vercel Dashboard:
- Settings → Environment Variables
- Add the following:

```
DATABASE_URL=postgresql://your_connection_string
OKX_API_KEY=your_api_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_TESTNET=false
```

5. **Redeploy**
```bash
vercel --prod
```

### Vercel Endpoints

After deployment:
- `https://your-project.vercel.app/` - Web dashboard
- `https://your-project.vercel.app/api/orders` - JSON API
- `https://your-project.vercel.app/api/health` - Health check

## 🐳 Docker Deployment (Optional)

### Create Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Environment variables (override at runtime)
ENV DATABASE_URL=""
ENV OKX_API_KEY=""
ENV OKX_SECRET=""
ENV OKX_PASSPHRASE=""
ENV SIMULATION_MODE="true"

# Run trading bot
CMD ["python", "websocket_limit_trading.py"]
```

### Build and Run

```bash
# Build image
docker build -t hour-trade .

# Run container
docker run -d \
  --name hour-trade-bot \
  --env-file .env \
  hour-trade

# View logs
docker logs -f hour-trade-bot

# Stop container
docker stop hour-trade-bot
```

## ☁️ Cloud Server Deployment

### AWS EC2 / DigitalOcean / Linode

```bash
# 1. SSH into server
ssh user@your-server-ip

# 2. Clone repository
git clone https://github.com/xucheng2024/hour_trade.git
cd hour_trade

# 3. Install Python 3.11+
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip

# 4. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# 5. Install dependencies
pip install -r requirements.txt

# 6. Configure environment
cp .env.example .env
nano .env  # Edit with real credentials

# 7. Initialize database
python init_database.py

# 8. Run with systemd (keep alive)
sudo nano /etc/systemd/system/hour-trade.service
```

### Systemd Service File

```ini
[Unit]
Description=OKX Hour Trade Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/hour_trade
Environment="PATH=/home/ubuntu/hour_trade/venv/bin"
ExecStart=/home/ubuntu/hour_trade/venv/bin/python websocket_limit_trading.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Start Service

```bash
# Enable and start service
sudo systemctl enable hour-trade
sudo systemctl start hour-trade

# Check status
sudo systemctl status hour-trade

# View logs
sudo journalctl -u hour-trade -f
```

## 📊 Database Migration (If Needed)

### From SQLite to Neon PostgreSQL

```bash
# 1. Export data from SQLite
python -c "
import sqlite3
import json
conn = sqlite3.connect('okx.db')
cur = conn.cursor()
cur.execute('SELECT * FROM orders')
orders = cur.fetchall()
with open('orders_backup.json', 'w') as f:
    json.dump(orders, f)
conn.close()
"

# 2. Import to PostgreSQL
python -c "
import json
import psycopg
import os
conn = psycopg.connect(os.getenv('DATABASE_URL'))
cur = conn.cursor()
with open('orders_backup.json') as f:
    orders = json.load(f)
for order in orders:
    cur.execute('INSERT INTO orders VALUES (%s, %s, %s, ...)', order)
conn.commit()
conn.close()
"
```

## 🔄 Continuous Deployment

### Vercel 自动部署

Vercel 会自动监听 GitHub 仓库的推送：

1. **推送到 GitHub**:
```bash
git push origin main
```

2. **Vercel 自动触发**:
- 自动检测到新提交
- 自动构建和部署
- 无需 GitHub Actions

3. **查看部署状态**:
```bash
# 使用 Vercel CLI
vercel ls

# 或访问 Vercel Dashboard
# https://vercel.com/dashboard
```

## 🔐 Security Best Practices

### Production Checklist

- [ ] Use strong database passwords
- [ ] Enable SSL/TLS for database connections
- [ ] Rotate API keys regularly
- [ ] Use environment variables (never hardcode)
- [ ] Enable 2FA on OKX account
- [ ] Monitor for suspicious activity
- [ ] Set trading limits (max daily loss)
- [ ] Keep backups of database
- [ ] Use firewalls to restrict access
- [ ] Enable logging and monitoring

### Environment Variable Management

```bash
# Development (.env)
SIMULATION_MODE=true
TRADING_AMOUNT_USDT=10

# Production (server environment)
SIMULATION_MODE=false
TRADING_AMOUNT_USDT=100
```

## 📈 Monitoring Setup

### Grafana + Prometheus (Optional)

```bash
# Install Prometheus
docker run -d -p 9090:9090 prom/prometheus

# Install Grafana
docker run -d -p 3000:3000 grafana/grafana

# Configure dashboards for:
# - Active orders
# - Profit/loss
# - API latency
# - Database connections
```

### Simple Monitoring Script

```bash
# Create monitor.sh
#!/bin/bash
while true; do
  curl -s http://localhost:5000/api/health || echo "❌ Service down!"
  sleep 60
done
```

## 🆘 Troubleshooting

### Common Issues

**Issue**: Push rejected
```bash
# Solution: Force push (careful!)
git push --force origin main
```

**Issue**: Port already in use
```bash
# Solution: Kill process
lsof -ti:5000 | xargs kill -9
```

**Issue**: Database connection timeout
```bash
# Solution: Check DATABASE_URL and firewall
psql $DATABASE_URL  # Test connection
```

---

**Repository**: https://github.com/xucheng2024/hour_trade
**Last Updated**: 2026-01-14
