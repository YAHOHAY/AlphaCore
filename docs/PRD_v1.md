# 量化回测系统 (AlphaCore) V1.0 产品需求规格说明书

**版本:** V1.0  

**定位:** 最小可行性产品 (MVP) - 纯面向对象 (OOP) 基础底座  

## 1. 项目概述

### 1.1 项目目标

搭建一套具有高扩展性的量化回测框架底座。V1.0 版本重点实现基础架构的解耦设计，并跑通基于日线数据（Daily OHLCV）的中低频策略回测闭环。核心目标是验证系统架构的合理性，确保未来升级到高频 Tick 级回测时，顶层策略代码无需修改。

### 1.2 不在 V1.0 范围内的功能 (Out of Scope)

* 接入真实交易所 API 或实盘交易。

* 复杂的订单类型（如限价单 LIMIT、止损单 STOP、冰山单）。V1.0 仅支持市价单 (MARKET)。

* 保证金交易与做空机制 (Short Selling)。V1.0 仅支持现货做多。

* 分布式计算或多进程参数寻优。

* 复杂的数据库对接。V1.0 数据源仅依赖本地 CSV 文件。

---

## 2. 核心业务数据字典 (Data Models)

系统内部流转的数据必须严格使用以下定义的数据类（推荐使用 Python `@dataclass`）。

### 2.1 枚举类型 (Enums)

* `OrderDirection`: `BUY` (买入), `SELL` (卖出)

* `OrderType`: `MARKET` (市价单)

* `OrderStatus`: `PENDING` (待处理), `FILLED` (完全成交), `REJECTED` (拒单)

### 2.2 K线数据结构 (BarData)

* `symbol` (str): 交易标的代码 (如 "BTCUSDT")。

* `datetime` (datetime): K线时间戳。

* `open` (float): 开盘价。

* `high` (float): 最高价。

* `low` (float): 最低价。

* `close` (float): 收盘价。

* `volume` (float): 成交量。

### 2.3 订单对象 (Order)

* `order_id` (str): 全局唯一订单号 (UUID)。

* `symbol` (str): 交易标的。

* `direction` (OrderDirection): 买卖方向。

* `order_type` (OrderType): 订单类型。

* `volume` (float): 委托数量。

* `status` (OrderStatus): 订单当前状态。默认为 `PENDING`。

### 2.4 持仓对象 (Position)

* `symbol` (str): 交易标的。

* `volume` (float): 当前持有数量。

* `average_price` (float): 持仓均价（加权平均成本）。

---

## 3. 模块接口定义与职责 (Interfaces)

系统必须遵守依赖倒置原则。策略不能直接修改资金和持仓，必须通过发送 `Order` 给 `Broker` 执行。

### 3.1 DataFeed (数据源模块)

* **职责:** 读取本地 CSV 文件，清洗数据，并模拟时间的推移。

* **核心方法:**

  * `__init__(filepath: str)`: 加载 CSV 数据。如果存在缺失值 (NaN)，必须使用前向填充 (Forward Fill) 处理。

  * `get_next_bar() -> Generator[BarData]`: 这是一个生成器，每次 yield 出一根 `BarData`，直到数据结束。

### 3.2 Strategy (策略基类模块)

* **职责:** 提供标准化的策略编写模板，维护用户定义的指标状态。

* **核心方法:**

  * `__init__(broker)`: 绑定底层的撮合引擎。

  * `on_init()`: 策略启动前的计算（如预加载历史数据计算均线）。

  * `on_bar(bar: BarData)`: 核心回调函数。每当 DataFeed 吐出一根新 K 线时触发。

  * `buy(symbol, volume)`: 包装函数，内部向 broker 发送 BUY Order。

  * `sell(symbol, volume)`: 包装函数，内部向 broker 发送 SELL Order。

### 3.3 Broker (撮合与账户模块)

* **职责:** 接收并撮合订单，管理资金 (Cash) 和计算总净值 (Net Value)。

* **核心属性:**

  * `cash` (float): 当前可用现金。

  * `positions` (Dict[str, Position]): 当前持仓字典。

  * `pending_orders` (List[Order]): 等待撮合的订单队列。

* **核心方法:**

  * `submit_order(order: Order)`: 接收策略发出的订单。进行前置风控拦截（见 4.3 节），若通过则放入 `pending_orders`。

  * `match_orders(bar: BarData)`: 核心撮合逻辑。在新 bar 到来时执行（见第 4 节数学模型）。

---

## 4. 核心数学模型与风控逻辑 (Critical Logic)

### 4.1 撮合时机 (无未来函数保证)

* 策略在第 T 根 K 线的 `on_bar(bar_T)` 中计算出信号，并发出订单。

 *该订单进入队列，**必须**在第 T+1 根 K 线的 `open` (开盘价) 被撮合成交。

### 4.2 滑点与手续费计算模型

设基准成交价为 $P_{open}$，滑点比例为 $S$ (如 0.001)，手续费率为 $C$ (如 0.0005)，成交量为 $V$。

* **真实成交价 ($P_{fill}$):**

  * 买单: $P_{fill} = P_{open} \times (1 + S)$

  * 卖单: $P_{fill} = P_{open} \times (1 - S)$

* **单笔手续费 (Fee):** $Fee = P_{fill} \times V \times C$

* **买入扣款逻辑:** $Cash = Cash - (P_{fill} \times V) - Fee$

* **卖出收款逻辑:** $Cash = Cash + (P_{fill} \times V) - Fee$

### 4.3 前置风控与异常拦截

* **资金不足限制:** 在 `submit_order` 买入时，若估算所需资金 `(bar.close * volume) > cash`，将订单状态置为 `REJECTED` 并打回。

* **无仓位防做空限制:** 在 `submit_order` 卖出时，若当前持仓 `volume < 订单 volume`，将订单状态置为 `REJECTED` 并打回。

---

## 5. 验收标准 (Acceptance Criteria)

V1.0 代码编写完成后，必须通过以下单元测试：

1. **测试用例:** 初始化资金 $100,000，滑点 $0.1\%$，手续费 $0.05\%$。

2. **模拟场景:** T 日生成市价买入单 (10个单位)，T+1 日以 $100 的开盘价撮合。

3. **断言目标 (Assert):**

   * 真实成交价必须精确等于 $100.1$

   * 手续费扣除必须精确等于 $0.5005$

   * 剩余可用现金必须精确等于 $98998.4995$

   * T+1 日结束时持仓均价计算无误。