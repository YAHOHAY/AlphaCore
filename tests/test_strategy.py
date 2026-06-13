"""core.strategy 单元测试。"""

from datetime import datetime

import pytest

from core.broker import Broker
from core.models import BarData, OrderDirection, OrderStatus
from core.strategy import BaseStrategy


class _DummyStrategy(BaseStrategy):
    """用于测试的最小策略：每根 bar 买入固定数量。"""

    def __init__(self, broker: Broker) -> None:
        super().__init__(broker)
        self.init_called: bool = False
        self.bars_seen: int = 0

    def on_init(self) -> None:
        self.init_called = True

    def on_bar(self, bar: BarData) -> None:
        self.bars_seen += 1
        self.buy(bar.symbol, volume=1.0)


def make_bar(open_: float = 100.0, close: float = 100.0) -> BarData:
    return BarData(
        symbol="BTCUSDT",
        datetime=datetime(2025, 1, 1),
        open=open_,
        high=max(open_, close),
        low=min(open_, close),
        close=close,
        volume=1000.0,
    )


class TestBaseStrategy:
    """策略基类接口与行为。"""

    def test_cannot_instantiate_abstract_base(self) -> None:
        broker = Broker(cash=100_000)
        with pytest.raises(TypeError):
            BaseStrategy(broker)  # type: ignore[abstract]

    def test_binds_broker(self) -> None:
        broker = Broker(cash=100_000)
        strategy = _DummyStrategy(broker)
        assert strategy.broker is broker

    def test_on_init_hook(self) -> None:
        strategy = _DummyStrategy(Broker(cash=100_000))
        assert strategy.init_called is False
        strategy.on_init()
        assert strategy.init_called is True

    def test_buy_submits_pending_order(self) -> None:
        broker = Broker(cash=100_000)
        broker.match_orders(make_bar())  # 提供参考价
        strategy = _DummyStrategy(broker)

        order = strategy.buy("BTCUSDT", volume=10.0)

        assert order.direction == OrderDirection.BUY
        assert order.status == OrderStatus.PENDING
        assert order in broker.pending_orders

    def test_sell_rejected_without_position(self) -> None:
        broker = Broker(cash=100_000)
        broker.match_orders(make_bar())
        strategy = _DummyStrategy(broker)

        order = strategy.sell("BTCUSDT", volume=10.0)

        assert order.direction == OrderDirection.SELL
        assert order.status == OrderStatus.REJECTED

    def test_orders_have_unique_ids(self) -> None:
        broker = Broker(cash=100_000)
        broker.match_orders(make_bar())
        strategy = _DummyStrategy(broker)

        o1 = strategy.buy("BTCUSDT", volume=1.0)
        o2 = strategy.buy("BTCUSDT", volume=1.0)

        assert o1.order_id != o2.order_id

    def test_strategy_loop_integration(self) -> None:
        """模拟回测主循环：match -> on_bar，验证 T+1 撮合闭环。"""
        broker = Broker(cash=1_000_000, slippage=0.0, commission=0.0)
        strategy = _DummyStrategy(broker)
        strategy.on_init()

        bars = [make_bar(open_=100.0, close=100.0) for _ in range(3)]
        for bar in bars:
            broker.match_orders(bar)
            strategy.on_bar(bar)

        assert strategy.init_called is True
        assert strategy.bars_seen == 3
        # 3 根 bar 各下 1 单；最后一根的订单尚未到 T+1，仍在队列。
        # 前两单已在后续 bar 撮合 -> 持仓 2 单位。
        assert broker.positions["BTCUSDT"].volume == 2.0
        assert len(broker.pending_orders) == 1
