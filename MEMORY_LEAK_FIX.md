# 内存泄漏修复方案

## 问题描述

在8:27时，Batch策略触发了购买，但Origin策略没有触发。经过分析发现：
- 数据库中没有未卖出的Origin订单
- 但内存中`active_orders`或`pending_buys`可能有残留数据
- 导致Origin策略在检查时被拦截（第334行：`if instId in pending_buys or instId in active_orders`）

## 根本原因

1. **卖出后清理不完整**：只有所有订单都成功卖出时才清理`active_orders`，如果有失败的就不清理
2. **程序重启后状态不同步**：内存清空但数据库中可能还有订单
3. **pending_buys超时未清理**：如果买入处理失败，`pending_buys`可能一直残留
4. **没有定期同步机制**：内存和数据库状态可能逐渐偏离

## 修复方案

### 1. 新增内存同步模块 ✅

创建 `src/core/memory_sync.py`：
- `sync_active_orders_with_db()` - 同步内存和数据库状态
  - 清理已sold out但还在内存中的订单
  - 恢复数据库中有但内存中缺失的订单
  - 清理超时的pending_buys
- `start_periodic_sync()` - 启动定期同步线程（默认5分钟）

### 2. 启动时初始化同步 ✅

在 `websocket_limit_trading.py` 主函数中：
- 程序启动后立即运行一次内存同步
- 启动后台定期同步线程（可通过环境变量`MEMORY_SYNC_INTERVAL_SECONDS`配置）

### 3. 买入时双重验证 ✅

在 `signal_processing.py` 的 `process_buy_signal()` 中：
- 查询数据库检查是否有未卖出订单（原有逻辑）
- **新增**：如果数据库中没有，但内存中有，自动清理内存残留
```python
if not recent_unsold:
    with lock:
        if instId in active_orders:
            logger.warning(f"🧹 Cleaned stale active_orders...")
            del active_orders[instId]
```

### 4. 改进卖出后清理逻辑 ✅

在 `signal_processing.py` 的 `process_sell_signal()` 中：
- 如果部分卖出失败，检查数据库是否还有未卖出订单
- 如果数据库中已经没有未卖出订单，清理内存（即使有失败记录）
```python
if unsold_count == 0:
    with lock:
        if instId in active_orders:
            del active_orders[instId]
```

### 5. pending_buys超时自动清理 ✅

**改进pending_buys结构**：
- 从 `Dict[str, bool]` 改为 `Dict[str, float]`（记录时间戳）
- 在买入检查时，如果pending超过60秒，自动清理并允许重试

在 `websocket_handlers.py` 中：
```python
if instId in pending_buys:
    pending_since = pending_buys[instId]
    elapsed = time.time() - pending_since
    if elapsed > 60:
        logger.warning(f"🧹 Cleaned stale pending_buys...")
        del pending_buys[instId]
```

### 6. 增加调试日志 ✅

在 `websocket_handlers.py` 中：
- 当Origin被跳过时，记录原因（pending还是active）
```python
logger.debug(
    f"⏭️ {instId} ORIGIN SKIPPED: "
    f"pending={instId in pending_buys}, "
    f"active={instId in active_orders}"
)
```

## 影响范围

### 修改的文件

1. ✅ `src/core/memory_sync.py` - 新增文件
2. ✅ `src/core/signal_processing.py` - 修改买入和卖出逻辑
3. ✅ `src/core/websocket_handlers.py` - 修改pending_buys记录方式，增加超时清理
4. ✅ `websocket_limit_trading.py` - 导入新模块，启动时初始化同步

### 涉及的策略

- ✅ Original策略（hourly_limit_ws）
- ✅ Gap策略（original_gap）
- ✅ Stable策略（stable_buy_ws）
- ✅ Batch策略（batch_buy_ws）

## 配置参数

新增环境变量：
- `MEMORY_SYNC_INTERVAL_SECONDS` - 内存同步间隔（默认：300秒 = 5分钟）

## 预期效果

1. **启动时状态一致**：程序重启后，内存自动从数据库恢复
2. **运行时自动清理**：每5分钟自动检查并清理内存泄漏
3. **实时清理残留**：买入和卖出时双重验证，发现不一致立即清理
4. **pending_buys超时保护**：超过60秒自动清理，避免长期阻塞
5. **数据库检查从2小时**：防止短时间内重复购买（之前是5分钟）

## 测试建议

1. 启动程序后检查日志：
   ```
   ✅ Initial memory sync completed
   ✅ Periodic memory sync started (interval: 300s)
   ```

2. 观察是否有清理日志：
   ```
   🧹 Cleaned stale active_orders: RSS3-USDT
   🧹 Cleaned stale pending_buys: XXX-USDT
   🔄 Restored missing memory: XXX-USDT
   ```

3. 触发买入信号时，检查是否有跳过日志：
   ```
   ⏭️ RSS3-USDT ORIGIN SKIPPED: pending for 5.2s
   ⏭️ RSS3-USDT ORIGIN SKIPPED: active order exists
   ```

## 回滚方案

如果出现问题，可以：
1. 设置环境变量 `MEMORY_SYNC_INTERVAL_SECONDS=0` 禁用定期同步
2. 注释掉启动时的同步调用
3. 或者直接删除 `src/core/memory_sync.py` 文件

## 注意事项

- pending_buys现在记录时间戳而不是bool，需要确保所有代码兼容
- 定期同步会增加数据库查询，但间隔5分钟影响很小
- 如果发现误清理，可以调整60秒超时参数

---

**修复完成时间**: 2026-02-07
**修复人**: AI Assistant
