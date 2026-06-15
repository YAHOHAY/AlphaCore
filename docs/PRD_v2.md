# 量化回测系统 (AlphaCore) V2.0 产品需求规格说明书

**版本:** V2.0

**状态:** Confirmed

**定位:** 在 V1.0 回测闭环之上补齐「绩效评估 + 订单类型扩展 + 可视化报告」三大能力

---

## 1. 项目概述

### 1.1 背景与目标

V1.0 已跑通基于日线数据、仅市价单的回测闭环，但存在两个核心短板：

1. 只产出净值曲线，**无法量化评估**策略表现（收益、回撤、风险调整收益等）。
2. 订单类型**仅支持市价单 (MARKET)**，无法表达常见的限价、止损交易意图。

V2.0 的目标是让回测结果**可评估、可信、可呈现**，并将订单能力扩展到限价单 (LIMIT) 与止损单 (STOP)，同时延续 V1.0 的解耦架构与无未来函数原则。

### 1.2 不在 V2.0 范围内的功能 (Out of Scope)

* 做空机制与保证金交易 (Short Selling / Margin)。V2.0 仍仅支持现货做多。

* 多标的 / 投资组合回测 (Portfolio)。V2.0 仍以单标的回测为主。

* 参数寻优与多进程并行。

* 技术指标库 (MA / RSI / MACD 等)。

* 数据源扩展（Parquet / 数据库 / 多周期重采样）。V2.0 数据源仍为本地 CSV。

> 以上功能列为 V3.0 候选。

---

## 2. 技术约束 (Constraints)

1. **延续 V1.0 库约束:** 仅允许 Python 标准库、`pandas`、`numpy`；测试使用 `pytest`。绝对禁止任何第三方回测/交易框架。

2. **可视化例外:** 可视化报告模块允许引入 `matplotlib` 用于绘图，需在 `requirements.txt` 中新增。

3. **延续 V1.0 编码规范:** Python 3.10+；强制类型注解；数据结构使用 `@dataclass`；类与核心方法须有 Google Style docstring。

4. **无未来函数 (No Lookahead Bias):** 所有新增撮合逻辑必须保证引擎在时刻 T 只能看到 ≤ T 的数据；T 时刻提交的订单最早在 T+1 根 K 线被评估撮合。

---

## 3. 核心业务数据字典增量 (Data Models Delta)

### 3.1 枚举扩展

* `OrderType` 新增成员：`LIMIT` (限价单)、`STOP` (止损单)。保留 `MARKET` (市价单)。

### 3.2 Order 对象扩展

* 新增字段 `price` (float | None): 限价/止损单的触发价格。市价单 (MARKET) 该字段为 `None`，默认为 `None`。

* 其余字段沿用 V1.0 (`order_id`, `symbol`, `direction`, `order_type`, `volume`, `status`)。

### 3.3 新增成交记录对象 (Trade)

每一笔成交生成一条 `Trade` 记录，使用 `@dataclass` 定义：

* `order_id` (str): 对应订单号。

* `symbol` (str): 交易标的。

* `direction` (OrderDirection): 买卖方向。

* `datetime` (datetime): 成交时间戳（撮合所在 K 线时间）。

* `price` (float): 真实成交价（已含滑点）。

* `volume` (float): 成交数量。

* `fee` (float): 本笔手续费。

* `realized_pnl` (float): 已实现盈亏。买入开仓记为 `0.0`；卖出平仓按均价法计算（见 4.4 节）。

---

## 4. 模块接口与核心逻辑

### 4.1 订单类型扩展撮合模型 (LIMIT / STOP)

订单在第 T 根 K 线提交后进入队列，**在第 T+1 根（及之后）K 线内**依据该 bar 的 OHLC 判断是否触发。触发后在基准成交价上套用 V1.0 第 4 节的滑点与手续费公式。

**触发与基准成交价规则：**

| 订单类型 | 方向 | 触发条件 | 基准成交价 |
|----------|------|----------|------------|
| LIMIT | BUY | `bar.low <= price` | `min(bar.open, price)` |
| LIMIT | SELL | `bar.high >= price` | `max(bar.open, price)` |
| STOP | BUY | `bar.high >= price` | `max(bar.open, price)` |
| STOP | SELL | `bar.low <= price` | `min(bar.open, price)` |
| MARKET | BUY / SELL | 总是触发 | `bar.open` |

**滑点与手续费（沿用 V1.0 4.2）：** 设基准价 $P_{base}$、滑点 $S$、手续费率 $C$、数量 $V$。

* 买单真实成交价 $P_{fill} = P_{base} \times (1 + S)$

* 卖单真实成交价 $P_{fill} = P_{base} \times (1 - S)$

* 手续费 $Fee = P_{fill} \times V \times C$

**订单有效期 (GTC):** 未触发的限价/止损单**长期有效**，保留在 `pending_orders` 中，后续每根 K 线继续尝试撮合，直到成交或被显式撤单。

**同一 bar 多笔触发的处理顺序:** 按订单**提交顺序 (FIFO)** 依次撮合，先提交者先成交、先占用资金/持仓。

### 4.2 Strategy 接口扩展

策略基类新增/调整下单包装方法（内部仍通过构造 `Order` 提交给 Broker，遵守依赖倒置）：

* `buy(symbol, volume, price=None)`: `price` 为 `None` 时发市价买单；否则发**限价**买单。

* `sell(symbol, volume, price=None)`: `price` 为 `None` 时发市价卖单；否则发**限价**卖单。

* `buy_stop(symbol, volume, price)`: 发**止损**买单（突破触发）。

* `sell_stop(symbol, volume, price)`: 发**止损**卖单（跌破触发）。

### 4.3 Broker 接口扩展

* `submit_order(order)`: 前置风控适配新订单类型。

  * 买入风控参考价：限价/止损单使用 `order.price`，市价单使用最近收盘价；若 `参考价 * volume > cash` 则置 `REJECTED`。

  * 卖出风控沿用 V1.0：持仓 `volume < 订单 volume` 则置 `REJECTED`。

* `match_orders(bar)`: 按 4.1 节模型撮合，支持 GTC 与 FIFO。

* 新增属性 `trades` (List[Trade]): 全部成交记录。

* `get_net_value()`: 沿用 V1.0。

### 4.4 已实现盈亏计算（均价法）

* 买入开仓：`realized_pnl = 0.0`，并按加权平均更新持仓均价（沿用 V1.0）。

* 卖出平仓：`realized_pnl = (P_fill - average_price) * volume - Fee`，其中 `average_price` 为卖出前的持仓均价。卖出不改变剩余持仓均价。

* 一笔「平仓交易」即一条方向为 SELL 的 `Trade`；其 `realized_pnl > 0` 记为盈利交易，否则记为亏损交易。

### 4.5 绩效分析模块 (新增 `core/analytics.py`)

输入：净值曲线 `List[Tuple[datetime, float]]` 与成交记录 `List[Trade]`。输出以下 8 项指标：

| 指标 | 计算方式 |
|------|----------|
| 总收益率 | `equity[-1] / equity[0] - 1` |
| 年化收益率 | `(equity[-1] / equity[0]) ** (periods_per_year / n) - 1`，`n` 为净值点数 - 1 |
| 最大回撤 (MDD) | 净值相对历史峰值的最大跌幅 `min_t(equity_t / running_max_t - 1)` |
| 夏普比率 | `mean(r) / std(r) * sqrt(periods_per_year)`，`r` 为逐期收益率，无风险利率默认 0 |
| 波动率 | `std(r) * sqrt(periods_per_year)` |
| 胜率 | 盈利平仓笔数 / 总平仓笔数 |
| 盈亏比 (Profit Factor) | `总盈利 / |总亏损|`（基于平仓 `realized_pnl`） |
| 交易次数 | 成交记录笔数（或平仓笔数，实现时区分开仓/平仓口径） |

* `periods_per_year` 为**可配置参数，默认 365**（加密品种全年无休市）。

* 无风险利率默认为 0，可配置。

### 4.6 可视化报告模块 (新增 `core/report.py`)

* 接口示例：`generate_report(equity_curve, trades, metrics, output_path)`。

* 输出**单文件 HTML 报告**，包含：

  1. 净值曲线图（matplotlib 渲染后内嵌）。

  2. 回撤曲线图。

  3. 绩效指标汇总表（4.5 节 8 项）。

  4. 成交明细表（基于 `Trade` 列表）。

---

## 5. 验收标准 (Acceptance Criteria)

V2.0 代码完成后，必须通过以下测试：

1. **限价/止损撮合:** 为 LIMIT-BUY、LIMIT-SELL、STOP-BUY、STOP-SELL 四种场景各构造特定 OHLC 数据，断言触发与否、基准成交价及含滑点后的真实成交价精确正确。

2. **GTC 与 FIFO:** 构造连续多根 bar，验证未触发订单跨 bar 保留；同 bar 多笔触发按提交顺序成交。

3. **绩效指标:** 给定一段可控净值序列，断言 8 项指标计算出精确预期值。

4. **盈亏统计:** 构造若干盈利/亏损平仓，断言 `realized_pnl`、胜率、盈亏比正确。

5. **报告生成:** `generate_report` 能生成包含全部图表与表格的 HTML 文件。

6. **回归:** V1.0 既有全部单元测试不回归，新旧测试全部通过。

---

## 6. 依赖与风险 (Dependencies & Risks)

| 项 | 说明 |
|----|------|
| matplotlib | 报告绘图新增依赖，需加入 `requirements.txt` |
| 撮合复杂度 | OHLC 盘中触发比 V1.0 开盘价撮合复杂，需充分测试跳空、同 bar 多笔触发等边界 |
| realized_pnl 口径 | 采用均价法（非 FIFO 逐笔配对），口径已与需求方确认 |
| 单标的假设 | V2.0 仍假设单标的；多标的组合留待 V3.0 |
