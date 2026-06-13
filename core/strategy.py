"""策略基类模块 (Strategy)。

依据 `docs/PRD_v1.md` 第 3.2 节提供标准化的策略编写模板。

设计原则 (依赖倒置):
    策略层不允许直接读取数据层 (DataFeed)，也不允许直接修改资金 (cash) 与
    持仓 (positions)。所有交易意图必须封装为 ``Order`` 并通过 ``Broker`` 发送，
    由 Broker 统一进行风控、撮合与结算。``buy`` / ``sell`` 即为对这一通信过程
    的包装。
"""

import uuid
from abc import ABC, abstractmethod

from core.broker import Broker
from core.models import BarData, Order, OrderDirection, OrderType


class BaseStrategy(ABC):
    """策略抽象基类。

    提供策略生命周期回调 (``on_init`` / ``on_bar``) 与下单包装方法
    (``buy`` / ``sell``)。用户策略应继承本类并实现 ``on_bar``，在其中根据行情
    计算信号并调用 ``buy`` / ``sell`` 下单。

    Attributes:
        broker (Broker): 绑定的撮合引擎，所有订单经由它提交。
    """

    def __init__(self, broker: Broker) -> None:
        """绑定底层撮合引擎。

        Args:
            broker: 负责风控、撮合与结算的 ``Broker`` 实例。
        """
        self.broker: Broker = broker

    def on_init(self) -> None:
        """策略启动前的初始化钩子。

        在回测主循环开始前调用一次，可用于预加载历史数据、计算初始指标
        (如均线窗口) 等。默认实现为空，子类可按需重写。
        """
        return None

    @abstractmethod
    def on_bar(self, bar: BarData) -> None:
        """核心回调函数。

        每当 DataFeed 吐出一根新 K 线时触发。子类在此实现交易逻辑：根据当前
        及历史行情计算信号，并通过 ``buy`` / ``sell`` 下单。

        Args:
            bar: 当前最新的 K 线数据。
        """
        raise NotImplementedError

    def buy(self, symbol: str, volume: float) -> Order:
        """发送一笔市价买入订单。

        内部构造方向为 ``BUY`` 的市价 ``Order`` 并提交给 ``Broker``。

        Args:
            symbol: 交易标的代码。
            volume: 委托买入数量。

        Returns:
            Order: 已提交的订单对象 (其 ``status`` 由 Broker 风控结果决定)。
        """
        order: Order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            direction=OrderDirection.BUY,
            order_type=OrderType.MARKET,
            volume=volume,
        )
        return self.broker.submit_order(order)

    def sell(self, symbol: str, volume: float) -> Order:
        """发送一笔市价卖出订单。

        内部构造方向为 ``SELL`` 的市价 ``Order`` 并提交给 ``Broker``。

        Args:
            symbol: 交易标的代码。
            volume: 委托卖出数量。

        Returns:
            Order: 已提交的订单对象 (其 ``status`` 由 Broker 风控结果决定)。
        """
        order: Order = Order(
            order_id=str(uuid.uuid4()),
            symbol=symbol,
            direction=OrderDirection.SELL,
            order_type=OrderType.MARKET,
            volume=volume,
        )
        return self.broker.submit_order(order)
