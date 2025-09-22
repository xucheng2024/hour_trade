# V-shaped Reversal Strategy Research

V型反转策略研究模块 - 基于小时数据检测和交易V型反转模式

## 📊 策略概述

V型反转策略旨在捕捉加密货币市场中的短期V型反转模式：

1. **检测阶段**: 识别快速下跌后快速恢复的V型价格模式
2. **确认阶段**: 在价格恢复到一定水平后确认模式
3. **交易阶段**: 在恢复确认后买入，持有20小时后卖出

## 🎯 策略参数

### V型模式检测参数
- **最小下跌深度**: 3-25% (可配置)
- **最小恢复比例**: 70% (从底部恢复到起点的70%)
- **最大总时间**: 48小时 (从开始下跌到恢复完成)
- **最大恢复时间**: 24小时 (从底部到恢复的时间)

### 交易参数
- **入场时机**: V型恢复确认后下一小时
- **持有时间**: 20小时 (固定)
- **退出方式**: 仅固定时间退出，无止损止盈
- **最小模式质量**: 0.2 (基于深度、速度、成交量的综合评分)

## 📁 文件结构

```
v_reversal_research/
├── __init__.py                    # 模块初始化
├── data_loader.py                 # 数据加载器
├── v_pattern_detector.py          # V型模式检测器
├── v_strategy_backtester.py       # 策略回测系统
├── run_v_analysis.py             # 分析运行器
└── README.md                     # 说明文档
```

## 🚀 快速开始

### 运行分析

```bash
# 进入V型反转研究目录
cd v_reversal_research

# 运行完整分析
python run_v_analysis.py

# 或者直接快速测试
python -c "from run_v_analysis import quick_test; quick_test()"
```

### 选项
1. **快速测试**: 3个币种，3个月数据
2. **完整分析**: 5个币种，6个月数据  
3. **自定义分析**: 自定义币种和时间范围

## 📈 分析流程

### 1. 数据加载
- 从现有OKX数据基础设施加载小时K线数据
- 添加技术指标（移动平均线、波动率等）
- 数据预处理和格式标准化

### 2. V型模式检测
- 寻找局部高点作为下跌起点
- 识别符合条件的底部位置
- 验证恢复速度和程度
- 计算模式质量分数

### 3. 策略回测
- 模拟V型恢复确认后的买入
- 固定持有20小时后退出
- 计算交易收益率和持有时间
- 不使用止损止盈，纯粹测试V型反转效果

### 4. 结果分析
- 胜率和平均收益统计
- 夏普比率计算
- 不同退出原因的收益分析
- 各币种表现对比

## 📊 输出结果

### 控制台输出
- V型模式检测结果
- 策略回测性能统计
- 详细的交易分析报告

### JSON结果文件
保存在 `../data/v_reversal_analysis_TIMESTAMP.json`，包含：
- 检测器和回测器配置
- 所有检测到的V型模式详情
- 交易记录和性能统计
- 汇总分析结果

## 🔧 核心算法

### V型模式检测算法
1. **局部高点识别**: 使用滑动窗口找到价格局部最高点
2. **底部搜索**: 在高点后寻找满足深度要求的局部最低点
3. **恢复验证**: 检查价格是否在规定时间内恢复到阈值
4. **质量评分**: 基于深度、速度、成交量综合评分
5. **重叠过滤**: 移除重叠模式，保留质量最高的

### 质量评分公式
```
质量分数 = 深度分数 × 0.4 + 速度分数 × 0.4 + 成交量分数 × 0.2

其中:
- 深度分数 = min(下跌深度 / 15%, 1.0)
- 速度分数 = max(0, 1.0 - 恢复时间 / 24小时)  
- 成交量分数 = min(底部成交量放大倍数 / 3.0, 1.0)
```

## 📝 使用示例

```python
from v_reversal_research.data_loader import VReversalDataLoader
from v_reversal_research.v_pattern_detector import VPatternDetector
from v_reversal_research.v_strategy_backtester import VReversalBacktester

# 加载数据
loader = VReversalDataLoader()
data = loader.load_multiple_symbols(['BTC-USDT', 'ETH-USDT'], months=3)

# 检测V型模式
detector = VPatternDetector()
patterns = detector.detect_patterns(data['BTC-USDT'])

# 回测策略 (固定20小时持有，无止损止盈)
backtester = VReversalBacktester(holding_hours=20)
results = backtester.backtest_multiple_symbols(data, detector)
```

## ⚠️ 注意事项

1. **数据依赖**: 需要充足的小时K线历史数据
2. **参数敏感性**: V型检测参数对结果影响较大，建议多次测试
3. **市场环境**: 策略在不同市场环境下表现可能差异较大
4. **交易费用**: 已考虑0.1%的单边交易费用
5. **滑点影响**: 实际交易中可能存在滑点，影响收益

## 🔄 未来改进

- [ ] 添加更多技术指标辅助检测
- [ ] 实现动态参数优化
- [ ] 增加市场环境分类分析
- [ ] 支持更多时间框架分析
- [ ] 添加风险管理模块
