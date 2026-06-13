"""回测引擎模块 (BacktestEngine)。

依据 `docs/PRD_v1.md` 第 3.4 节，将 ``DataFeed``、``Broker``、``Strategy`` 三大
模块组装为完整的回测闭环，驱动整个事件循环 (event loop)。

主循环时序 (严格保证无未来函数):
    对 DataFeed 吐出的每一根 K 线 ``bar``，依次执行:
        1. ``broker.match_orders(bar)``: 以本根 bar 的开盘价撮合上一根 bar 遗留
           的挂单 (实现 T+1 开盘价成交)。
        2. ``strategy.on_bar(bar)``: 策略读取本根行情计算信号并下单，新订单进入
           队列，等待下一根 bar 撮合。
        3. 记录本根 bar 收盘后的账户净值，形成净值曲线 (equity curve)。

    "先撮合、后回调" 的顺序确保策略在 T 时刻发出的订单只能在 T+1 成交，
    策略在任何时刻都无法看到未来数据。
"""

from datetime import datetime

from core.broker import Broker
from core.data import BaseDataFeed
from core.strategy import BaseStrategy


class BacktestEngine:
    """回测主引擎。

    负责组装并驱动数据源、撮合引擎与策略，运行完整的回测事件循环，并产出
    逐根 K 线的账户净值曲线。

    Attributes:
        data_feed (BaseDataFeed): 行情数据源。
        broker (Broker): 撮合与账户模块。
        strategy (BaseStrategy): 用户策略实例。
        equity_curve (list[tuple[datetime, float]]): 逐根 K 线记录的
            (时间戳, 账户净值) 序列。
    """

    def __init__(
        self,
        data_feed: BaseDataFeed,
        broker: Broker,
        strategy: BaseStrategy,
    ) -> None:
        """组装回测所需的三大模块。

        Args:
            data_feed: 提供按时间顺序回放的行情数据源。
            broker: 负责风控、撮合与结算的撮合引擎。
            strategy: 待回测的策略实例 (应已绑定同一个 broker)。
        """
        self.data_feed: BaseDataFeed = data_feed
        self.broker: Broker = broker
        self.strategy: BaseStrategy = strategy
        self.equity_curve: list[tuple[datetime, float]] = []

    def run(self) -> list[tuple[datetime, float]]:
        """运行回测主循环。

        先调用一次 ``strategy.on_init`` 完成策略初始化，随后遍历数据源的每一根
        K 线，按 "先撮合、后回调、再记录净值" 的顺序推进时间。

        Returns:
            list[tuple[datetime, float]]: 净值曲线，每个元素为 (K 线时间戳,
                该 K 线收盘后的账户总净值)。
        """
        self.equity_curve = []
        self.strategy.on_init()

        for bar in self.data_feed.get_next_bar():
            # 1. 以当前 bar 开盘价撮合上一根 bar 遗留的挂单 (T+1 成交)。
            self.broker.match_orders(bar)
            # 2. 策略读取当前行情并可能下单 (新单等待下一根 bar 撮合)。
            self.strategy.on_bar(bar)
            # 3. 记录当前 bar 收盘后的账户净值。
            self.equity_curve.append((bar.datetime, self.broker.get_net_value()))

        return self.equity_curve
