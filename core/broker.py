"""撮合与账户模块 (Broker)。

依据 `docs/PRD_v1.md` 第 3.3 节与第 4 节实现订单撮合、资金结算、持仓管理与
前置风控。本模块是整个回测系统的“交易所 + 账户”，所有资金与持仓的变动都
必须经由此处，策略层不得绕过 Broker 直接修改资金或持仓 (依赖倒置)。

核心数学模型 (PRD 第 4 节):
    设基准成交价为开盘价 ``P_open``，滑点比例 ``S``，手续费率 ``C``，成交量 ``V``。

    * 真实成交价 (P_fill):
        - 买单: ``P_fill = P_open * (1 + S)``
        - 卖单: ``P_fill = P_open * (1 - S)``
    * 单笔手续费: ``Fee = P_fill * V * C``
    * 买入扣款: ``Cash = Cash - P_fill * V - Fee``
    * 卖出收款: ``Cash = Cash + P_fill * V - Fee``

无未来函数保证 (No Lookahead Bias):
    策略在第 T 根 K 线发出的订单进入 ``pending_orders`` 队列，必须在第 T+1 根
    K 线的开盘价被撮合。``match_orders`` 在新 bar 到来时，先以该 bar 的 ``open``
    撮合上一根 bar 遗留的挂单，从而保证 T 时刻只能看到 <= T 的数据。
"""

from core.models import (
    BarData,
    Order,
    OrderDirection,
    OrderStatus,
    Position,
)


class Broker:
    """撮合与账户模块。

    负责接收并撮合订单、管理可用现金与持仓、执行前置风控，并提供净值计算。

    Attributes:
        cash (float): 当前可用现金。
        slippage (float): 滑点比例 (如 0.001 表示 0.1%)。
        commission (float): 手续费率 (如 0.0005 表示 0.05%)。
        positions (dict[str, Position]): 当前持仓字典，键为标的代码。
        pending_orders (list[Order]): 等待撮合的订单队列。
    """

    def __init__(
        self,
        cash: float,
        slippage: float = 0.0,
        commission: float = 0.0,
    ) -> None:
        """初始化账户与撮合参数。

        Args:
            cash: 初始可用现金。
            slippage: 滑点比例，默认 0.0 (无滑点)。
            commission: 手续费率，默认 0.0 (无手续费)。
        """
        self.cash: float = cash
        self.slippage: float = slippage
        self.commission: float = commission
        self.positions: dict[str, Position] = {}
        self.pending_orders: list[Order] = []

        # 各标的最近一根已知 K 线的收盘价，用于前置风控与净值估算。
        # 仅记录 <= 当前时刻的收盘价，不引入未来信息。
        self._last_close: dict[str, float] = {}

    def submit_order(self, order: Order) -> Order:
        """接收策略发出的订单并执行前置风控。

        风控规则 (PRD 第 4.3 节):
            * 资金不足限制: 买单若 ``最近收盘价 * volume > cash``，置为 ``REJECTED``。
            * 无仓位防做空限制: 卖单若当前持仓 ``volume < 订单 volume``，置为 ``REJECTED``。

        通过风控的订单状态保持 ``PENDING`` 并进入 ``pending_orders`` 队列，
        等待下一根 K 线撮合；被拒绝的订单不会进入队列。

        Args:
            order: 待提交的订单对象。

        Returns:
            Order: 同一订单对象，其 ``status`` 已被更新为 ``PENDING`` 或 ``REJECTED``。
        """
        if order.direction == OrderDirection.BUY:
            reference_price: float | None = self._last_close.get(order.symbol)
            if reference_price is None or reference_price * order.volume > self.cash:
                order.status = OrderStatus.REJECTED
                return order
        else:  # OrderDirection.SELL
            position: Position | None = self.positions.get(order.symbol)
            if position is None or position.volume < order.volume:
                order.status = OrderStatus.REJECTED
                return order

        order.status = OrderStatus.PENDING
        self.pending_orders.append(order)
        return order

    def match_orders(self, bar: BarData) -> None:
        """在新 K 线到来时撮合挂单。

        以 ``bar.open`` 作为基准成交价撮合 ``pending_orders`` 中与该 bar 标的
        相同的订单 (实现 T+1 开盘价成交)。同时刷新该标的的最近收盘价，供后续
        风控与净值计算使用。

        Args:
            bar: 当前 (T+1) K 线数据。
        """
        self._last_close[bar.symbol] = bar.close

        remaining: list[Order] = []
        for order in self.pending_orders:
            # 不同标的的挂单无法用当前 bar 撮合，继续留在队列中等待对应行情。
            if order.symbol != bar.symbol:
                remaining.append(order)
                continue
            self._execute_order(order, bar.open)
        self.pending_orders = remaining

    def get_net_value(self) -> float:
        """计算账户总净值。

        总净值 = 可用现金 + 所有持仓的市值。持仓市值以各标的最近一根已知 K 线
        的收盘价估算；若某标的尚无收盘价记录，则退化为以持仓均价估值。

        Returns:
            float: 账户当前总净值。
        """
        market_value: float = 0.0
        for symbol, position in self.positions.items():
            price: float = self._last_close.get(symbol, position.average_price)
            market_value += position.volume * price
        return self.cash + market_value

    def _execute_order(self, order: Order, open_price: float) -> None:
        """以给定开盘价执行单笔订单的撮合与结算。

        Args:
            order: 待撮合的订单 (状态应为 ``PENDING``)。
            open_price: 撮合基准价 (T+1 开盘价)。
        """
        if order.direction == OrderDirection.BUY:
            fill_price: float = open_price * (1 + self.slippage)
            fee: float = fill_price * order.volume * self.commission
            self.cash -= fill_price * order.volume + fee
            self._add_position(order.symbol, order.volume, fill_price)
        else:  # OrderDirection.SELL
            fill_price = open_price * (1 - self.slippage)
            fee = fill_price * order.volume * self.commission
            self.cash += fill_price * order.volume - fee
            self._reduce_position(order.symbol, order.volume)

        order.status = OrderStatus.FILLED

    def _add_position(self, symbol: str, volume: float, fill_price: float) -> None:
        """买入成交后增加持仓并更新加权平均成本。

        新均价采用成交价的加权平均 (不含手续费):
            ``new_avg = (old_vol * old_avg + fill_price * volume) / (old_vol + volume)``

        Args:
            symbol: 交易标的。
            volume: 本次成交数量。
            fill_price: 本次真实成交价。
        """
        position: Position | None = self.positions.get(symbol)
        if position is None:
            self.positions[symbol] = Position(
                symbol=symbol,
                volume=volume,
                average_price=fill_price,
            )
            return

        total_volume: float = position.volume + volume
        position.average_price = (
            position.volume * position.average_price + fill_price * volume
        ) / total_volume
        position.volume = total_volume

    def _reduce_position(self, symbol: str, volume: float) -> None:
        """卖出成交后减少持仓。

        持仓均价在卖出时保持不变 (仅减少数量)；当持仓数量减至 0 时移除该持仓。

        Args:
            symbol: 交易标的。
            volume: 本次卖出数量。
        """
        position: Position = self.positions[symbol]
        position.volume -= volume
        if position.volume <= 0:
            del self.positions[symbol]
