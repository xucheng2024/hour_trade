# Vercel 部署指南

## ✅ 项目已支持 Vercel 部署

### 功能说明

**Web 仪表板** - 查看交易记录
- URL: `https://your-project.vercel.app/`
- 功能: HTML 仪表板，展示所有交易记录
- 特性: 按币种分组、盈亏计算、现代化UI

**JSON API** - 获取数据
- URL: `https://your-project.vercel.app/api/orders`
- 返回: JSON 格式的交易数据
- 用途: 供其他应用调用

**健康检查**
- URL: `https://your-project.vercel.app/api/health`
- 返回: 系统状态

## 🚀 快速部署

### 方法 1: Vercel CLI（推荐）

```bash
# 1. 安装 Vercel CLI
npm install -g vercel

# 2. 登录
vercel login

# 3. 进入项目目录
cd /Users/mac/Downloads/stocks/hour_trade

# 4. 部署
vercel --prod
```

### 方法 2: GitHub 自动部署

```bash
# 1. 推送到 GitHub
./push_to_github.sh

# 2. 访问 Vercel Dashboard
# https://vercel.com/new

# 3. 导入 GitHub 仓库
# - 选择: github.com/xucheng2024/hour_trade
# - Framework Preset: Other
# - 点击 Deploy

# 4. 部署完成！
```

## ⚙️ 环境变量配置

在 Vercel Dashboard 配置以下环境变量：

**Settings → Environment Variables**

```bash
# 必需配置
DATABASE_URL=postgresql://your_connection_string
OKX_API_KEY=your_api_key
OKX_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase

# 可选配置
OKX_TESTNET=false
```

**重要**: 配置后需要重新部署：

```bash
vercel --prod
```

## 📁 部署文件结构

Vercel 只部署必需文件（`.vercelignore` 已配置）：

```
部署到 Vercel:
├── api/
│   └── index.py              ✅ API Handler
├── src/
│   ├── utils/
│   │   └── db_connection.py  ✅ 数据库连接
│   └── config/
│       └── okx_config.py     ✅ OKX配置
├── requirements.txt          ✅ 依赖
├── vercel.json              ✅ 配置
└── valid_crypto_limits.json  ✅ 币种配置

不部署（在 .vercelignore 中）:
- websocket_limit_trading.py  ❌ 后台服务
- trading_web_viewer.py        ❌ 本地开发
- src/crypto_remote/           ❌ 后台任务
- *.log                        ❌ 日志
- *.md                         ❌ 文档
```

## 🔍 验证部署

### 本地测试 API

```bash
# 测试 API 处理器
cd api
python index.py

# 访问: http://localhost:5000
```

### 部署后测试

```bash
# 健康检查
curl https://your-project.vercel.app/api/health

# 获取数据
curl https://your-project.vercel.app/api/orders

# 浏览器访问
open https://your-project.vercel.app
```

## 📊 Vercel 配置说明

### vercel.json

```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "api/index.py"
    }
  ],
  "env": {
    "PYTHON_VERSION": "3.11"
  },
  "functions": {
    "api/index.py": {
      "memory": 1024,
      "maxDuration": 10
    }
  }
}
```

**说明**:
- `builds`: 指定 Python 运行环境
- `routes`: 所有请求路由到 `api/index.py`
- `functions.memory`: 分配 1GB 内存
- `functions.maxDuration`: 最大执行 10 秒

### requirements.txt（已更新）

```txt
Flask==3.1.0                  ← Web框架
python-dotenv==1.0.1         ← 环境变量
psycopg[binary]>=3.2.0       ← PostgreSQL (v3, modern)
python-okx==0.4.0            ← OKX API
pandas==2.3.1                ← 数据处理
requests==2.32.4             ← HTTP请求
```

## 🎨 页面预览

### 主页 (/)

```
┌─────────────────────────────────────┐
│  📊 Trading Records                 │
├─────────────────────────────────────┤
│  Total Cryptos: 36                  │
│  Total Trades: 150                  │
│  Total Profit: +1,250.50 USDT       │
├─────────────────────────────────────┤
│  BTC-USDT                  +50 USDT │
│  ├─ 2026-01-14 10:30  BUY           │
│  └─ 2026-01-14 11:30  SELL          │
│                                     │
│  ETH-USDT                  +30 USDT │
│  ├─ 2026-01-14 09:15  BUY           │
│  └─ 2026-01-14 10:15  SELL          │
└─────────────────────────────────────┘
```

### API (/api/orders)

```json
{
  "success": true,
  "data": {
    "total_cryptos": 36,
    "total_trades": 150,
    "total_profit": 1250.50,
    "cryptos": {
      "BTC-USDT": {
        "profit": 50.00,
        "profit_pct": 2.5,
        "trades": [...]
      }
    }
  }
}
```

## 🔧 故障排除

### Issue: 部署失败

**检查**:
```bash
# 1. 验证 vercel.json 格式
cat vercel.json | python -m json.tool

# 2. 验证 requirements.txt
cat requirements.txt

# 3. 本地测试 API
cd api && python index.py
```

### Issue: 数据库连接失败

**解决**:
1. 在 Vercel Dashboard 检查 `DATABASE_URL`
2. 确认 Neon PostgreSQL 允许外部连接
3. 检查数据库表是否存在：
```bash
python init_database.py
```

### Issue: API 返回空数据

**原因**: 数据库中没有订单记录

**解决**: 运行交易机器人生成数据
```bash
python websocket_limit_trading.py
```

### Issue: 500 Internal Server Error

**查看日志**:
```bash
# Vercel Dashboard → Deployments → View Logs
# 或使用 CLI
vercel logs
```

## 📱 移动端适配

页面已支持响应式设计：
- ✅ 手机浏览器
- ✅ 平板浏览器
- ✅ 桌面浏览器

## 🔄 更新部署

```bash
# 1. 修改代码
git add .
git commit -m "Update API"
git push

# 2. Vercel 自动部署
# 或手动触发
vercel --prod
```

## 💰 费用说明

**Vercel Hobby Plan（免费）**:
- ✅ 100GB 带宽/月
- ✅ 无限请求
- ✅ 自动 HTTPS
- ✅ 全球 CDN
- ⚠️ 10 秒函数超时

**Pro Plan（$20/月）**:
- ✅ 1TB 带宽/月
- ✅ 60 秒函数超时
- ✅ 更多并发

## 🎯 性能优化

### 1. 数据库查询优化

```python
# 添加查询限制
cur.execute("""
    SELECT * FROM orders 
    WHERE flag = %s 
    ORDER BY create_time DESC 
    LIMIT 1000  ← 限制返回数量
""", (STRATEGY_NAME,))
```

### 2. 缓存策略

```python
# 添加 HTTP 缓存头
@app.after_request
def add_header(response):
    response.cache_control.max_age = 60  # 缓存60秒
    return response
```

### 3. 数据库连接池

```python
# 使用连接池
from psycopg.pool import ConnectionPool
pool = SimpleConnectionPool(1, 10, DATABASE_URL)
```

## 📊 监控和分析

### Vercel Analytics

在 Vercel Dashboard 启用：
- Settings → Analytics → Enable

查看：
- 访问量
- 响应时间
- 地理分布
- 错误率

### 自定义监控

```python
# 添加日志
import logging
logging.info(f"Orders fetched: {len(orders)}")
```

## 🔗 相关链接

- **Vercel Dashboard**: https://vercel.com/dashboard
- **Vercel 文档**: https://vercel.com/docs
- **GitHub 仓库**: https://github.com/xucheng2024/hour_trade
- **OKX API**: https://www.okx.com/docs-v5/en/

---

**状态**: ✅ Vercel 部署已配置完成

**部署命令**: `vercel --prod`

**仓库**: https://github.com/xucheng2024/hour_trade
