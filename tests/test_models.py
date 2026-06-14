"""core.models 单元测试。"""

from datetime import datetime

from core.models import (
    BarData,
    Order,
    OrderDirection,
    OrderStatus,
    OrderType,
    Position,
)


class TestEnums:
    """枚举类型与 PRD 定义一致性。"""

    def test_order_direction_values(self) -> None:
        """OrderDirection 的取值应为 BUY / SELL，锁定 PRD 2.1 的方向定义。"""
        assert OrderDirection.BUY.value == "BUY"
        assert OrderDirection.SELL.value == "SELL"

    def test_order_type_values(self) -> None:
        """OrderType 仅包含 MARKET，验证 V1.0 只支持市价单。"""
        assert OrderType.MARKET.value == "MARKET"

    def test_order_status_values(self) -> None:
        """OrderStatus 状态机取值应为 PENDING / FILLED / REJECTED。"""
        assert OrderStatus.PENDING.value == "PENDING"
        assert OrderStatus.FILLED.value == "FILLED"
        assert OrderStatus.REJECTED.value == "REJECTED"


class TestBarData:
    """K 线数据结构。"""

    def test_create_bar_data(self) -> None:
        """BarData 能正常创建，且 7 个字段(含 OHLCV)可正确读取。"""
        dt = datetime(2025, 1, 1)
        bar = BarData(
            symbol="BTCUSDT",
            datetime=dt,
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            volume=1000.0,
        )

        assert bar.symbol == "BTCUSDT"
        assert bar.datetime == dt
        assert bar.open == 100.0
        assert bar.high == 105.0
        assert bar.low == 99.0
        assert bar.close == 104.0
        assert bar.volume == 1000.0


class TestOrder:
    """订单对象。"""

    def test_default_status_is_pending(self) -> None:
        """不显式传 status 时，Order 默认状态应为 PENDING(PRD 2.3 默认值约定)。"""
        order = Order(
            order_id="test-uuid-001",
            symbol="BTCUSDT",
            direction=OrderDirection.BUY,
            order_type=OrderType.MARKET,
            volume=10.0,
        )

        assert order.status == OrderStatus.PENDING

    def test_explicit_status(self) -> None:
        """显式传入方向与状态时，Order 应原样保存，不被默认值覆盖。"""
        order = Order(
            order_id="test-uuid-002",
            symbol="BTCUSDT",
            direction=OrderDirection.SELL,
            order_type=OrderType.MARKET,
            volume=5.0,
            status=OrderStatus.FILLED,
        )

        assert order.direction == OrderDirection.SELL
        assert order.status == OrderStatus.FILLED


class TestPosition:
    """持仓对象。"""

    def test_create_position(self) -> None:
        """Position 能正常创建，symbol / volume / average_price 可正确读取。"""
        position = Position(
            symbol="BTCUSDT",
            volume=10.0,
            average_price=100.1,
        )

        assert position.symbol == "BTCUSDT"
        assert position.volume == 10.0
        assert position.average_price == 100.1
