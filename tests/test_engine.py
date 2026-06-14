"""core.engine 单元测试。"""

from datetime import datetime
from pathlib import Path

from core.broker import Broker
from core.data import CSVDataFeed
from core.engine import BacktestEngine
from core.models import BarData
from core.strategy import BaseStrategy


class _BuyOnceStrategy(BaseStrategy):
    """在第一根 bar 买入一次，之后不再交易。"""

    def __init__(self, broker: Broker, symbol: str, volume: float) -> None:
        super().__init__(broker)
        self._symbol = symbol
        self._volume = volume
        self._bought = False
        self.init_called = False

    def on_init(self) -> None:
        self.init_called = True

    def on_bar(self, bar: BarData) -> None:
        if not self._bought:
            self.buy(self._symbol, self._volume)
            self._bought = True


class _NoopStrategy(BaseStrategy):
    """不下任何单的空策略。"""

    def on_bar(self, bar: BarData) -> None:
        return None


class TestBacktestEngine:
    """回测主循环。"""

    def test_run_calls_on_init_and_builds_equity_curve(
        self, sample_csv_with_symbol: Path
    ) -> None:
        """run() 应遍历全部 bar 生成等长净值曲线;无交易时净值恒等于初始现金。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        broker = Broker(cash=100_000)
        strategy = _NoopStrategy(broker)
        engine = BacktestEngine(feed, broker, strategy)

        curve = engine.run()

        # sample_csv_with_symbol 含 3 根 bar
        assert len(curve) == 3
        assert all(isinstance(dt, datetime) for dt, _ in curve)
        # 无交易，净值恒等于初始现金
        assert all(value == 100_000 for _, value in curve)

    def test_buy_fills_on_next_bar(self, sample_csv_with_symbol: Path) -> None:
        """首根 bar 下的买单在第二根 bar 以其开盘价(102)成交,现金与持仓相应更新。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        broker = Broker(cash=100_000, slippage=0.0, commission=0.0)
        strategy = _BuyOnceStrategy(broker, symbol="BTCUSDT", volume=10.0)
        engine = BacktestEngine(feed, broker, strategy)

        engine.run()

        # 第 1 根 bar (open=100) 下单 -> 第 2 根 bar (open=102) 成交
        assert strategy.init_called is True
        assert "BTCUSDT" in broker.positions
        assert broker.positions["BTCUSDT"].volume == 10.0
        assert broker.positions["BTCUSDT"].average_price == 102.0
        assert broker.cash == 100_000 - 102.0 * 10.0

    def test_no_lookahead_first_bar_not_filled_same_bar(
        self, sample_csv_with_symbol: Path
    ) -> None:
        """无未来函数验证:第一根 bar 下的单不会在同根 bar 成交,当根净值仍为初始现金。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        broker = Broker(cash=100_000, slippage=0.0, commission=0.0)
        strategy = _BuyOnceStrategy(broker, symbol="BTCUSDT", volume=10.0)
        engine = BacktestEngine(feed, broker, strategy)

        curve = engine.run()

        # 第 1 根 bar 收盘时订单尚未成交，净值仍等于初始现金
        assert curve[0][1] == 100_000

    def test_equity_curve_reflects_position_value(
        self, sample_csv_with_symbol: Path
    ) -> None:
        """净值曲线应逐根反映持仓市值随收盘价(106、109)的变化。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        broker = Broker(cash=100_000, slippage=0.0, commission=0.0)
        strategy = _BuyOnceStrategy(broker, symbol="BTCUSDT", volume=10.0)
        engine = BacktestEngine(feed, broker, strategy)

        curve = engine.run()

        # 第 2 根 bar 成交后: cash = 100000 - 1020 = 98980; 持仓 10 @ close=106 -> 1060
        assert curve[1][1] == 98980 + 10 * 106.0
        # 第 3 根 bar: 持仓 10 @ close=109 -> 1090
        assert curve[2][1] == 98980 + 10 * 109.0

    def test_run_is_idempotent_resets_curve(
        self, sample_csv_with_symbol: Path
    ) -> None:
        """重复调用 run() 应重置净值曲线,两次结果长度一致(不累加历史)。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        broker = Broker(cash=100_000)
        engine = BacktestEngine(feed, broker, _NoopStrategy(broker))

        first = engine.run()
        second = engine.run()

        assert len(first) == len(second) == 3
