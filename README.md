# AlphaCore

一套从零构建、具有高扩展性的量化回测框架底座 (V1.0 MVP)。

V1.0 聚焦基础架构的解耦设计，跑通基于日线数据 (Daily OHLCV) 的中低频策略回测闭环，
并保证未来升级到高频 Tick 级回测时顶层策略代码无需修改。

## 设计原则

- **纯自研引擎:** 不依赖任何现成回测/交易框架 (backtrader、vnpy、zipline、ccxt 等)。
- **依赖倒置:** 策略层不直接读取数据、不直接修改资金与持仓，统一通过向 `Broker` 发送 `Order` 通信。
- **杜绝未来函数:** 引擎在时刻 T 只能看到 ≤ T 的数据；T 时刻发出的订单在 T+1 撮合。

## 目录结构

```
AlphaCore/
├── core/
│   ├── __init__.py      # 包导出
│   ├── models.py        # 核心数据模型 (BarData / Order / Position + 枚举状态机)
│   └── data.py          # 数据源模块 (BaseDataFeed 抽象基类 / CSVDataFeed 实现)
├── docs/
│   └── PRD_v1.md        # 产品需求规格说明书 (唯一事实来源)
├── requirements.txt
└── README.md
```

## 环境要求

- Python 3.10+
- 依赖: `pandas`、`numpy`，测试使用 `pytest`

```bash
pip install -r requirements.txt
```

## 快速开始

```python
from core import CSVDataFeed

# CSV 需包含列: datetime, open, high, low, close, volume (symbol 列可选)
feed = CSVDataFeed("data/btcusdt.csv", symbol="BTCUSDT")

for bar in feed.get_next_bar():
    print(bar.datetime, bar.close)
```

## 开发进度

- [x] 核心数据模型 (`core/models.py`)
- [x] 数据源模块 (`core/data.py`)
- [ ] 策略基类 (`Strategy`)
- [ ] 撮合与账户模块 (`Broker`)
- [ ] 回测引擎主循环
- [ ] 单元测试 (见 PRD 第 5 节验收标准)
