"""Forecast the next 3 h from the latest 24 h, using the direct model set."""
import numpy as np
import pandas as pd

from .. import config
from . import explain
from .features import build_features
from .train import ModelSet


def latest_row(grid: pd.DataFrame, models: ModelSet) -> tuple[pd.Timestamp, np.ndarray]:
    X = build_features(grid.iloc[-config.LAG_STEPS:])
    return X.index[-1], X.reindex(columns=models.meta["feature_names"]).to_numpy(dtype=np.float32)


def recent_level(models: ModelSet, sensor: str, row: np.ndarray, fallback: float) -> float:
    """Same recent level as training; fallback is the last reading if all three slots are empty."""
    names = models.meta["feature_names"]
    recent = [row[0, names.index(f"{sensor}_lag{k}")] for k in range(config.ANCHOR_STEPS)]
    recent = [v for v in recent if not np.isnan(v)]
    return float(np.median(recent)) if recent else float(fallback)


def forecast_sensor(models: ModelSet, sensor: str, origin: pd.Timestamp, row: np.ndarray,
                    fallback: float = np.nan) -> pd.Series:
    level = recent_level(models, sensor, row, fallback)
    step = pd.Timedelta(config.FREQ)
    times, values = [], []
    for h in range(1, config.HORIZON_STEPS + 1):
        booster = models.boosters[(sensor, h)]
        times.append(origin + h * step)
        values.append(level + float(booster.predict(row, num_iteration=booster.best_iteration or None)[0]))
    return pd.Series(values, index=pd.DatetimeIndex(times), name=sensor)


def explain_forecast(models: ModelSet, sensor: str, horizon: int, row: np.ndarray,
                     fallback: float = np.nan) -> dict:
    booster = models.boosters[(sensor, horizon)]
    level = recent_level(models, sensor, row, fallback)
    return explain.local_explanation(booster, models.meta["feature_names"], row, level)
