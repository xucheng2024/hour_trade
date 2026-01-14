# Railway 部署指南

## 🚀 快速部署（5分钟完成）

### 前置条件

- ✅ GitHub 仓库已推送代码
- ✅ Railway 账号（使用 GitHub 登录）
- ✅ Neon PostgreSQL 数据库 URL
- ✅ OKX API 凭证

---

## 步骤 1: 创建 Railway 项目

1. **访问 Railway**
   - 打开 https://railway.app
   - 使用 GitHub 账号登录

2. **创建新项目**
   - 点击 "New Project"
   - 选择 "Deploy from GitHub repo"
   - 选择你的仓库：`xucheng2024/hour_trade`

3. **Railway 会自动检测项目**
   - 检测到 Python 项目
   - 自动识别 `requirements_railway.txt` 或 `requirements.txt`
   - 自动识别 `Procfile`（使用 `web:` 命令）

---

## 步骤 2: 配置环境变量

**重要**: 环境变量必须在 **Service 级别**配置，不是 Project 级别！

在 Railway Dashboard 中：

1. **点击服务卡片（hour_trade）**，进入服务详情页

2. **点击 "Variables" 标签**

3. **确保在 "Service Variables" 区域**（不是 Project Variables）

4. **添加以下环境变量**（点击 "+ New Variable"）：

```bash
# 数据库连接（与 Vercel 使用相同的 Neon 数据库）
DATABASE_URL=postgresql://neondb_owner:npg_F4epMLXJ8ity@ep-wispy-smoke-a1qg30ip-pooler.ap-southeast-1.aws.neon.tech/crypto_trading?sslmode=require&channel_binding=require

# OKX API 凭证
OKX_API_KEY=your_api_key_here
OKX_SECRET=your_secret_here
OKX_PASSPHRASE=your_passphrase_here

# 交易配置
TRADING_AMOUNT_USDT=100
SIMULATION_MODE=true

# 策略名称（可选，默认已设置）
STRATEGY_NAME=hourly_limit_ws
```

5. **点击 "Save"** 保存所有环境变量

6. **重要**: 配置环境变量后，必须**重新部署**（Redeploy）才能生效！
   - 方法1: 点击 "Deployments" → 最新部署 → "Redeploy"
   - 方法2: 做一个小改动并推送到GitHub触发自动部署

---

## 步骤 3: 配置部署设置

1. **进入项目 → Settings → Service**

2. **确保以下设置**：
   - **Start Command**: `python websocket_limit_trading.py`（自动从 Procfile 读取）
   - **Restart Policy**: `ON_FAILURE`（应用崩溃时自动重启）

3. **资源限制**（免费额度）：
   - CPU: 共享 CPU（免费）
   - Memory: 512MB（免费额度内）
   - 对于交易机器人足够使用

---

## 步骤 4: 部署

1. **Railway 会自动开始部署**
   - 检测到代码推送后自动部署
   - 或点击 "Deploy" 手动触发

2. **查看部署日志**
   - 在 Dashboard 中点击 "Deployments"
   - 查看实时日志输出

3. **等待部署完成**
   - 通常需要 1-2 分钟
   - 看到 "✅ Deployed" 表示成功

---

## 步骤 5: 验证运行状态

1. **查看日志**
   - 在 Dashboard 中点击 "Logs"
   - 应该看到：
     ```
     Starting hourly_limit_ws trading system
     Loaded X cryptos with limits
     ✅ Connected to PostgreSQL database successfully
     WebSocket connections started, waiting for messages...
     ```

2. **检查运行状态**
   - Dashboard 显示 "Running" 状态
   - 日志持续输出（每60秒状态更新）

3. **测试功能**
   - 查看 Vercel Dashboard 是否显示新的交易记录
   - 检查数据库是否有新订单

---

## 📊 监控和管理

### 查看日志

```bash
# 在 Railway Dashboard 中
# 项目 → Logs → 实时查看
```

### 查看指标

- **CPU 使用率**: Dashboard → Metrics
- **内存使用**: Dashboard → Metrics
- **网络流量**: Dashboard → Metrics

### 重启应用

**方法1: 快速重启（推荐）**
- Dashboard → 点击服务卡片（hour_trade）
- 点击右上角菜单（三个点）→ 选择 "Restart"

**方法2: 重新部署**
- Dashboard → Deployments → 点击最新部署 → "Redeploy"

**重要**: 配置环境变量后**必须重启**应用才能生效！

### 停止应用

- Dashboard → Service → 点击 "Stop"
- 注意：停止后不会自动运行

---

## 🔧 故障排查

### 问题 1: 部署失败

**可能原因**:
- 依赖安装失败
- Python 版本不兼容

**解决方法**:
1. 检查 `requirements_railway.txt` 是否存在
2. 查看部署日志中的错误信息
3. 确保 Python 版本为 3.11+

### 问题 2: 应用启动后立即退出 / 找不到环境变量

**可能原因**:
- 环境变量未配置或配置在错误的级别（Project vs Service）
- 环境变量配置后没有重新部署
- 环境变量名称拼写错误

**解决方法**:
1. **确认环境变量在 Service 级别**：
   - 点击服务卡片（hour_trade）→ Variables
   - 确保在 "Service Variables" 区域，不是 "Project Variables"
   
2. **检查环境变量名称**（大小写敏感）：
   - 必须是 `DATABASE_URL`（全大写）
   - 不能是 `database_url` 或 `Database_Url`
   
3. **配置后必须重新部署**：
   - 不是仅仅重启，需要 Redeploy
   - Deployments → 最新部署 → Redeploy
   
4. 验证 `DATABASE_URL` 是否正确（与Vercel使用相同的URL）
5. 查看日志中的错误信息

### 问题 3: WebSocket 连接失败

**可能原因**:
- 网络问题
- OKX API 凭证错误

**解决方法**:
1. 检查 `OKX_API_KEY`, `OKX_SECRET`, `OKX_PASSPHRASE` 是否正确
2. 查看日志中的 WebSocket 错误信息
3. Railway 的网络通常很稳定，问题多在 API 凭证

### 问题 4: 应用运行一段时间后停止

**可能原因**:
- 超出免费额度
- 内存不足

**解决方法**:
1. 检查 Dashboard → Usage 查看资源使用
2. 如果超出免费额度，需要升级到付费计划
3. 优化代码减少资源使用

---

## 💰 成本管理

### 免费额度

- **$5/月免费额度**
- 对于小型交易机器人通常足够
- 主要消耗：CPU 和内存

### 监控使用量

- Dashboard → Usage → 查看当前使用量
- 设置告警：Usage → Alerts

### 超出额度

- Railway 会发送邮件通知
- 需要添加付款方式继续运行
- 或优化代码减少资源使用

---

## 🔄 更新代码

### 自动部署

1. **推送代码到 GitHub**
   ```bash
   git add .
   git commit -m "Update trading bot"
   git push
   ```

2. **Railway 自动检测并部署**
   - 通常 1-2 分钟内完成
   - 在 Dashboard 中查看部署状态

### 手动部署

- Dashboard → Deployments → 点击 "Redeploy"

---

## 📝 环境变量说明

| 变量名 | 必需 | 说明 | 示例 |
|--------|------|------|------|
| `DATABASE_URL` | ✅ | Neon PostgreSQL 连接字符串 | `postgresql://...` |
| `OKX_API_KEY` | ✅ | OKX API Key | `your_key` |
| `OKX_SECRET` | ✅ | OKX API Secret | `your_secret` |
| `OKX_PASSPHRASE` | ✅ | OKX API Passphrase | `your_passphrase` |
| `TRADING_AMOUNT_USDT` | ❌ | 每次交易金额（默认100） | `100` |
| `SIMULATION_MODE` | ❌ | 模拟模式（默认true） | `true` |
| `STRATEGY_NAME` | ❌ | 策略名称（默认已设置） | `hourly_limit_ws` |

---

## ✅ 部署检查清单

部署前确认：

- [ ] GitHub 仓库已推送最新代码
- [ ] `requirements_railway.txt` 已创建
- [ ] `Procfile` 已创建
- [ ] `railway.json` 已创建（可选）
- [ ] 所有环境变量已配置
- [ ] `DATABASE_URL` 正确（与 Vercel 相同）
- [ ] OKX API 凭证正确
- [ ] `SIMULATION_MODE=true`（首次部署建议）

部署后验证：

- [ ] 应用状态显示 "Running"
- [ ] 日志显示 "WebSocket connections started"
- [ ] 没有错误信息
- [ ] Vercel Dashboard 可以正常访问
- [ ] 数据库连接正常

---

## 🎉 完成！

部署成功后，你的交易机器人将：

- ✅ 24/7 持续运行
- ✅ 自动重启（如果崩溃）
- ✅ 自动部署（代码更新时）
- ✅ 实时日志查看
- ✅ 资源监控

**恭喜！你的交易机器人现在在云端自动运行了！** 🚀

---

## 📚 相关文档

- [Railway 官方文档](https://docs.railway.app)
- [项目部署分析](./CLOUD_DEPLOYMENT_ANALYSIS.md)
- [环境变量设置](./ENV_SETUP.md)
