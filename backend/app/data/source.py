"""Where readings come from. The rest of the app only sees this interface."""
from abc import ABC, abstractmethod

import pandas as pd

from .. import config


class DataSource(ABC):
    name = "base"

    @abstractmethod
    def read(self, start: pd.Timestamp | None = None) -> pd.DataFrame:
        """Raw readings since start: a naive UTC DatetimeIndex and one numeric column per sensor."""

    def close(self) -> None:
        pass


def get_source() -> DataSource:
    if config.DATA_SOURCE == "mysql":
        from .mysql_source import MySQLSource
        return MySQLSource()
    if config.DATA_SOURCE == "synthetic":
        from .synthetic import SyntheticSource
        return SyntheticSource()
    raise ValueError(f"DATA_SOURCE must be 'mysql' or 'synthetic', got {config.DATA_SOURCE!r}")
