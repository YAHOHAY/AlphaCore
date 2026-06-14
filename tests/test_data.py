"""core.data 单元测试。"""

from datetime import datetime
from pathlib import Path

import pytest

from core.data import BaseDataFeed, CSVDataFeed
from core.models import BarData


class TestBaseDataFeed:
    """抽象基类接口约束。"""

    def test_cannot_instantiate_directly(self) -> None:
        """BaseDataFeed 是抽象类，直接实例化应抛 TypeError(强制子类实现接口)。"""
        with pytest.raises(TypeError):
            BaseDataFeed()  # type: ignore[abstract]


class TestCSVDataFeed:
    """CSV 数据源读取与回放。"""

    def test_load_csv_with_symbol_column(
        self, sample_csv_with_symbol: Path
    ) -> None:
        """含 symbol 列的 CSV 能正常加载，回放出的全部对象都是 BarData。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        bars = list(feed.get_next_bar())

        assert len(bars) == 3
        assert all(isinstance(bar, BarData) for bar in bars)
        assert all(bar.symbol == "BTCUSDT" for bar in bars)

    def test_load_csv_without_symbol_column_requires_param(
        self, sample_csv_without_symbol: Path
    ) -> None:
        """CSV 无 symbol 列且未传 symbol 参数时，应报错而非静默生成错误数据。"""
        with pytest.raises(ValueError, match="symbol"):
            CSVDataFeed(str(sample_csv_without_symbol))

    def test_load_csv_without_symbol_column_with_param(
        self, sample_csv_without_symbol: Path
    ) -> None:
        """CSV 无 symbol 列但传入 symbol 参数时，应用该参数填充每根 BarData。"""
        feed = CSVDataFeed(str(sample_csv_without_symbol), symbol="ETHUSDT")
        bars = list(feed.get_next_bar())

        assert len(bars) == 2
        assert bars[0].symbol == "ETHUSDT"

    def test_column_names_case_insensitive(
        self, sample_csv_without_symbol: Path
    ) -> None:
        """列名大小写不敏感:大写表头(Open/Close)也能被正确识别解析。"""
        feed = CSVDataFeed(str(sample_csv_without_symbol), symbol="BTCUSDT")
        bar = next(feed.get_next_bar())

        assert bar.open == 100.0
        assert bar.close == 104.0

    def test_bars_sorted_by_datetime_ascending(
        self, sample_csv_with_symbol: Path
    ) -> None:
        """乱序 CSV 加载后应按时间升序回放(杜绝未来函数的前提)。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        bars = list(feed.get_next_bar())

        datetimes = [bar.datetime for bar in bars]
        assert datetimes == sorted(datetimes)
        assert bars[0].datetime == datetime(2025, 1, 1)
        assert bars[1].datetime == datetime(2025, 1, 2)
        assert bars[2].datetime == datetime(2025, 1, 3)

    def test_forward_fill_nan_values(self, sample_csv_with_nan: Path) -> None:
        """缺失值应按前向填充(ffill)处理:用上一根的有效值补齐当前 NaN。"""
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
        """get_next_bar 产出的 BarData 各字段值应与 CSV 内容精确对应。"""
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
        """get_next_bar 每次调用都返回全新生成器,可被回测引擎多次完整遍历。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))

        first_pass = list(feed.get_next_bar())
        second_pass = list(feed.get_next_bar())

        assert len(first_pass) == len(second_pass) == 3
        assert first_pass[0].close == second_pass[0].close

    def test_file_not_found_raises(self, tmp_path: Path) -> None:
        """构造时文件不存在应抛 FileNotFoundError 并带明确提示。"""
        missing = tmp_path / "missing.csv"

        with pytest.raises(FileNotFoundError, match="CSV 文件不存在"):
            CSVDataFeed(str(missing))

    def test_missing_required_columns_raises(
        self, sample_csv_missing_columns: Path
    ) -> None:
        """CSV 缺少 OHLCV 必需列时应抛 ValueError,避免加载残缺行情。"""
        with pytest.raises(ValueError, match="缺少必需列"):
            CSVDataFeed(str(sample_csv_missing_columns))

    def test_is_subclass_of_base_data_feed(
        self, sample_csv_with_symbol: Path
    ) -> None:
        """CSVDataFeed 应为 BaseDataFeed 子类,保证上层只依赖抽象接口(依赖倒置)。"""
        feed = CSVDataFeed(str(sample_csv_with_symbol))
        assert isinstance(feed, BaseDataFeed)
