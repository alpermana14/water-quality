"""Does the detector find anomalies planted in the synthetic series, and stay quiet without them?"""
import numpy as np
import pandas as pd
import pytest

from app import config
from app.data.preprocess import to_grid
from app.data.synthetic import generate
from app.ml import anomaly

END = pd.Timestamp("2026-06-15 00:00")


@pytest.fixture(scope="module")
def planted():
    df, anomalies = generate(END, days=20)
    return to_grid(df), {(s, k): (a, b) for s, k, a, b in anomalies}


def flagged_near(result, start, stop):
    """Any flagged window overlapping the planted span?"""
    width = pd.Timedelta(config.FREQ) * (config.IDK_WIDTH - 1)
    mask = (result["times"] >= start) & (result["times"] - width <= stop)
    return bool(result["flags"][mask].any())


@pytest.mark.parametrize("sensor,kind", [("ph", "step"), ("conductivity", "step")])
def test_planted_step_is_caught_at_most_seeds(planted, sensor, kind):
    """s-IDK samples at random, so judge the hit rate, not one draw."""
    grid, spans = planted
    start, stop = spans[(sensor, kind)]
    series = grid[sensor]
    hits = sum(flagged_near(anomaly.score_sensor(series.iloc[:-i or None], sensor), start, stop) for i in range(10))
    assert hits >= 8


def test_stuck_sensor_at_a_normal_value_is_flagged(planted):
    grid, spans = planted
    result = anomaly.score_sensor(grid["dissolved_oxygen"], "dissolved_oxygen")
    assert result["stuck"].any()
    assert flagged_near(result, *spans[("dissolved_oxygen", "stuck")])


def test_turbidity_gap_windows_are_not_scored(planted):
    grid, spans = planted
    result = anomaly.score_sensor(grid["turbidity"], "turbidity")
    start, stop = spans[("turbidity", "gap")]
    assert grid["turbidity"][start:stop].isna().sum() >= 17
    assert np.isnan(result["scores"]).any()


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_clean_series_flag_rate(seed):
    df, _ = generate(END, days=20, inject=False, seed=seed)
    grid = to_grid(df)
    rates = {s: float(anomaly.score_sensor(grid[s], s)["flags"].mean()) for s in config.SENSOR_KEYS}
    print(f"seed {seed} flag rates {rates}")
    assert np.mean(list(rates.values())) < 0.15
