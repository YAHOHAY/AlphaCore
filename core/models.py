"""核心业务数据模型 (Data Models)。

本模块依据 `docs/PRD_v1.md` 第 2 节『核心业务数据字典』定义系统内部流转的
全部数据结构，是整个 AlphaCore 框架的唯一事实来源 (Single Source of Truth)。

包含两部分:
    1. 枚举类型 (Enums): 描述订单方向、类型与状态机。
    2. 数据类 (Dataclasses): K 线、订单、持仓三大核心实体，均使用标准库
       `@dataclass` 实现，并带有严格的类型注解。

Typical usage example:

    bar = BarData(
        symbol="BTCUSDT",
        datetime=datetime(2025, 1, 1),
        open=100.0,
        high=105.0,
        low=99.0,
        close=104.0,
        volume=1000.0,
    )
    order = Order(
        order_id=str(uuid.uuid4()),
        symbol="BTCUSDT",
        direction=OrderDirection.BUY,
        order_type=OrderType.MARKET,
        volume=10.0,
    )
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderDirection(Enum):
    """订单买卖方向枚举。

    Attributes:
        BUY: 买入方向。
        SELL: 卖出方向。
    """

    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """订单类型枚举。

    V1.0 版本仅支持市价单 (MARKET)，限价单、止损单等不在范围内。

    Attributes:
        MARKET: 市价单，以对手价/开盘价立即撮合。
    """

    MARKET = "MARKET"


class OrderStatus(Enum):
    """订单状态机枚举。

    描述一笔订单从创建到终态的生命周期流转:
    ``PENDING`` -> ``FILLED`` (成功撮合) 或 ``PENDING`` -> ``REJECTED`` (风控拦截)。

    Attributes:
        PENDING: 待处理，订单已提交进入队列，等待下一根 K 线撮合。
        FILLED: 完全成交。
        REJECTED: 拒单，未通过前置风控（资金不足或无仓位做空）。
    """

    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


@dataclass
class BarData:
    """K 线数据结构 (OHLCV)。

    表示某一交易标的在单个时间周期内的行情快照，是 DataFeed 模块向上层
    推送的最小数据单元。

    Attributes:
        symbol (str): 交易标的代码 (如 "BTCUSDT")。
        datetime (datetime): K 线时间戳。
        open (float): 开盘价。
        high (float): 最高价。
        low (float): 最低价。
        close (float): 收盘价。
        volume (float): 成交量。
    """

    symbol: str
    datetime: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class Order:
    """订单对象。

    由 Strategy 层创建并发送给 Broker 进行撮合的指令载体。遵循依赖倒置原则，
    策略不能直接修改资金与持仓，只能通过提交 Order 与 Broker 通信。

    Attributes:
        order_id (str): 全局唯一订单号 (UUID)。
        symbol (str): 交易标的。
        direction (OrderDirection): 买卖方向。
        order_type (OrderType): 订单类型。
        volume (float): 委托数量。
        status (OrderStatus): 订单当前状态，默认为 ``OrderStatus.PENDING``。
    """

    order_id: str
    symbol: str
    direction: OrderDirection
    order_type: OrderType
    volume: float
    status: OrderStatus = OrderStatus.PENDING


@dataclass
class Position:
    """持仓对象。

    记录某一交易标的当前的净持仓与加权平均成本，由 Broker 在撮合成交后维护。

    Attributes:
        symbol (str): 交易标的。
        volume (float): 当前持有数量。
        average_price (float): 持仓均价（加权平均成本）。
    """

    symbol: str
    volume: float
    average_price: float


@dataclass
class Trade:
    """成交记录 (V2.0)。

    依据 `docs/PRD_v2.md` 第 3.3 节定义，记录每一笔实际成交的明细，由 Broker 在
    撮合成交时生成。成交记录是绩效分析 (胜率、盈亏比) 与交易复盘的数据基础。

    Attributes:
        order_id (str): 对应订单号。
        symbol (str): 交易标的。
        direction (OrderDirection): 买卖方向。
        datetime (datetime): 成交时间戳 (撮合所在 K 线时间)。
        price (float): 真实成交价 (已含滑点)。
        volume (float): 成交数量。
        fee (float): 本笔手续费。
        realized_pnl (float): 已实现盈亏。买入开仓记为 ``0.0``；卖出平仓按均价法
            计算 ``(成交价 - 持仓均价) * 数量 - 手续费``。默认为 ``0.0``。
    """

    order_id: str
    symbol: str
    direction: OrderDirection
    datetime: datetime
    price: float
    volume: float
    fee: float
    realized_pnl: float = 0.0
