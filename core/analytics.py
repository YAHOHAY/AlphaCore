"""绩效分析模块 (Performance Analytics)。

依据 `docs/PRD_v2.md` 第 4.5 节，基于回测产出的净值曲线与成交记录计算策略的
关键绩效指标。本模块为纯函数式实现，不持有状态、不修改任何输入对象，便于独立
测试与复用。

约定:
    * 逐期收益率标准差采用样本标准差 (``ddof=1``)，与金融实务中夏普比率的常见
      口径一致。
    * 最大回撤为非正数 (净值相对历史峰值的跌幅，``<= 0``)。
    * 胜率与盈亏比仅基于平仓交易 (方向为 SELL 的成交记录) 的已实现盈亏统计。
    * 当数据不足以计算某项指标时 (如净值点数不足、无平仓交易、无亏损交易)，
      采用下文文档说明的退化取值，避免抛出除零异常。
"""

from dataclasses import dataclass
from datetime import datetime

import numpy as np

from core.models import OrderDirection, Trade


@dataclass
class PerformanceMetrics:
    """绩效指标汇总 (PRD 4.5)。

    Attributes:
        total_return (float): 总收益率 = 末期净值 / 初期净值 - 1。
        annual_return (float): 年化收益率。
        max_drawdown (float): 最大回撤 (非正数，越小代表回撤越深)。
        sharpe_ratio (float): 年化夏普比率 (无风险利率默认 0)。
        volatility (float): 年化波动率。
        win_rate (float): 胜率 = 盈利平仓笔数 / 总平仓笔数，取值 [0, 1]。
        profit_factor (float): 盈亏比 = 总盈利 / |总亏损|。无亏损且有盈利时为
            ``inf``；无平仓交易时为 ``0.0``。
        trade_count (int): 成交记录总笔数 (含开仓与平仓)。
    """

    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    volatility: float
    win_rate: float
    profit_factor: float
    trade_count: int


def calculate_metrics(
    equity_curve: list[tuple[datetime, float]],
    trades: list[Trade],
    periods_per_year: int = 365,
    risk_free_rate: float = 0.0,
) -> PerformanceMetrics:
    """计算策略绩效指标。

    Args:
        equity_curve: 净值曲线，每个元素为 (时间戳, 账户净值)，按时间升序。
        trades: 成交记录列表 (由 Broker 产出)。
        periods_per_year: 年化基准周期数，日线加密品种默认 365。
        risk_free_rate: 年化无风险利率，默认 0.0。

    Returns:
        PerformanceMetrics: 汇总后的 8 项绩效指标。
    """
    equity: np.ndarray = np.array(
        [value for _, value in equity_curve], dtype=float
    )

    total_return = _total_return(equity)
    annual_return = _annual_return(equity, periods_per_year)
    max_drawdown = _max_drawdown(equity)
    volatility, sharpe_ratio = _volatility_and_sharpe(
        equity, periods_per_year, risk_free_rate
    )
    win_rate, profit_factor = _trade_statistics(trades)

    return PerformanceMetrics(
        total_return=total_return,
        annual_return=annual_return,
        max_drawdown=max_drawdown,
        sharpe_ratio=sharpe_ratio,
        volatility=volatility,
        win_rate=win_rate,
        profit_factor=profit_factor,
        trade_count=len(trades),
    )


def _periodic_returns(equity: np.ndarray) -> np.ndarray:
    """计算逐期简单收益率序列。

    Args:
        equity: 净值序列。

    Returns:
        np.ndarray: 逐期收益率 ``equity[t] / equity[t-1] - 1``；当净值点数不足
            两个时返回空数组。
    """
    if equity.size < 2:
        return np.array([], dtype=float)
    return np.diff(equity) / equity[:-1]


def _total_return(equity: np.ndarray) -> float:
    """总收益率。净值点数不足或初期净值为 0 时返回 0.0。"""
    if equity.size < 2 or equity[0] == 0:
        return 0.0
    return float(equity[-1] / equity[0] - 1)


def _annual_return(equity: np.ndarray, periods_per_year: int) -> float:
    """年化收益率。净值点数不足或初期净值非正时返回 0.0。"""
    n_periods = equity.size - 1
    if n_periods < 1 or equity[0] <= 0 or equity[-1] <= 0:
        return 0.0
    growth = equity[-1] / equity[0]
    return float(growth ** (periods_per_year / n_periods) - 1)


def _max_drawdown(equity: np.ndarray) -> float:
    """最大回撤 (非正数)。净值为空时返回 0.0。"""
    if equity.size == 0:
        return 0.0
    running_max = np.maximum.accumulate(equity)
    drawdowns = equity / running_max - 1
    return float(drawdowns.min())


def _volatility_and_sharpe(
    equity: np.ndarray,
    periods_per_year: int,
    risk_free_rate: float,
) -> tuple[float, float]:
    """年化波动率与年化夏普比率。

    收益率不足两个 (无法估计样本标准差) 或标准差为 0 时，波动率与夏普均返回 0.0。

    Args:
        equity: 净值序列。
        periods_per_year: 年化基准周期数。
        risk_free_rate: 年化无风险利率。

    Returns:
        tuple[float, float]: (年化波动率, 年化夏普比率)。
    """
    returns = _periodic_returns(equity)
    if returns.size < 2:
        return 0.0, 0.0

    std = float(np.std(returns, ddof=1))
    annual_volatility = std * np.sqrt(periods_per_year)

    if std == 0:
        return annual_volatility, 0.0

    rf_per_period = risk_free_rate / periods_per_year
    excess_mean = float(np.mean(returns)) - rf_per_period
    sharpe = excess_mean / std * np.sqrt(periods_per_year)
    return annual_volatility, float(sharpe)


def _trade_statistics(trades: list[Trade]) -> tuple[float, float]:
    """基于平仓交易计算胜率与盈亏比。

    平仓交易定义为方向为 ``SELL`` 的成交记录 (V2.0 仅支持现货做多)。

    Args:
        trades: 成交记录列表。

    Returns:
        tuple[float, float]: (胜率, 盈亏比)。无平仓交易时返回 ``(0.0, 0.0)``；
            有盈利但无亏损时盈亏比为 ``inf``。
    """
    closing_trades = [
        trade for trade in trades if trade.direction == OrderDirection.SELL
    ]
    if not closing_trades:
        return 0.0, 0.0

    wins = [t for t in closing_trades if t.realized_pnl > 0]
    win_rate = len(wins) / len(closing_trades)

    gross_profit = sum(t.realized_pnl for t in closing_trades if t.realized_pnl > 0)
    gross_loss = sum(
        -t.realized_pnl for t in closing_trades if t.realized_pnl < 0
    )

    if gross_loss == 0:
        profit_factor = float("inf") if gross_profit > 0 else 0.0
    else:
        profit_factor = gross_profit / gross_loss

    return win_rate, profit_factor
