# 订单生命周期完整说明

## 🔄 完整流程（已修复所有问题）

### 1️⃣ **买入阶段**

```
触发条件: ticker价格 <= 限价
      ↓
提交限价买单 (place_order)
      ↓
立即记录到数据库
  - state = '' (空)
  - size = 预期数量
  - price = 限价
      ↓
加入 active_orders 字典
      ↓
启动1分钟超时检查线程
```

### 2️⃣ **1分钟超时检查**（关键修复）

```python
# 60秒后检查订单状态
time.sleep(60)

# 调用 API 获取订单实际状态
result = tradeAPI.get_order(instId=instId, ordId=ordId)

# 检查是否成交
filled_size = float(order_data['accFillSz'])
fill_price = order_data['fillPx']
state = order_data['state']

if filled_size > 0 or state in ['filled', 'partially_filled']:
    # ✅ 修复：更新数据库记录实际成交信息
    UPDATE orders SET 
        state = 'filled',
        size = <实际成交量>,
        price = <实际成交价>
    WHERE ordId = ...
    
    # 更新 active_orders 中的实际成交数据
    active_orders[instId]['filled_size'] = filled_size
    active_orders[instId]['fill_price'] = fill_price
    
    # 保留在 active_orders 等待卖出
else:
    # 未成交，取消订单
    tradeAPI.cancel_order(instId=instId, ordId=ordId)
    
    UPDATE orders SET state = 'canceled'
    
    # 从 active_orders 删除
    del active_orders[instId]
```

### 3️⃣ **卖出触发**

```
下一个整点小时K线确认
      ↓
on_candle_message 接收到 confirm='1'
      ↓
触发 process_sell_signal(instId)
```

### 4️⃣ **卖出前验证**（关键修复）

```python
# ✅ 修复 1: 检查 active_orders
if instId not in active_orders:
    return  # 没有活跃订单，跳过

# ✅ 修复 2: 从数据库查询状态和数量
SELECT state, size FROM orders WHERE instId = %s AND ordId = %s

# ✅ 修复 3: 防止重复卖出
if state == 'sold out':
    logger.warning("Already sold")
    del active_orders[instId]
    return

# ✅ 修复 4: 验证订单已成交
if state != 'filled' or size == '0':
    logger.warning("Order not filled")
    del active_orders[instId]
    return

# ✅ 修复 5: 使用实际成交数量
size = float(db_size)

# 提交市价卖单
sell_market_order(instId, ordId, size, tradeAPI, conn)

# ✅ 修复 6: 更新数据库
UPDATE orders SET 
    state = 'sold out',
    sell_price = <实际卖价>

# ✅ 修复 7: 卖出成功后删除
del active_orders[instId]
```

---

## 🛡️ 安全机制

### 1. **防止重复卖出**
```python
# 检查1：数据库状态
if db_state == 'sold out':
    return

# 检查2：加锁保护
with lock:
    if instId in active_orders:
        del active_orders[instId]

# 检查3：异常处理也会清理
except Exception as e:
    with lock:
        if instId in active_orders:
            del active_orders[instId]
```

### 2. **防止卖出未成交订单**
```python
# 验证订单状态
if db_state not in ['filled', '']:
    return

# 验证数量不为0
if not db_size or db_size == '0':
    return
```

### 3. **实际成交数量追踪**
```python
# 1分钟检查时更新
UPDATE orders SET 
    size = <API返回的实际成交量>

# 卖出时使用数据库的实际值
size = float(db_size)
```

---

## 📊 数据库状态流转

```
订单创建:
  state = '' (空字符串)
  size = 预期数量
  price = 限价

      ↓ [1分钟内成交]

订单成交:
  state = 'filled'
  size = 实际成交数量
  price = 实际成交价格

      ↓ [下一小时K线确认]

卖出完成:
  state = 'sold out'
  sell_price = 实际卖价

---

订单创建:
  state = '' (空字符串)

      ↓ [1分钟未成交]

订单取消:
  state = 'canceled'
  从 active_orders 删除
```

---

## 🔍 如何检查订单状态

### 方法 1：查询数据库
```sql
-- 查看所有活跃订单
SELECT instId, ordId, state, size, price, sell_price
FROM orders
WHERE flag = 'hourly_limit_ws'
  AND create_time > (EXTRACT(EPOCH FROM NOW()) - 86400) * 1000
ORDER BY create_time DESC;

-- 统计各状态订单数
SELECT state, COUNT(*) 
FROM orders 
WHERE flag = 'hourly_limit_ws' 
GROUP BY state;
```

### 方法 2：查看日志
```bash
# 查看买入记录
grep "buy limit DB" websocket_limit_trading.log

# 查看成交确认
grep "Order filled within 1 minute" websocket_limit_trading.log

# 查看卖出记录
grep "sell market DB" websocket_limit_trading.log

# 查看取消记录
grep "Canceled unfilled order" websocket_limit_trading.log
```

---

## ⚠️ 常见问题

### Q1: 订单1分钟内成交了，但没有卖出？
**A**: 检查数据库 `state` 字段：
```sql
SELECT state, size FROM orders WHERE ordId = 'xxx';
```
- 如果 `state = 'filled'`：正常，等待下一小时K线确认
- 如果 `state = ''`：异常，可能1分钟检查失败，手动更新

### Q2: 会不会重复卖出同一个订单？
**A**: 不会，有三重保护：
1. 卖出前检查 `state = 'sold out'`
2. 卖出后立即从 `active_orders` 删除
3. 异常时也会删除 `active_orders`

### Q3: 部分成交怎么处理？
**A**: 1分钟检查时会更新实际成交量：
```python
UPDATE orders SET size = <实际成交量>
```
卖出时使用数据库的实际值，不会多卖。

### Q4: 订单取消后会不会尝试卖出？
**A**: 不会，卖出前会检查：
```python
if db_state not in ['filled', '']:
    return
```

---

## 📝 测试建议

### 1. 模拟模式测试
```bash
# 设置环境变量
export SIMULATION_MODE=true

# 运行交易机器人
python3 websocket_limit_trading.py
```

### 2. 检查点
- [ ] 买入后立即查询数据库，确认记录创建
- [ ] 1分钟后查询数据库，确认 `state='filled'` 和实际 `size`
- [ ] 下一小时确认卖出，检查 `state='sold out'`
- [ ] 确认 `active_orders` 已清空

### 3. 压力测试
- 同时触发多个币种买入
- 验证无重复卖出
- 验证无遗漏卖出

---

## 🎯 总结

### ✅ 已修复的问题
1. ✅ 订单成交后数据库状态更新
2. ✅ 实际成交数量记录
3. ✅ 防止重复卖出
4. ✅ 防止卖出未成交订单
5. ✅ 异常情况的清理机制

### ✅ 核心保障
- **数据一致性**：数据库记录实际成交信息
- **幂等性**：重复调用不会重复卖出
- **健壮性**：异常情况下自动清理

### 🚀 生产环境建议
1. 定期检查数据库状态一致性
2. 监控日志中的异常信息
3. 备份交易记录
4. 测试后再使用真实资金
