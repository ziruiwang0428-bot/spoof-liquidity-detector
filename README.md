# Spoof Liquidity Detector

一个面向链上限价单市场的蓝方 demo，用来识别“看起来提供流动性、但在价格接近成交前快速撤单”的可疑挂单行为。

> 说明：本项目不是对任何地址或交易所的定性指控工具，而是一个统计检测框架。输出应被理解为风险评分、告警线索和复核队列。

## 背景

一些交易所或链上协议会根据挂单深度、挂单时间、报价距离等指标给流动性奖励。攻击者可能会把大额订单挂在离成交价较远的位置来提高流动性指标，一旦市场价格接近该盘口，订单又快速撤掉。这样会让平台错误估计真实可成交流动性，也会影响做市奖励分配。

本 demo 先做蓝方检测：

- 标准化不同交易场所的订单事件数据
- 构造可疑特征，例如远离中价、短生命周期、接近成交前撤单、大额占比
- 用统计检验和打分模型输出可疑订单
- 保留接口，后续可以接入 Pendle、Polymarket 或第三方数据商

红方套利或执行策略不在本 demo 范围内。

## 数据源状态

- Pendle limit order: https://app.pendle.finance/limit-order
- Polymarket: 链接待补充。你当前给出的 Polymarket 链接和 Pendle 相同。

真实数据接入建议由数据商提供以下标准字段，或者在 `providers/` 里写适配器转换：

| 字段 | 含义 |
| --- | --- |
| `venue` | 交易场所，例如 `pendle` |
| `market` | 市场或合约 |
| `order_id` | 订单 ID |
| `maker` | 挂单地址或账户 |
| `side` | `buy` 或 `sell` |
| `price` | 挂单价格 |
| `quantity` | 挂单数量 |
| `event_type` | `open`, `cancel`, `fill` |
| `timestamp` | ISO 时间戳 |
| `mid_price` | 事件时刻中间价 |
| `best_bid` | 最优买价 |
| `best_ask` | 最优卖价 |

## 项目结构

```text
spoof_liquidity_detector/
  cli.py                    # 命令行入口
  pipeline.py               # 端到端检测流程
  schema.py                 # 标准事件、订单画像、告警结果
  providers/                # 数据源接口和适配器
  features/                 # 特征工程
  statistics/               # 统计检验与风险评分
examples/
  run_demo.py               # 最小运行示例
data/
  sample_order_events.csv   # demo 样例数据
tests/
  test_pipeline.py
```

## 快速开始

```bash
python -m spoof_liquidity_detector.cli --input data/sample_order_events.csv --top 10
```

或：

```bash
python examples/run_demo.py
```

输出示例：

```text
risk  p_value  order_id  maker      venue   market
0.91  0.0123   p-1003    0xAlpha    pendle  PT-sUSDe-2026
```

## 检测逻辑

当前 demo 使用可解释规则和统计检验组合：

- `distance_bps`: 挂单价格距离中间价的基点数
- `lifetime_seconds`: 从挂单到撤单/成交的生命周期
- `cancelled`: 是否撤单
- `approach_bps`: 撤单时订单价格距离最优盘口或中间价的距离
- `notional`: 价格乘数量，用于衡量订单规模
- `z_score`: 和同市场订单相比的异常程度
- `p_value`: 基于同市场经验分布的单尾检验

风险评分不是机器学习黑盒，而是便于 GitHub demo 展示和后续审计的解释型打分：

```text
risk = 短生命周期 + 撤单 + 远端挂单 + 接近成交前撤单 + 大额订单
```

## 接入真实数据

实现新的 provider：

```python
from spoof_liquidity_detector.providers.base import OrderEventProvider

class MyVenueProvider(OrderEventProvider):
    def load_events(self):
        ...
```

只要返回 `OrderEvent` 列表，就可以复用所有检测逻辑。

## 研发路线

- 接入 Pendle / Polymarket 数据商 API
- 按 maker 维度聚合可疑行为，例如撤单率、奖励窗口前后行为变化
- 加入生存分析或 Cox hazard model，估计“价格接近时撤单”的条件概率
- 增加 notebook 报告和可视化 dashboard
- 后续单独评估红方套利风险，但不和蓝方检测 demo 混在一起

## 合规说明

该项目用于市场完整性研究、风控、奖励机制审计和可疑流动性检测。不要把输出直接用于攻击、操纵市场或未经复核的公开指控。
