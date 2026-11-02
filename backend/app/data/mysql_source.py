"""Read-only access to the sensor table. Nothing in this app writes to MySQL."""
import os

import pandas as pd
from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import URL

from .. import config
from .source import DataSource


def make_engine():
    missing = [k for k in ("DB_HOST", "DB_USER", "DB_NAME") if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"MySQL settings missing from .env: {', '.join(missing)}")
    url = URL.create(
        "mysql+mysqlconnector",
        username=os.environ["DB_USER"],
        password=os.getenv("DB_PASSWORD", ""),
        host=os.environ["DB_HOST"],
        port=int(os.getenv("DB_PORT", "3306")),
        database=os.environ["DB_NAME"],
    )
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800)


def quote(identifier: str) -> str:
    """Identifiers cannot be bound as parameters, so they are restricted before quoting."""
    if not identifier or not all(c.isalnum() or c == "_" for c in identifier):
        raise ValueError(f"Invalid SQL identifier: {identifier!r}")
    return f"`{identifier}`"


class MySQLSource(DataSource):
    name = "mysql"

    def __init__(self):
        if not config.DB_TABLE:
            raise RuntimeError("DB_TABLE is not set. Run scripts/inspect_db.py to find it.")
        self.engine = make_engine()

    def read(self, start=None):
        time_col = quote(config.DB_TIME_COLUMN)
        table = quote(config.DB_TABLE)
        if config.DB_FORMAT == "long":
            cols = f"{time_col}, {quote(config.DB_SENSOR_COLUMN)}, {quote(config.DB_VALUE_COLUMN)}"
        else:
            cols = ", ".join([time_col] + [quote(k) for k in config.SENSOR_KEYS])
        sql = f"SELECT {cols} FROM {table}"
        params = {}
        if start is not None:
            sql += f" WHERE {time_col} >= :start"
            local = pd.Timestamp(start).tz_localize("UTC").tz_convert(config.DB_TIMEZONE).tz_localize(None)
            params["start"] = local.to_pydatetime()
        sql += f" ORDER BY {time_col}"
        stmt = text(sql).bindparams(*[bindparam(k) for k in params])

        with self.engine.connect() as conn:
            df = pd.read_sql(stmt, conn, params=params)

        times = pd.to_datetime(df[config.DB_TIME_COLUMN])
        if times.dt.tz is None:
            times = times.dt.tz_localize(config.DB_TIMEZONE, ambiguous="NaT", nonexistent="NaT")
        df[config.DB_TIME_COLUMN] = times.dt.tz_convert("UTC").dt.tz_localize(None)
        df = df.dropna(subset=[config.DB_TIME_COLUMN])

        if config.DB_FORMAT == "long":
            df = df.pivot_table(index=config.DB_TIME_COLUMN, columns=config.DB_SENSOR_COLUMN,
                                values=config.DB_VALUE_COLUMN, aggfunc="mean")
        else:
            df = df.set_index(config.DB_TIME_COLUMN)
        return df.reindex(columns=config.SENSOR_KEYS).apply(pd.to_numeric, errors="coerce")

    def close(self):
        self.engine.dispose()
