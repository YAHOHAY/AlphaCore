"""数据源模块 (DataFeed)。

依据 `docs/PRD_v1.md` 第 3.1 节实现行情数据的读取与回放。

设计要点:
    * ``BaseDataFeed`` 抽象基类: 定义所有数据源必须遵守的统一接口，便于未来
      扩展数据库、Tick 级、API 等不同数据源而无需改动上层策略代码 (依赖倒置)。
    * ``CSVDataFeed`` 具体实现: 读取本地 CSV 文件，前向填充缺失值，并通过生成器
      按时间顺序逐根回放 K 线。

杜绝未来函数 (No Lookahead Bias):
    数据在加载时会按时间戳升序排序，``get_next_bar`` 严格按时间顺序逐根 yield，
    保证引擎在时刻 T 只能看到 <= T 的数据。
"""

from abc import ABC, abstractmethod
from collections.abc import Generator
from pathlib import Path

import pandas as pd

from core.models import BarData


class BaseDataFeed(ABC):
    """数据源抽象基类。

    定义统一的行情回放接口。任何具体数据源 (CSV、数据库、实时 API 等) 都必须
    继承本类并实现 ``get_next_bar`` 方法，从而保证上层策略与撮合引擎无需关心
    底层数据来源。
    """

    @abstractmethod
    def get_next_bar(self) -> Generator[BarData, None, None]:
        """按时间顺序逐根回放 K 线数据。

        这是一个生成器方法，每次 yield 出一根 ``BarData``，直到数据耗尽。

        Yields:
            BarData: 下一根（时间上更晚的）K 线数据对象。
        """
        raise NotImplementedError


class CSVDataFeed(BaseDataFeed):
    """基于本地 CSV 文件的数据源实现。

    读取本地 CSV 行情文件，完成数据清洗（前向填充缺失值）与时间排序，
    并以生成器形式按时间顺序逐根输出 ``BarData``。

    CSV 文件要求包含以下列 (列名大小写不敏感):
        ``datetime, open, high, low, close, volume``。
    ``symbol`` 列为可选: 若 CSV 中不含该列，则需要在构造时通过 ``symbol``
    参数显式指定（PRD 中 ``__init__`` 仅定义了 ``filepath``，此处新增可选
    ``symbol`` 参数以兼容不含标的列的常见 OHLCV 文件，属于向后兼容的小幅增强）。

    Attributes:
        filepath (Path): CSV 文件路径。
        data (pd.DataFrame): 清洗、排序后的行情数据。
    """

    REQUIRED_COLUMNS: tuple[str, ...] = (
        "datetime",
        "open",
        "high",
        "low",
        "close",
        "volume",
    )

    def __init__(self, filepath: str, symbol: str | None = None) -> None:
        """加载并预处理 CSV 数据。

        加载流程: 读取 CSV -> 统一列名 -> 校验必需列 -> 解析时间戳 ->
        按时间升序排序 -> 对数值列执行前向填充 (Forward Fill)。

        Args:
            filepath: 本地 CSV 文件路径。
            symbol: 交易标的代码。当 CSV 文件不包含 ``symbol`` 列时必须提供，
                用于填充每根 ``BarData`` 的 ``symbol`` 字段。

        Raises:
            FileNotFoundError: 指定的 CSV 文件不存在。
            ValueError: CSV 缺少必需列，或既无 ``symbol`` 列也未提供 ``symbol`` 参数。
        """
        self.filepath: Path = Path(filepath)
        if not self.filepath.is_file():
            raise FileNotFoundError(f"CSV 文件不存在: {self.filepath}")

        self._default_symbol: str | None = symbol
        self.data: pd.DataFrame = self._load_and_clean()

    def _load_and_clean(self) -> pd.DataFrame:
        """读取 CSV 并完成清洗。

        Returns:
            pd.DataFrame: 已按时间升序排序、并对数值列执行前向填充后的行情数据。
                索引为默认的连续整数索引 (RangeIndex)。

        Raises:
            ValueError: CSV 缺少必需列，或缺少标的信息。
        """
        df: pd.DataFrame = pd.read_csv(self.filepath)
        df.columns = [str(col).strip().lower() for col in df.columns]

        missing: list[str] = [
            col for col in self.REQUIRED_COLUMNS if col not in df.columns
        ]
        if missing:
            raise ValueError(
                f"CSV 缺少必需列: {missing}。需包含 {list(self.REQUIRED_COLUMNS)}。"
            )

        if "symbol" not in df.columns:
            if self._default_symbol is None:
                raise ValueError(
                    "CSV 不含 'symbol' 列，且未通过 symbol 参数指定交易标的。"
                )
            df["symbol"] = self._default_symbol

        df["datetime"] = pd.to_datetime(df["datetime"])

        # 升序排序以杜绝未来函数: 保证回放严格遵循时间先后顺序。
        df = df.sort_values("datetime", kind="stable").reset_index(drop=True)

        # 前向填充缺失值 (Forward Fill): 用上一有效观测值填补 NaN，
        # 符合行情数据“沿用最近已知价格”的语义，且不会引入未来信息。
        numeric_cols: list[str] = ["open", "high", "low", "close", "volume"]
        df[numeric_cols] = df[numeric_cols].ffill()

        return df

    def get_next_bar(self) -> Generator[BarData, None, None]:
        """按时间顺序逐根回放 K 线数据。

        遍历已清洗排序的内部 ``DataFrame``，将每一行封装为 ``BarData`` 并 yield。

        Yields:
            BarData: 下一根（时间上更晚的）K 线数据对象。
        """
        for row in self.data.itertuples(index=False):
            yield BarData(
                symbol=str(row.symbol),
                datetime=row.datetime.to_pydatetime(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
            )
