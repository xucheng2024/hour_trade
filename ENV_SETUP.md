# 环境变量配置说明

## ⚠️ 重要：变量名说明

代码中使用的变量名是：
- `OKX_API_KEY` ✅
- `OKX_SECRET` ✅（注意：不是 `OKX_SECRET_KEY`）
- `OKX_PASSPHRASE` ✅

## .env 文件格式

在 `.env` 文件中应该这样设置：

```bash
# OKX API 凭证
OKX_API_KEY=your_api_key_here
OKX_SECRET=your_secret_key_here
OKX_PASSPHRASE=your_passphrase_here

# 数据库连接
DATABASE_URL=postgresql://your_connection_string

# 模拟模式（true=模拟，false=真实交易）
SIMULATION_MODE=true

# 交易金额（每次交易使用的USDT数量）
TRADING_AMOUNT_USDT=100
```

## 常见问题

### 错误：OKX_SECRET not found

如果遇到 `OKX_SECRET not found` 错误，检查 `.env` 文件中是否使用了错误的变量名：

❌ 错误：
```bash
OKX_SECRET_KEY=your_secret  # 错误！应该是 OKX_SECRET
```

✅ 正确：
```bash
OKX_SECRET=your_secret  # 正确！
```

## 检查环境变量

```bash
# 使用 Python 检查
python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print('OKX_SECRET:', 'SET' if os.getenv('OKX_SECRET') else 'NOT SET')"
```

## 编辑 .env 文件

```bash
# 使用 nano 编辑
nano .env

# 或使用 vim
vim .env

# 或使用其他编辑器
code .env  # VS Code
```
