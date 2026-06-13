"""core.data 单元测试。"""

from datetime import datetime
from pathlib import Path

import pytest

from core.data import BaseDataFeed, CSVDataFeed
from core.models import BarData


class TestBaseDataFeed:
    """抽象基类接口约束。"""

    def test_cannot_instantiate_directly(self) -> None:
        with pytest.raises(TypeError):
            BaseDataFeed()  # type: ignore[abstract]


class TestCSVDataFeed:
    """CSV 数据源读取与回放。"""

    def test_load_csv_with_symbol_column(
        self, sample_csv_with_symbol: Path
    ) -> None:
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        bars = list(feed.get_next_bar())

        assert len(bars) == 3
        assert all(isinstance(bar, BarData) for bar in bars)
        assert all(bar.symbol == "BTCUSDT" for bar in bars)

    def test_load_csv_without_symbol_column_requires_param(
        self, sample_csv_without_symbol: Path
    ) -> None:
        with pytest.raises(ValueError, match="symbol"):
            CSVDataFeed(str(sample_csv_without_symbol))

    def test_load_csv_without_symbol_column_with_param(
        self, sample_csv_without_symbol: Path
    ) -> None:
        feed = CSVDataFeed(str(sample_csv_without_symbol), symbol="ETHUSDT")
        bars = list(feed.get_next_bar())

        assert len(bars) == 2
        assert bars[0].symbol == "ETHUSDT"

    def test_column_names_case_insensitive(
        self, sample_csv_without_symbol: Path
    ) -> None:
        feed = CSVDataFeed(str(sample_csv_without_symbol), symbol="BTCUSDT")
        bar = next(feed.get_next_bar())

        assert bar.open == 100.0
        assert bar.close == 104.0

    def test_bars_sorted_by_datetime_ascending(
        self, sample_csv_with_symbol: Path
    ) -> None:
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        bars = list(feed.get_next_bar())

        datetimes = [bar.datetime for bar in bars]
        assert datetimes == sorted(datetimes)
        assert bars[0].datetime == datetime(2025, 1, 1)
        assert bars[1].datetime == datetime(2025, 1, 2)
        assert bars[2].datetime == datetime(2025, 1, 3)

    def test_forward_fill_nan_values(self, sample_csv_with_nan: Path) -> None:
        feed = CSVDataFeed(str(sample_csv_with_nan))
        bars = list(feed.get_next_bar())

        # 第 2 行 open 缺失 -> 沿用第 1 行 open=100.0
        assert bars[1].open == 100.0
        # 第 3 行 low 缺失 -> 沿用第 2 行 low=101.0（不是第 1 行的 99.0）
        assert bars[2].low == 101.0
        # 第 3 行 volume 缺失 -> 沿用第 2 行 volume=2000.0
        assert bars[2].volume == 2000.0

    def test_get_next_bar_yields_correct_ohlcv(
        self, sample_csv_with_symbol: Path
    ) -> None:
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        first_bar = next(feed.get_next_bar())

        assert first_bar.symbol == "BTCUSDT"
        assert first_bar.datetime == datetime(2025, 1, 1)
        assert first_bar.open == 100.0
        assert first_bar.high == 105.0
        assert first_bar.low == 99.0
        assert first_bar.close == 104.0
        assert first_bar.volume == 1000.0

    def test_get_next_bar_is_reusable_generator(
        self, sample_csv_with_symbol: Path
    ) -> None:
        feed = CSVDataFeed(str(sample_csv_with_symbol))

        first_pass = list(feed.get_next_bar())
        second_pass = list(feed.get_next_bar())

        assert len(first_pass) == len(second_pass) == 3
        assert first_pass[0].close == second_pass[0].close

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        missing = tmp_path / "missing.csv"

        with pytest.raises(FileNotFoundError, match="CSV 文件不存在"):
            CSVDataFeed(str(missing))

    def test_missing_required_columns_raises(
        self, sample_csv_missing_columns: Path
    ) -> None:
        with pytest.raises(ValueError, match="缺少必需列"):
            CSVDataFeed(str(sample_csv_missing_columns))

    def test_is_subclass_of_base_data_feed(
        self, sample_csv_with_symbol: Path
    ) -> None:
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        assert isinstance(feed, BaseDataFeed)
