"""core.analytics 单元测试。"""

from datetime import datetime

import numpy as np
import pytest

from core.analytics import PerformanceMetrics, calculate_metrics
from core.models import OrderDirection, Trade


def make_trade(
    direction: OrderDirection,
    realized_pnl: float = 0.0,
) -> Trade:
    """构造一笔成交记录（仅关心方向与已实现盈亏）。"""
    return Trade(
        order_id="t",
        symbol="BTCUSDT",
        direction=direction,
        datetime=datetime(2025, 1, 1),
        price=100.0,
        volume=1.0,
        fee=0.0,
        realized_pnl=realized_pnl,
    )


def make_curve(values: list[float]) -> list[tuple[datetime, float]]:
    """把净值序列包装成 (时间戳, 净值) 列表。"""
    return [(datetime(2025, 1, day + 1), v) for day, v in enumerate(values)]


class TestEquityMetrics:
    """基于净值曲线的指标。"""

    def test_total_return(self) -> None:
        """总收益率 = 末期/初期 - 1。"""
        metrics = calculate_metrics(make_curve([100, 110, 99]), [])
        assert metrics.total_return == pytest.approx(99 / 100 - 1)

    def test_annual_return_uses_periods_per_year(self) -> None:
        """年化收益率按 (末/初)^(periods_per_year/区间数) - 1 计算。"""
        metrics = calculate_metrics(
            make_curve([100, 110, 99]), [], periods_per_year=365
        )
        expected = (99 / 100) ** (365 / 2) - 1
        assert metrics.annual_return == pytest.approx(expected)

    def test_max_drawdown_is_non_positive(self) -> None:
        """最大回撤为净值相对历史峰值的最大跌幅（非正数）。"""
        metrics = calculate_metrics(make_curve([100, 110, 99]), [])
        # 峰值 110 -> 99，回撤 = 99/110 - 1
        assert metrics.max_drawdown == pytest.approx(99 / 110 - 1)
        assert metrics.max_drawdown <= 0

    def test_volatility_uses_sample_std(self) -> None:
        """年化波动率 = 样本标准差(ddof=1) * sqrt(periods_per_year)。"""
        metrics = calculate_metrics(
            make_curve([100, 110, 99]), [], periods_per_year=365
        )
        returns = np.array([0.1, 99 / 110 - 1])
        expected = float(np.std(returns, ddof=1) * np.sqrt(365))
        assert metrics.volatility == pytest.approx(expected)

    def test_sharpe_zero_when_mean_excess_zero(self) -> None:
        """收益率均值为 0（无风险利率 0）时夏普为 0。"""
        # returns = [0.1, -0.1]，均值为 0
        metrics = calculate_metrics(make_curve([100, 110, 99]), [])
        assert metrics.sharpe_ratio == pytest.approx(0.0)

    def test_sharpe_positive_for_steady_growth(self) -> None:
        """稳定上涨序列应得到正夏普。"""
        metrics = calculate_metrics(make_curve([100, 101, 102, 103]), [])
        assert metrics.sharpe_ratio > 0


class TestTradeStatistics:
    """基于成交记录的胜率与盈亏比。"""

    def test_win_rate_and_profit_factor(self) -> None:
        """胜率=盈利平仓/总平仓；盈亏比=总盈利/|总亏损|。"""
        trades = [
            make_trade(OrderDirection.BUY, 0.0),
            make_trade(OrderDirection.SELL, 50.0),
            make_trade(OrderDirection.SELL, -20.0),
        ]
        metrics = calculate_metrics(make_curve([100, 130]), trades)

        assert metrics.win_rate == pytest.approx(0.5)
        assert metrics.profit_factor == pytest.approx(50 / 20)
        assert metrics.trade_count == 3

    def test_profit_factor_inf_when_no_loss(self) -> None:
        """有盈利且无亏损时盈亏比为 inf。"""
        trades = [
            make_trade(OrderDirection.SELL, 30.0),
            make_trade(OrderDirection.SELL, 10.0),
        ]
        metrics = calculate_metrics(make_curve([100, 140]), trades)

        assert metrics.win_rate == pytest.approx(1.0)
        assert metrics.profit_factor == float("inf")

    def test_no_closing_trades(self) -> None:
        """无平仓交易（只有买入）时胜率与盈亏比均为 0。"""
        trades = [make_trade(OrderDirection.BUY, 0.0)]
        metrics = calculate_metrics(make_curve([100, 100]), trades)

        assert metrics.win_rate == 0.0
        assert metrics.profit_factor == 0.0
        assert metrics.trade_count == 1


class TestEdgeCases:
    """边界场景。"""

    def test_empty_equity_curve(self) -> None:
        """空净值曲线时所有净值类指标为 0，不抛异常。"""
        metrics = calculate_metrics([], [])

        assert isinstance(metrics, PerformanceMetrics)
        assert metrics.total_return == 0.0
        assert metrics.annual_return == 0.0
        assert metrics.max_drawdown == 0.0
        assert metrics.volatility == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_single_point_equity_curve(self) -> None:
        """仅一个净值点时无法计算收益率，相关指标为 0。"""
        metrics = calculate_metrics(make_curve([100]), [])

        assert metrics.total_return == 0.0
        assert metrics.volatility == 0.0
        assert metrics.sharpe_ratio == 0.0

    def test_flat_equity_has_zero_volatility(self) -> None:
        """净值无波动时波动率与夏普为 0（避免除零）。"""
        metrics = calculate_metrics(make_curve([100, 100, 100]), [])

        assert metrics.volatility == 0.0
        assert metrics.sharpe_ratio == 0.0
        assert metrics.max_drawdown == 0.0
