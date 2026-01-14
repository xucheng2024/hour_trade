#!/bin/bash
# 后台运行交易机器人脚本

cd "$(dirname "$0")"

# 检查程序是否已经在运行
if pgrep -f "websocket_limit_trading.py" > /dev/null; then
    echo "⚠️  交易机器人已经在运行中"
    echo "PID: $(pgrep -f 'websocket_limit_trading.py')"
    exit 1
fi

# 创建日志目录
mkdir -p logs

# 使用 nohup 在后台运行
echo "🚀 启动交易机器人..."
nohup python3 websocket_limit_trading.py > logs/trading_bot.log 2>&1 &

# 获取进程ID
PID=$!
echo "✅ 交易机器人已启动"
echo "PID: $PID"
echo "日志文件: logs/trading_bot.log"
echo ""
echo "查看日志: tail -f logs/trading_bot.log"
echo "停止程序: kill $PID"
