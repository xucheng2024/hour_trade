# Vercel 部署完整指南

## 当前状态

- ✅ Vercel 项目已创建: `hour-trade`
- ✅ GitHub 仓库已推送: `xucheng2024/hour_trade`
- ❌ 还没有连接和部署

项目链接: https://vercel.com/xuchengs-projects-27b3e479/hour-trade

---

## 🚀 快速部署（5分钟完成）

### 步骤 1: 配置环境变量（必须先做！）

1. **访问环境变量设置**:
   ```
   https://vercel.com/xuchengs-projects-27b3e479/hour-trade/settings/environment-variables
   ```

2. **添加环境变量（只需要 1 个！）**:

   **DATABASE_URL**
   ```
   Key: DATABASE_URL
   Value: postgresql://neondb_owner:npg_F4epMLXJ8ity@ep-wispy-smoke-a1qg30ip-pooler.ap-southeast-1.aws.neon.tech/crypto_trading?sslmode=require&channel_binding=require
   Environment: Production (勾选)
   ```

   ⚠️ **不需要 OKX API 密钥！**
   
   Vercel 仪表板只是读取数据库，不调用 OKX API。
   OKX API 密钥只在交易机器人（本地/服务器）中使用。

3. **点击 "Save"**

---

### 步骤 2: 连接 GitHub 仓库

#### 方法 A: 通过网页（推荐）

1. **访问项目设置**:
   ```
   https://vercel.com/xuchengs-projects-27b3e479/hour-trade/settings/git
   ```

2. **点击 "Connect Git Repository"**

3. **选择 GitHub** 并授权 Vercel

4. **选择仓库**: `xucheng2024/hour_trade`

5. **点击 "Connect"**

6. **Vercel 会自动开始部署！**

#### 方法 B: 使用 CLI

```bash
cd /Users/mac/Downloads/stocks/hour_trade

# 安装 Vercel CLI（如果还没有）
npm install -g vercel

# 登录
vercel login

# 链接到现有项目
vercel link
# 选择: xuchengs-projects-27b3e479
# 选择: hour-trade

# 部署
vercel --prod
```

---

### 步骤 3: 等待部署完成

部署大约需要 **1-2 分钟**。

**查看部署进度**:
```
https://vercel.com/xuchengs-projects-27b3e479/hour-trade/deployments
```

你会看到：
- ⏳ Building...
- ✅ Ready

---

### 步骤 4: 访问你的仪表板

部署成功后，访问：
```
https://hour-trade.vercel.app
```

或者：
```
https://hour-trade-xuchengs-projects-27b3e479.vercel.app
```

---

## 🔍 验证部署

### 测试端点

1. **健康检查**:
   ```
   https://hour-trade.vercel.app/api/health
   ```
   
   应该返回:
   ```json
   {
     "status": "healthy",
     "timestamp": "2026-01-14T..."
   }
   ```

2. **交易数据 API**:
   ```
   https://hour-trade.vercel.app/api/orders
   ```

3. **Web 仪表板**:
   ```
   https://hour-trade.vercel.app/
   ```

---

## ⚠️ 常见问题

### 问题 1: 部署失败 - "Missing environment variables"

**解决**: 返回步骤 1，确保配置了所有 4 个环境变量

### 问题 2: 部署成功但显示错误

**检查**:
1. 查看部署日志: https://vercel.com/xuchengs-projects-27b3e479/hour-trade/deployments
2. 点击最新的部署 → 查看 "Logs"
3. 检查是否有数据库连接错误

**解决**:
- 确认 DATABASE_URL 正确
- 确认 Neon PostgreSQL 允许外部连接

### 问题 3: 页面空白

**原因**: 数据库中没有订单记录

**解决**: 运行交易机器人生成一些数据：
```bash
python websocket_limit_trading.py
```

---

## 📊 部署后的架构

```
GitHub
  └─ xucheng2024/hour_trade (代码仓库)
       ↓ (自动触发)
  Vercel
  └─ hour-trade (Web仪表板)
       ↓ (连接)
  Neon PostgreSQL (数据库)
       ↑ (写入数据)
  本地/服务器
  └─ websocket_limit_trading.py (交易机器人)
```

---

## 🔄 后续更新

每次推送到 GitHub，Vercel 会自动重新部署：

```bash
# 修改代码
git add .
git commit -m "Update something"
git push

# Vercel 自动检测并重新部署（约1分钟）
```

---

## 📱 自定义域名（可选）

如果你有自己的域名：

1. 访问: https://vercel.com/xuchengs-projects-27b3e479/hour-trade/settings/domains
2. 点击 "Add"
3. 输入你的域名
4. 按照提示配置 DNS

---

## 🔐 安全检查

✅ 环境变量已正确配置（在 Vercel，不在代码中）
✅ API 密钥不会暴露在公开仓库
✅ 数据库使用 SSL 连接
✅ Vercel 提供自动 HTTPS

---

## 📈 监控和分析

### 启用 Analytics

1. 访问: https://vercel.com/xuchengs-projects-27b3e479/hour-trade/analytics
2. 查看访问统计

### 查看日志

1. 访问: https://vercel.com/xuchengs-projects-27b3e479/hour-trade/logs
2. 实时查看函数调用日志

---

## 🎯 快速检查清单

部署前确认：

- [ ] 环境变量已配置（4个）
- [ ] GitHub 仓库已推送
- [ ] Vercel 项目已连接 GitHub
- [ ] 数据库表已初始化（`python init_database.py`）

部署后确认：

- [ ] 访问主页没有错误
- [ ] `/api/health` 返回正常
- [ ] `/api/orders` 可以访问
- [ ] 查看 Logs 没有错误信息

---

## 📞 需要帮助？

- **Vercel 文档**: https://vercel.com/docs
- **查看部署日志**: https://vercel.com/xuchengs-projects-27b3e479/hour-trade/deployments
- **环境变量设置**: https://vercel.com/xuchengs-projects-27b3e479/hour-trade/settings/environment-variables

---

**项目**: hour-trade  
**GitHub**: https://github.com/xucheng2024/hour_trade  
**Vercel**: https://vercel.com/xuchengs-projects-27b3e479/hour-trade  
**最后更新**: 2026-01-14
