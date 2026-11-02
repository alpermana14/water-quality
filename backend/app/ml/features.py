"""Lag matrix and direct multi-step targets.

Row t holds what is known at t: {sensor}_lag{k} = sensor[t - k] for k = 0..LAG_STEPS-1, so lag0
is the latest reading and the row spans exactly 24 h. Target for horizon h is sensor[t + h].
"""
import numpy as np
import pandas as pd

from .. import config


def feature_names(sensors=None) -> list[str]:
    sensors = sensors or config.SENSOR_KEYS
    return [f"{s}_lag{k}" for s in sensors for k in range(config.LAG_STEPS)] + ["hour_sin", "hour_cos"]


def build_features(grid: pd.DataFrame) -> pd.DataFrame:
    """All rows with a full 24 h behind them. NaN stays in: LightGBM treats missing natively."""
    sensors = list(grid.columns)
    values = grid.to_numpy(dtype=np.float32)
    n_rows = len(grid) - config.LAG_STEPS + 1
    if n_rows <= 0:
        return pd.DataFrame(columns=feature_names(sensors), dtype=np.float32)

    windows = np.lib.stride_tricks.sliding_window_view(values, config.LAG_STEPS, axis=0)
    # windows[t, sensor, j]: j runs oldest to newest, so reverse to make lag 0 the latest.
    lags = windows[:, :, ::-1].reshape(n_rows, -1)
    index = grid.index[config.LAG_STEPS - 1:]
    hours = index.hour + index.minute / 60
    clock = np.column_stack([np.sin(2 * np.pi * hours / 24), np.cos(2 * np.pi * hours / 24)])
    return pd.DataFrame(np.hstack([lags, clock]).astype(np.float32), index=index,
                        columns=feature_names(sensors))


def build_target(grid: pd.DataFrame, sensor: str, horizon: int) -> pd.Series:
    return grid[sensor].shift(-horizon)


def anchor(X: pd.DataFrame, sensor: str) -> pd.Series:
    """Recent level each forecast is measured from: robust to a single-reading glitch."""
    cols = [f"{sensor}_lag{k}" for k in range(config.ANCHOR_STEPS)]
    return X[cols].median(axis=1, skipna=True)


def parse_feature(name: str) -> tuple[str | None, int | None]:
    """'ph_lag12' -> ('ph', 12); clock features -> (None, None)."""
    if "_lag" not in name:
        return None, None
    sensor, lag = name.rsplit("_lag", 1)
    return sensor, int(lag)
