# 多策略隔离机制说明

## 🎯 核心问题

**如果同一个OKX账户运行多个交易程序，如何确保它们不会互相干扰？**

---

## ✅ 当前隔离机制（已实现）

### 1. **数据库 flag 字段隔离**

每个策略有唯一的 `flag` 标识符：

```sql
-- hourly_limit_ws 策略的订单
SELECT * FROM orders WHERE flag = 'hourly_limit_ws';

-- 其他策略的订单
SELECT * FROM orders WHERE flag = 'crypto_remote';
SELECT * FROM orders WHERE flag = 'manual_trade';
```

**优点**：
- ✅ 永久记录，不会丢失
- ✅ 程序重启后仍有效
- ✅ 多个程序可以共享同一个数据库

**实现**：
```python
# 买入时记录 flag
cur.execute(
    "INSERT INTO orders (instId, flag, ordId, ...) VALUES (%s, %s, %s, ...)",
    (instId, STRATEGY_NAME, ordId, ...)  # STRATEGY_NAME = "hourly_limit_ws"
)

# 查询时过滤 flag
cur.execute(
    "SELECT * FROM orders WHERE instId = %s AND ordId = %s AND flag = %s",
    (instId, ordId, STRATEGY_NAME)
)
```

---

### 2. **内存 active_orders 字典隔离**

每个程序有独立的进程空间：

```python
# 程序 A（hourly_limit_ws）
active_orders = {
    'BTC-USDT': {'ordId': 'A123', ...},
    'ETH-USDT': {'ordId': 'A456', ...}
}

# 程序 B（另一个策略）- 不同进程
active_orders = {
    'BTC-USDT': {'ordId': 'B789', ...},  # ✅ 不会冲突
}
```

**优点**：
- ✅ 进程隔离，天然安全
- ✅ 快速查询，无需数据库

**限制**：
- ⚠️ 程序重启后丢失（但可从数据库恢复）

---

### 3. **订单ID (ordId) 精确匹配**

操作订单时使用交易所返回的唯一 `ordId`：

```python
# ✅ 只操作本程序创建的订单
result = tradeAPI.place_order(...)
ordId = result['data'][0]['ordId']  # 交易所生成的唯一ID

# 取消订单
tradeAPI.cancel_order(instId=instId, ordId=ordId)

# 查询订单
result = tradeAPI.get_order(instId=instId, ordId=ordId)
```

**优点**：
- ✅ 绝对唯一，交易所保证
- ✅ 不会误操作其他订单

---

### 4. **不订阅私有 WebSocket 频道**

当前实现：

```python
# ✅ 只订阅公共频道
ticker_url = 'wss://ws.okx.com:8443/ws/v5/public'    # Ticker价格
candle_url = 'wss://ws.okx.com:8443/ws/v5/business'  # K线数据

# ❌ 不订阅私有订单频道
# private_url = 'wss://ws.okx.com:8443/ws/v5/private'  # 所有账户订单
```

**优点**：
- ✅ 不会收到其他程序的订单信号
- ✅ 避免混淆

**缺点**：
- ⚠️ 无法实时感知订单状态变化（通过定时查询API弥补）

---

## 🔐 隔离验证示例

### 场景：两个程序同时交易 BTC-USDT

#### 程序 A：hourly_limit_ws
```python
# 1. 买入
tradeAPI.place_order(instId='BTC-USDT', ...)
# 返回 ordId = '12345'

# 2. 记录数据库
INSERT INTO orders (instId, flag, ordId, ...)
VALUES ('BTC-USDT', 'hourly_limit_ws', '12345', ...)

# 3. 记录内存
active_orders['BTC-USDT'] = {'ordId': '12345', ...}

# 4. 卖出时查询
SELECT * FROM orders 
WHERE instId = 'BTC-USDT' 
  AND ordId = '12345'      # ✅ 精确匹配
  AND flag = 'hourly_limit_ws'  # ✅ 策略过滤
```

#### 程序 B：crypto_remote
```python
# 1. 买入（同一个币种）
tradeAPI.place_order(instId='BTC-USDT', ...)
# 返回 ordId = '67890'  # ✅ 不同的ordId

# 2. 记录数据库
INSERT INTO orders (instId, flag, ordId, ...)
VALUES ('BTC-USDT', 'crypto_remote', '67890', ...)  # ✅ 不同的flag

# 3. 记录内存（不同进程）
active_orders['BTC-USDT'] = {'ordId': '67890', ...}  # ✅ 不会影响程序A

# 4. 卖出时查询
SELECT * FROM orders 
WHERE instId = 'BTC-USDT' 
  AND ordId = '67890'      # ✅ 只会找到自己的订单
  AND flag = 'crypto_remote'
```

**结果**：
- ✅ 两个程序互不干扰
- ✅ 数据库中有明确的记录
- ✅ 各自只操作自己的订单

---

## ⚠️ 潜在风险场景

### 风险 1：使用私有 WebSocket 但未过滤

**错误示例**：
```python
# ❌ 订阅私有订单频道
ws.send({
    "op": "subscribe",
    "args": [{"channel": "orders", "instType": "SPOT"}]
})

def on_order_message(ws, msg_string):
    data = json.loads(msg_string)
    for order in data['data']:
        ordId = order['ordId']
        instId = order['instId']
        
        # ❌ 直接处理，没有验证是否是本程序的订单
        active_orders[instId] = {'ordId': ordId, ...}
```

**问题**：
- 会收到所有程序的订单更新
- 可能覆盖 `active_orders` 中的其他订单

**正确做法**：
```python
def on_order_message(ws, msg_string):
    data = json.loads(msg_string)
    for order in data['data']:
        ordId = order['ordId']
        instId = order['instId']
        
        # ✅ 验证是否是本程序的订单
        with lock:
            # 方法1：检查是否在active_orders中
            if instId not in active_orders:
                continue
            if active_orders[instId]['ordId'] != ordId:
                continue
            
            # 方法2：查询数据库验证flag
            cur.execute(
                "SELECT 1 FROM orders WHERE ordId = %s AND flag = %s",
                (ordId, STRATEGY_NAME)
            )
            if not cur.fetchone():
                continue  # 不是本程序的订单
        
        # 现在可以安全处理
        logger.info(f"Order update: {ordId}")
```

---

### 风险 2：手动交易干扰

**场景**：
- 程序A自动买入 BTC-USDT
- 用户手动在OKX APP/网页卖出 BTC-USDT

**当前保护**：
```python
# 卖出前验证订单状态
cur.execute(
    "SELECT state, size FROM orders WHERE ordId = %s AND flag = %s",
    (ordId, STRATEGY_NAME)
)

# 如果用户手动卖了，程序不会找到这个订单
if not row:
    logger.error("Order not found")
    return
```

**建议**：
- ⚠️ 避免手动操作程序管理的币种
- ✅ 或者手动操作后，从数据库删除对应记录

---

## 🚀 增强隔离方案

### 方案 1：使用 clOrdId（客户端订单ID）

OKX API 支持自定义客户端订单ID：

```python
import uuid

# 生成带策略前缀的客户端订单ID
clOrdId = f"HLW-{uuid.uuid4().hex[:16]}"  # HLW = Hourly Limit WS

# 下单时指定
result = tradeAPI.place_order(
    instId=instId,
    tdMode="cash",
    side="buy",
    ordType="limit",
    px=buy_price,
    sz=size,
    clOrdId=clOrdId  # ✅ 自定义ID
)

# 后续可以通过 clOrdId 查询
result = tradeAPI.get_order(instId=instId, clOrdId=clOrdId)
```

**优点**：
- ✅ 可以通过前缀识别订单来源
- ✅ 支持通过 clOrdId 查询订单
- ✅ 便于调试和追踪

**示例命名规则**：
```
HLW-abc123def456  # hourly_limit_ws 策略
CRM-xyz789ghi012  # crypto_remote 策略
MAN-aaa111bbb222  # manual 手动交易
```

---

### 方案 2：独立的数据库表

为每个策略创建独立的订单表：

```sql
-- hourly_limit_ws 策略
CREATE TABLE orders_hourly_limit_ws (
    id SERIAL PRIMARY KEY,
    instId VARCHAR(50),
    ordId VARCHAR(100),
    ...
);

-- crypto_remote 策略
CREATE TABLE orders_crypto_remote (
    id SERIAL PRIMARY KEY,
    instId VARCHAR(50),
    ordId VARCHAR(100),
    ...
);
```

**优点**：
- ✅ 完全隔离
- ✅ 不需要 flag 字段过滤

**缺点**：
- ⚠️ 需要修改代码
- ⚠️ 不利于全局统计

---

### 方案 3：订单状态恢复机制

程序启动时从数据库恢复 `active_orders`：

```python
def restore_active_orders_from_db():
    """Restore active orders from database on startup"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # 查询未完成的订单
    cur.execute("""
        SELECT instId, ordId, price, size, sell_time
        FROM orders
        WHERE flag = %s 
          AND state IN ('', 'filled')  -- 未卖出的订单
          AND create_time > %s  -- 最近24小时
    """, (STRATEGY_NAME, (time.time() - 86400) * 1000))
    
    rows = cur.fetchall()
    
    for row in rows:
        instId = row[0]
        ordId = row[1]
        
        # 验证订单是否真的存在
        result = tradeAPI.get_order(instId=instId, ordId=ordId)
        if result and result.get('code') == '0':
            order_data = result['data'][0]
            state = order_data.get('state', '')
            
            # 只恢复已成交的订单
            if state == 'filled':
                active_orders[instId] = {
                    'ordId': ordId,
                    'buy_price': float(row[2]),
                    'buy_time': datetime.now(),
                    'next_hour_close_time': datetime.fromtimestamp(row[4] / 1000)
                }
                logger.warning(f"Restored active order: {instId}, {ordId}")
    
    cur.close()
    conn.close()
    
    logger.warning(f"Restored {len(active_orders)} active orders")

# 程序启动时调用
if __name__ == "__main__":
    restore_active_orders_from_db()
    main()
```

---

## 📊 隔离机制对比

| 方案 | 隔离强度 | 实现难度 | 性能 | 推荐度 |
|------|---------|---------|------|--------|
| flag字段 | ⭐⭐⭐⭐ | 简单 | 高 | ✅ 推荐 |
| clOrdId | ⭐⭐⭐⭐⭐ | 简单 | 高 | ✅ 推荐 |
| 独立表 | ⭐⭐⭐⭐⭐ | 中等 | 中 | ⚠️ 可选 |
| 进程隔离 | ⭐⭐⭐⭐⭐ | 免费 | 高 | ✅ 默认 |

---

## 🎯 最佳实践

### 1. 策略命名规范
```python
# 使用清晰的策略名称
STRATEGY_NAME = "hourly_limit_ws"   # ✅ 描述性强
# 避免
STRATEGY_NAME = "strategy1"         # ❌ 不明确
```

### 2. 订单追踪
```python
# 始终使用三元组验证
WHERE instId = %s 
  AND ordId = %s 
  AND flag = %s
```

### 3. 日志记录
```python
logger.warning(f"{STRATEGY_NAME} buy: {instId}, ordId={ordId}")  # ✅ 包含策略名
logger.warning(f"buy: {instId}")  # ❌ 无法区分来源
```

### 4. 定期清理
```sql
-- 删除旧的已完成订单（保留最近7天）
DELETE FROM orders 
WHERE flag = 'hourly_limit_ws' 
  AND state = 'sold out'
  AND create_time < (EXTRACT(EPOCH FROM NOW()) - 604800) * 1000;
```

---

## ✅ 总结

### 当前机制已足够安全：
1. ✅ 数据库 `flag` 字段隔离
2. ✅ 进程独立 `active_orders`
3. ✅ 订单ID精确匹配
4. ✅ 不订阅私有WebSocket

### 如需更强隔离，可添加：
1. ⭐ clOrdId 客户端订单ID
2. ⭐ 启动时恢复active_orders
3. ⭐ 订单前缀命名规范

**结论：当前架构已经很安全，多个程序可以共存！** 🎉
