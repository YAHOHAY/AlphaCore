"""pytest 共享 fixtures。"""

from pathlib import Path

import pytest


@pytest.fixture
def sample_csv_with_symbol(tmp_path: Path) -> Path:
    """包含 symbol 列的标准 OHLCV CSV。"""
    csv_path = tmp_path / "btcusdt.csv"
    csv_path.write_text(
        "datetime,symbol,open,high,low,close,volume\n"
        "2025-01-02,BTCUSDT,102.0,108.0,101.0,106.0,2000.0\n"
        "2025-01-01,BTCUSDT,100.0,105.0,99.0,104.0,1000.0\n"
        "2025-01-03,BTCUSDT,106.0,110.0,105.0,109.0,1500.0\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def sample_csv_without_symbol(tmp_path: Path) -> Path:
    """不含 symbol 列的 OHLCV CSV（需构造时传入 symbol 参数）。"""
    csv_path = tmp_path / "ohlcv.csv"
    csv_path.write_text(
        "Datetime,Open,High,Low,Close,Volume\n"
        "2025-01-01,100.0,105.0,99.0,104.0,1000.0\n"
        "2025-01-02,102.0,108.0,101.0,106.0,2000.0\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def sample_csv_with_nan(tmp_path: Path) -> Path:
    """含缺失值、需前向填充的 CSV。"""
    csv_path = tmp_path / "nan.csv"
    csv_path.write_text(
        "datetime,symbol,open,high,low,close,volume\n"
        "2025-01-01,BTCUSDT,100.0,105.0,99.0,104.0,1000.0\n"
        "2025-01-02,BTCUSDT,,108.0,101.0,106.0,2000.0\n"
        "2025-01-03,BTCUSDT,106.0,110.0,,109.0,\n",
        encoding="utf-8",
    )
    return csv_path


@pytest.fixture
def sample_csv_missing_columns(tmp_path: Path) -> Path:
    """缺少必需列的 CSV。"""
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text(
        "datetime,symbol,open,high,low\n"
        "2025-01-01,BTCUSDT,100.0,105.0,99.0\n",
        encoding="utf-8",
    )
    return csv_path
