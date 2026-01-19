# 项目架构说明

## 📁 项目组成

本项目包含 **3个独立部分**，各有不同的部署方式：

---

## 1. 🤖 WebSocket 交易机器人（主程序）

### 文件
- `websocket_limit_trading.py`

### 功能
- 实时监控 36 个加密货币价格
- 自动下单（限价买入）
- 自动卖出（市价卖出）
- 数据库记录
- 声音通知

### 运行方式
**需要持续运行的服务器**

```bash
# 本地运行
python websocket_limit_trading.py

# 服务器后台运行
nohup python websocket_limit_trading.py > output.log 2>&1 &

# 或使用 systemd（推荐）
sudo systemctl start hour-trade
```

### 部署位置
- ✅ **Railway** (推荐) - 持续运行，自动重启
- ✅ VPS/云服务器（阿里云、腾讯云、AWS EC2）
- ✅ 本地电脑（24/7运行）
- ❌ **不适合** Vercel（需要持续 WebSocket 连接）
- ❌ **不适合** GitHub Actions（需要持续运行）

---

## 2. 📊 Web 仪表板

### 文件
- `api/index.py` - Vercel API Handler
- `trading_web_viewer.py` - 本地开发版本

### 功能
- 查看交易记录（只读）
- 按币种分组展示
- 盈亏计算
- 现代化 UI

### 运行方式

**本地开发**:
```bash
python trading_web_viewer.py
# 访问: http://localhost:5000
```

**生产部署**:
```bash
vercel --prod
# 访问: https://your-project.vercel.app
```

### 部署位置
- ✅ **Vercel** (推荐) - Serverless，按需触发
- ✅ 任何支持 Flask 的平台
- ❌ **不需要** GitHub Actions（Vercel 自动部署）

---

## 3. 🔄 自动化任务（crypto_remote）

### 文件
- `src/crypto_remote/monitor_delist.py` - 监控退市
- `src/crypto_remote/fetch_filled_orders.py` - 获取已成交订单

### 功能
- 定时任务（5分钟、15分钟、每日）
- 退市保护
- 订单跟踪

**注意**：所有卖出操作由 `websocket_limit_trading.py` 处理，具有双重保障机制（K线事件 + 超时检查）

### 运行方式
**Railway Cron Jobs**

在 Railway 项目中添加 Cron Jobs 服务，配置定时任务：
- 每 5 分钟：`monitor_delist.py` + `cancel_pending_limits.py`
- 每 15 分钟：`fetch_filled_orders.py`
- 每天 23:55：`cancel_pending_triggers.py`
- 每天 00:05：`create_algo_triggers.py`

详细配置见 `RAILWAY_CRON_SETUP.md`

### 部署位置
- ✅ **Railway Cron Jobs** - 与主程序在同一平台，共享环境变量
- ❌ **不需要** Cloudflare Workers
- ❌ **不需要** GitHub Actions

---

## 📊 部署架构对比

| 组件 | 部署位置 | 原因 | GitHub Actions? |
|------|---------|------|----------------|
| WebSocket交易机器人 | Railway | 需要持续运行 | ❌ 不需要 |
| Web仪表板 | Vercel | 按需触发，自动部署 | ❌ 不需要 |
| 自动化任务 | Railway Cron Jobs | 与主程序同平台 | ❌ 不需要 |

---

## 🚀 完整部署流程

### Step 1: 推送代码到 GitHub

```bash
cd /Users/mac/Downloads/stocks/hour_trade
./push_to_github.sh
```

**GitHub 仓库作用**:
- ✅ 代码版本控制
- ✅ 触发 Vercel 自动部署
- ❌ **不运行** GitHub Actions

### Step 2: 部署 Web 仪表板到 Vercel

```bash
# 自动部署（推荐）
# 推送到GitHub后，Vercel自动检测并部署

# 或手动部署
vercel --prod
```

配置环境变量（Vercel Dashboard）:
- `DATABASE_URL`
- `OKX_API_KEY`
- `OKX_SECRET`
- `OKX_PASSPHRASE`

### Step 3: 部署交易机器人到 Railway

1. **在 Railway 中创建项目**
   - 连接 GitHub 仓库
   - Railway 会自动检测并部署

2. **配置环境变量**
   - 在 Railway Dashboard 的 Variables 标签中设置：
     - `DATABASE_URL`
     - `OKX_API_KEY`
     - `OKX_SECRET_KEY`
     - `OKX_PASSPHRASE`
     - `SIMULATION_MODE=true` (测试模式)

3. **Railway 会自动运行**
   - 根据 `railway.json` 或 `Procfile` 自动启动
   - 主程序：`python websocket_limit_trading.py`

详细步骤见 `RAILWAY_DEPLOY.md`

### Step 4: 配置定时任务（Railway）

在 Railway Dashboard 中添加 Cron Jobs 服务，配置定时任务。

详细步骤见 `RAILWAY_CRON_SETUP.md`

---

## ❌ 不需要 GitHub Actions 的原因

1. **WebSocket 机器人**
   - 需要 24/7 持续运行
   - GitHub Actions 最长运行 6 小时
   - ❌ 不适合

2. **Web 仪表板**
   - Vercel 提供自动部署
   - 推送到 GitHub → 自动触发部署
   - ❌ 不需要额外的 Actions

3. **自动化任务**
   - Railway Cron Jobs 与主程序在同一平台
   - 共享环境变量，配置简单
   - ✅ 推荐使用 Railway Cron Jobs

---

## 📝 总结

**GitHub 仓库的作用**:
- ✅ 代码托管
- ✅ 版本控制
- ✅ 触发 Vercel 部署

**不需要的功能**:
- ❌ GitHub Actions workflows
- ❌ CI/CD 配置文件
- ❌ Secrets 配置（Vercel 有自己的环境变量）

**部署工具**:
- WebSocket 机器人 → Railway
- Web 仪表板 → Vercel
- 自动化任务 → Railway Cron Jobs

---

**最后更新**: 2026-01-14
**仓库**: https://github.com/xucheng2024/hour_trade
