"""core.broker 单元测试。

包含 PRD 第 5 节的验收标准测试 (TestAcceptanceCriteria)。
"""

from datetime import datetime

import pytest

from core.broker import Broker
from core.models import (
    BarData,
    Order,
    OrderDirection,
    OrderStatus,
    OrderType,
)


def make_bar(
    close: float,
    open_: float,
    symbol: str = "BTCUSDT",
    dt: datetime | None = None,
) -> BarData:
    """构造一根简单的 BarData（high/low/volume 取无关紧要的占位值）。"""
    return BarData(
        symbol=symbol,
        datetime=dt or datetime(2025, 1, 1),
        open=open_,
        high=max(open_, close),
        low=min(open_, close),
        close=close,
        volume=1000.0,
    )


def make_order(
    direction: OrderDirection,
    volume: float,
    symbol: str = "BTCUSDT",
) -> Order:
    """构造一笔市价订单。"""
    return Order(
        order_id="test-order",
        symbol=symbol,
        direction=direction,
        order_type=OrderType.MARKET,
        volume=volume,
    )


class TestSubmitOrderRiskControl:
    """前置风控 (PRD 4.3)。"""

    def test_buy_accepted_when_cash_sufficient(self) -> None:
        """资金充足的买单应通过风控:状态置 PENDING 并进入挂单队列。"""
        broker = Broker(cash=100_000)
        broker.match_orders(make_bar(close=100.0, open_=100.0))  # 提供参考价

        order = broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))

        assert order.status == OrderStatus.PENDING
        assert order in broker.pending_orders

    def test_buy_rejected_when_cash_insufficient(self) -> None:
        """资金不足(close*volume > cash)的买单应被拒,且不进入队列。"""
        broker = Broker(cash=500.0)
        broker.match_orders(make_bar(close=100.0, open_=100.0))

        order = broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))

        assert order.status == OrderStatus.REJECTED
        assert order not in broker.pending_orders

    def test_buy_rejected_without_reference_price(self) -> None:
        """尚无任何已知收盘价时(未走过 match_orders),买单无法估算资金,应被拒。"""
        broker = Broker(cash=100_000)

        order = broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))

        assert order.status == OrderStatus.REJECTED

    def test_sell_rejected_without_position(self) -> None:
        """无任何持仓时的卖单应被拒(防做空)。"""
        broker = Broker(cash=100_000)
        broker.match_orders(make_bar(close=100.0, open_=100.0))

        order = broker.submit_order(make_order(OrderDirection.SELL, volume=10.0))

        assert order.status == OrderStatus.REJECTED

    def test_sell_rejected_when_position_insufficient(self) -> None:
        """卖出数量超过当前持仓时应被拒(持仓 5 卖 10 -> REJECTED)。"""
        broker = Broker(cash=100_000)
        broker.match_orders(make_bar(close=100.0, open_=100.0))
        broker.submit_order(make_order(OrderDirection.BUY, volume=5.0))
        broker.match_orders(make_bar(close=100.0, open_=100.0))  # 成交得到 5 单位

        order = broker.submit_order(make_order(OrderDirection.SELL, volume=10.0))

        assert order.status == OrderStatus.REJECTED


class TestMatching:
    """撮合与结算逻辑 (PRD 4.1 / 4.2)。"""

    def test_order_filled_at_next_bar_open(self) -> None:
        """订单在提交后的下一根 bar 以开盘价成交(T+1 撮合,无未来函数)。"""
        broker = Broker(cash=100_000, slippage=0.0, commission=0.0)
        broker.match_orders(make_bar(close=50.0, open_=50.0))
        order = broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))

        assert order.status == OrderStatus.PENDING

        broker.match_orders(make_bar(close=120.0, open_=100.0))

        assert order.status == OrderStatus.FILLED
        assert broker.pending_orders == []
        assert "BTCUSDT" in broker.positions
        assert broker.positions["BTCUSDT"].volume == 10.0

    def test_average_price_weighted_on_multiple_buys(self) -> None:
        """多次买入后持仓均价应为成交价的加权平均(10@100 + 10@200 -> 150)。"""
        broker = Broker(cash=1_000_000, slippage=0.0, commission=0.0)
        broker.match_orders(make_bar(close=100.0, open_=100.0))
        broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))
        broker.match_orders(make_bar(close=200.0, open_=100.0))  # 10 @ 100
        broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))
        broker.match_orders(make_bar(close=200.0, open_=200.0))  # 10 @ 200

        position = broker.positions["BTCUSDT"]
        assert position.volume == 20.0
        assert position.average_price == pytest.approx(150.0)

    def test_sell_reduces_position(self) -> None:
        """卖出部分持仓后,持仓数量应相应减少(持仓 10 卖 4 -> 剩 6)。"""
        broker = Broker(cash=1_000_000, slippage=0.0, commission=0.0)
        broker.match_orders(make_bar(close=100.0, open_=100.0))
        broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))
        broker.match_orders(make_bar(close=100.0, open_=100.0))
        broker.submit_order(make_order(OrderDirection.SELL, volume=4.0))
        broker.match_orders(make_bar(close=100.0, open_=100.0))

        assert broker.positions["BTCUSDT"].volume == 6.0

    def test_position_removed_when_fully_sold(self) -> None:
        """持仓被全部卖出后,该标的应从持仓字典中移除。"""
        broker = Broker(cash=1_000_000, slippage=0.0, commission=0.0)
        broker.match_orders(make_bar(close=100.0, open_=100.0))
        broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))
        broker.match_orders(make_bar(close=100.0, open_=100.0))
        broker.submit_order(make_order(OrderDirection.SELL, volume=10.0))
        broker.match_orders(make_bar(close=100.0, open_=100.0))

        assert "BTCUSDT" not in broker.positions


class TestNetValue:
    """净值计算。"""

    def test_net_value_equals_cash_when_no_position(self) -> None:
        """无持仓时账户净值应等于可用现金。"""
        broker = Broker(cash=100_000)
        assert broker.get_net_value() == 100_000

    def test_net_value_includes_position_market_value(self) -> None:
        """有持仓时净值 = 现金 + 持仓市值(按最近收盘价估算)。"""
        broker = Broker(cash=1_000_000, slippage=0.0, commission=0.0)
        broker.match_orders(make_bar(close=100.0, open_=100.0))
        broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))
        broker.match_orders(make_bar(close=120.0, open_=100.0))  # 成交 10 @ 100

        # cash = 1_000_000 - 1000 = 999_000; 市值 = 10 * 120 = 1200
        assert broker.get_net_value() == pytest.approx(999_000 + 1200)


class TestAcceptanceCriteria:
    """PRD 第 5 节验收标准。

    初始化资金 100,000，滑点 0.1%，手续费 0.05%。
    T 日生成市价买入单 (10 单位)，T+1 日以 100 的开盘价撮合。
    """

    def test_prd_section5_acceptance(self) -> None:
        """端到端复现 PRD 验收用例:成交价 100.1 / 手续费 0.5005 / 现金 98998.4995。"""
        broker = Broker(cash=100_000, slippage=0.001, commission=0.0005)

        # T 日：提供参考价并提交买单
        broker.match_orders(make_bar(close=99.0, open_=99.0, dt=datetime(2025, 1, 1)))
        order = broker.submit_order(make_order(OrderDirection.BUY, volume=10.0))
        assert order.status == OrderStatus.PENDING

        # T+1 日：以开盘价 100 撮合
        broker.match_orders(make_bar(close=101.0, open_=100.0, dt=datetime(2025, 1, 2)))

        position = broker.positions["BTCUSDT"]

        # 真实成交价 = 100 * (1 + 0.001) = 100.1
        assert position.average_price == pytest.approx(100.1)
        # 手续费 = 100.1 * 10 * 0.0005 = 0.5005
        # 剩余现金 = 100000 - 100.1*10 - 0.5005 = 98998.4995
        assert broker.cash == pytest.approx(98998.4995)
        assert order.status == OrderStatus.FILLED
        assert position.volume == 10.0
