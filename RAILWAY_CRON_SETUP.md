# Railway 定时任务配置

## 概述

在 Railway 上运行定时任务，不需要 Cloudflare Workers。Railway 支持通过 Cron Jobs 服务来执行定时脚本。

## 配置方法

### 方法 1：使用 Railway Cron Jobs（推荐）

1. **在 Railway 项目中添加 Cron Jobs 服务**
   - 进入 Railway 项目
   - 点击 "New" → 选择 "Cron Job"
   - 配置定时任务

2. **配置定时任务**

   在 Railway Dashboard 中为每个脚本创建独立的 Cron Job：

   **任务 1：监控退市（每 5 分钟）**
   - Schedule: `*/5 * * * *`
   - Command: `cd src/crypto_remote && python3 monitor_delist.py`
   - Working Directory: `/` (项目根目录)

   **任务 2：取消限价单（每 5 分钟）**
   - Schedule: `*/5 * * * *`
   - Command: `cd src/crypto_remote && python3 cancel_pending_limits.py`
   - Working Directory: `/`

   **任务 3：获取已成交订单（每 15 分钟）**
   - Schedule: `*/15 * * * *`
   - Command: `cd src/crypto_remote && python3 fetch_filled_orders.py`
   - Working Directory: `/`

   **任务 4：取消待处理触发器（每天 23:55）**
   - Schedule: `55 23 * * *`
   - Command: `cd src/crypto_remote && python3 cancel_pending_triggers.py`
   - Working Directory: `/`

   **任务 5：创建算法触发器（每天 00:05）**
   - Schedule: `5 0 * * *`
   - Command: `cd src/crypto_remote && python3 create_algo_triggers.py`
   - Working Directory: `/`

3. **共享环境变量**
   - 确保所有 Cron Jobs 使用相同的环境变量
   - 在 Project 级别设置环境变量，或在每个 Cron Job 中单独设置

### 方法 2：在 websocket_limit_trading.py 中集成（简单但不推荐）

如果定时任务不多，可以在 `websocket_limit_trading.py` 中启动后台线程：

```python
import threading
import schedule
import time

def run_scheduled_tasks():
    """运行定时任务"""
    schedule.every(5).minutes.do(run_monitor_delist)
    schedule.every(15).minutes.do(run_fetch_filled_orders)
    schedule.every().day.at("23:55").do(run_cancel_pending_triggers)
    schedule.every().day.at("00:05").do(run_create_algo_triggers)
    
    while True:
        schedule.run_pending()
        time.sleep(60)

# 在 main() 中启动
threading.Thread(target=run_scheduled_tasks, daemon=True).start()
```

**缺点**：如果主程序崩溃，定时任务也会停止。

## 推荐方案

**使用 Railway Cron Jobs**（方法 1）：
- ✅ 独立运行，不影响主程序
- ✅ 可以单独重启和监控
- ✅ 更稳定可靠

## 注意事项

1. **时区**：Railway Cron Jobs 使用 UTC 时间
   - 新加坡时间 (SGT) = UTC + 8
   - 例如：23:55 SGT = 15:55 UTC

2. **环境变量**：确保 Cron Jobs 能访问到所有必要的环境变量
   - `DATABASE_URL`
   - `OKX_API_KEY`
   - `OKX_SECRET`
   - `OKX_PASSPHRASE`

3. **日志**：每个 Cron Job 的日志可以在 Railway Dashboard 中查看

4. **依赖**：确保 Cron Jobs 使用的 Python 环境已安装所有依赖

## 验证

部署后，检查 Railway Dashboard：
- 查看每个 Cron Job 的执行历史
- 确认任务按计划执行
- 检查日志是否有错误
