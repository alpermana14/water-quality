from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app import config
from app.ml import validation


def fake_models(origins, forecast, actual, persistence, horizons=3):
    def by_horizon(values):
        return np.tile(np.array(values, dtype=float), (1, horizons, 1))

    return SimpleNamespace(
        meta={"sensors": ["a"]},
        validation={
            "origins": np.array(origins.strftime("%Y-%m-%d %H:%M:%S"), dtype="U19"),
            "forecast": by_horizon(forecast),
            "actual": by_horizon(actual),
            "persistence": np.array(persistence, dtype=float).reshape(1, -1),
        })


EMPTY_LOG = pd.DataFrame(columns=["horizon", "target_time", "value"])


def test_backtest_points_sit_at_target_time_and_stats_are_right():
    origins = pd.date_range("2026-01-01", periods=4, freq=config.FREQ)
    models = fake_models(origins, [1, 2, 3, 6], [1, 1, 1, 1], [2, 2, 2, 2])
    grid = pd.DataFrame({"a": [1.0] * 4}, index=origins)
    out = validation.compare(models, grid, EMPTY_LOG, "a", 1)

    assert out["backtest"].index[0] == origins[0] + pd.Timedelta(config.FREQ)
    s = out["summary"]["backtest"]
    assert s["mae"] == pytest.approx(2.0)          # errors 0, 1, 2, 5
    assert s["bias"] == pytest.approx(2.0)
    assert s["max_error"] == pytest.approx(5.0)
    assert s["persistence_mae"] == pytest.approx(1.0)
    assert s["skill"] == pytest.approx(-1.0)
    assert out["summary"]["live"] is None


def test_missing_truth_is_not_scored():
    origins = pd.date_range("2026-01-01", periods=3, freq=config.FREQ)
    models = fake_models(origins, [1, 2, 3], [1, np.nan, 3], [1, 1, 1])
    out = validation.compare(models, pd.DataFrame({"a": [1.0] * 3}, index=origins), EMPTY_LOG, "a", 1)
    assert out["summary"]["backtest"]["n"] == 2


def test_live_points_join_truth_and_replace_overlapping_backtest():
    grid_index = pd.date_range("2026-01-01", periods=12, freq=config.FREQ)
    grid = pd.DataFrame({"a": np.arange(12.0)}, index=grid_index)
    models = fake_models(grid_index[:6], [0] * 6, [0] * 6, [0] * 6)
    log = pd.DataFrame({
        "horizon": [2, 2, 3, 2],
        "target_time": [str(grid_index[4]), str(grid_index[5]), str(grid_index[6]), str(grid_index[11] + pd.Timedelta(hours=1))],
        "value": [5.0, 7.0, 9.0, 1.0],
    })
    out = validation.compare(models, grid, log, "a", 2)

    live = out["live"]
    assert list(live["forecast"]) == [5.0, 7.0]    # other horizon and unmeasured future left out
    assert list(live["actual"]) == [4.0, 5.0]
    assert list(live["persistence"]) == [2.0, 3.0]
    assert out["backtest"].index.max() < live.index[0]
    assert out["summary"]["live"]["mae"] == pytest.approx(1.5)


def test_models_without_saved_validation_still_report_live():
    index = pd.date_range("2026-01-01", periods=4, freq=config.FREQ)
    models = SimpleNamespace(meta={"sensors": ["a"]}, validation=None)
    out = validation.compare(models, pd.DataFrame({"a": [1.0] * 4}, index=index), EMPTY_LOG, "a", 1)
    assert out["summary"]["combined"] is None
