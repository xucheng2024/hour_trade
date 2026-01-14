# 后台运行程序指南

## 🚀 方法一：使用 nohup（推荐，简单）

### 启动交易机器人

```bash
# 方式1：使用提供的脚本（推荐）
./run_background.sh

# 方式2：手动运行
nohup python3 websocket_limit_trading.py > logs/trading_bot.log 2>&1 &
```

### 查看日志

```bash
# 实时查看日志
tail -f logs/trading_bot.log

# 查看最后100行
tail -n 100 logs/trading_bot.log
```

### 停止程序

```bash
# 查找进程ID
ps aux | grep websocket_limit_trading.py

# 停止程序（替换 PID 为实际的进程ID）
kill <PID>

# 或者强制停止
pkill -f websocket_limit_trading.py
```

---

## 📺 方法二：使用 screen（推荐，可重新连接）

### 安装 screen（如果没有）

```bash
# macOS
brew install screen

# Linux (Ubuntu/Debian)
sudo apt-get install screen
```

### 启动

```bash
# 创建新的 screen 会话
screen -S trading_bot

# 在 screen 中运行程序
python3 websocket_limit_trading.py

# 按 Ctrl+A，然后按 D 来分离会话（程序继续运行）
```

### 重新连接

```bash
# 查看所有 screen 会话
screen -ls

# 重新连接到会话
screen -r trading_bot
```

### 停止

```bash
# 在 screen 会话中，按 Ctrl+C 停止程序
# 或者直接杀死 screen 会话
screen -X -S trading_bot quit
```

---

## 🎭 方法三：使用 tmux（推荐，功能强大）

### 安装 tmux（如果没有）

```bash
# macOS
brew install tmux

# Linux (Ubuntu/Debian)
sudo apt-get install tmux
```

### 启动

```bash
# 创建新的 tmux 会话
tmux new -s trading_bot

# 在 tmux 中运行程序
python3 websocket_limit_trading.py

# 按 Ctrl+B，然后按 D 来分离会话
```

### 重新连接

```bash
# 查看所有 tmux 会话
tmux ls

# 重新连接到会话
tmux attach -t trading_bot
```

### 停止

```bash
# 在 tmux 会话中，按 Ctrl+C 停止程序
# 或者杀死会话
tmux kill-session -t trading_bot
```

---

## 🔧 方法四：使用 systemd（Linux 系统服务，最专业）

### 创建服务文件

```bash
sudo nano /etc/systemd/system/hour-trade.service
```

### 服务文件内容

```ini
[Unit]
Description=Hour Trade Trading Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/hour_trade
Environment="PATH=/usr/bin:/usr/local/bin"
ExecStart=/usr/bin/python3 /path/to/hour_trade/websocket_limit_trading.py
Restart=always
RestartSec=10
StandardOutput=append:/path/to/hour_trade/logs/trading_bot.log
StandardError=append:/path/to/hour_trade/logs/trading_bot_error.log

[Install]
WantedBy=multi-user.target
```

### 使用服务

```bash
# 重载 systemd 配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start hour-trade

# 查看状态
sudo systemctl status hour-trade

# 查看日志
sudo journalctl -u hour-trade -f

# 停止服务
sudo systemctl stop hour-trade

# 设置开机自启
sudo systemctl enable hour-trade
```

---

## 📊 启动网页查看器（可选）

如果需要查看交易记录，可以在另一个终端启动：

```bash
# 前台运行
python3 trading_web_viewer.py

# 后台运行（使用 nohup）
nohup python3 trading_web_viewer.py > logs/web_viewer.log 2>&1 &

# 访问: http://localhost:5000
```

---

## 🔍 检查程序运行状态

```bash
# 检查进程
ps aux | grep websocket_limit_trading.py

# 检查端口（如果网页查看器在运行）
lsof -i :5000

# 查看日志
tail -f logs/trading_bot.log
```

---

## 💡 推荐方案

- **macOS/Linux 个人使用**：使用 **screen** 或 **tmux**（可以随时查看和操作）
- **Linux 服务器生产环境**：使用 **systemd**（自动重启、日志管理）
- **快速测试**：使用 **nohup**（最简单）
