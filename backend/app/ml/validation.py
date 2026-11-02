"""Forecast against what actually happened, for one sensor and look-ahead.

Backtest points come from the holdout, which the models never trained on. Live points are stored
forecasts whose target time has since been measured. True values are the cleaned readings, so
single-reading glitches are not counted as forecast errors.
"""
import numpy as np
import pandas as pd

from .. import config


def _summary(points: pd.DataFrame) -> dict | None:
    if points.empty:
        return None
    err = points["forecast"] - points["actual"]
    naive = (points["persistence"] - points["actual"]).abs()
    mae, naive_mae = float(err.abs().mean()), float(naive.mean())
    return {
        "n": len(points),
        "mae": mae,
        "rmse": float(np.sqrt((err ** 2).mean())),
        "bias": float(err.mean()),
        "max_error": float(err.abs().max()),
        "persistence_mae": naive_mae,
        "skill": 1 - mae / naive_mae if naive_mae > 0 else None,
        "mean_actual": float(points["actual"].mean()),
    }


def _backtest(models, sensor: str, horizon: int) -> pd.DataFrame:
    v = models.validation
    if v is None:
        return pd.DataFrame(columns=["forecast", "actual", "persistence"], dtype=float)
    row = models.meta["sensors"].index(sensor)
    step = pd.Timedelta(config.FREQ) * horizon
    origins = pd.to_datetime(v["origins"]).tz_localize(None)
    return pd.DataFrame({"forecast": v["forecast"][row, horizon - 1], "actual": v["actual"][row, horizon - 1],
                         "persistence": v["persistence"][row]}, index=origins + step).dropna()


def _live(grid: pd.DataFrame, log: pd.DataFrame, sensor: str, horizon: int) -> pd.DataFrame:
    log = log[log["horizon"] == horizon]
    times = pd.to_datetime(log["target_time"])
    actual = grid[sensor].reindex(times).to_numpy()
    earlier = grid[sensor].reindex(times - pd.Timedelta(config.FREQ) * horizon).to_numpy()
    return pd.DataFrame({"forecast": log["value"].to_numpy(dtype=float), "actual": actual, "persistence": earlier},
                        index=pd.DatetimeIndex(times)).dropna().sort_index()


def compare(models, grid: pd.DataFrame, log: pd.DataFrame, sensor: str, horizon: int) -> dict:
    live = _live(grid, log, sensor, horizon)
    backtest = _backtest(models, sensor, horizon)
    if not live.empty:
        # After a retrain the two periods overlap; a forecast really made at the time wins.
        backtest = backtest[backtest.index < live.index[0]]
    return {"backtest": backtest, "live": live,
            "summary": {"backtest": _summary(backtest), "live": _summary(live),
                        "combined": _summary(pd.concat([backtest, live]))}}
