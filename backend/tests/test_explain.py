"""Train a tiny set for real and check the explanations add up."""
import numpy as np
import pandas as pd
import pytest

from app import config
from app.ml import explain, forecast, train


@pytest.fixture(scope="module")
def trained(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    patch.setattr(config, "LAG_STEPS", 24)
    patch.setattr(config, "HORIZON_STEPS", 3)
    patch.setattr(config, "HOLDOUT_DAYS", 2)
    patch.setattr(config, "VALIDATION_DAYS", 2)
    patch.setattr(config, "LGB_MAX_ROUNDS", 30)
    patch.setattr(config, "EXPLAIN_SAMPLE_ROWS", 50)
    patch.setattr(config, "MODEL_DIR", tmp_path_factory.mktemp("models"))

    rng = np.random.default_rng(0)
    n = 15 * 288
    index = pd.date_range("2026-01-01", periods=n, freq=config.FREQ)
    a = np.sin(2 * np.pi * np.arange(n) / 288) + rng.normal(0, 0.02, n)
    b = 2 * np.roll(a, 12) + rng.normal(0, 0.02, n)
    grid = pd.DataFrame({"a": a, "b": b}, index=index)
    try:
        meta = train.train_all(grid, version="test", progress=lambda m: None)
        yield grid, meta, train.ModelSet(config.MODEL_DIR / "test")
    finally:
        patch.undo()


def test_contributions_sum_to_prediction(trained):
    grid, _, models = trained
    origin, row = forecast.latest_row(grid, models)
    series = forecast.forecast_sensor(models, "a", origin, row)
    assert len(series) == 3
    assert series.index[0] == origin + pd.Timedelta(config.FREQ)
    for h in (1, 2, 3):
        contrib, base = explain.contributions(models.boosters[("a", h)], row)
        level = forecast.recent_level(models, "a", row, np.nan)
        assert level + base + contrib.sum() == pytest.approx(series.iloc[h - 1], abs=1e-6)


def test_local_explanation_reconciles_with_folded_items(trained):
    grid, _, models = trained
    _, row = forecast.latest_row(grid, models)
    out = forecast.explain_forecast(models, "a", 2, row)
    total = out["recent_level"] + out["base_value"] + sum(i["contribution"] for i in out["items"]) + out["others"]
    assert total == pytest.approx(out["prediction"], abs=1e-3)


def test_recent_level_ignores_one_glitch_reading(trained):
    grid, _, models = trained
    origin, row = forecast.latest_row(grid, models)
    glitched = row.copy()
    glitched[0, models.meta["feature_names"].index("a_lag0")] = 999.0
    assert forecast.recent_level(models, "a", glitched, np.nan) < 10
    assert forecast.forecast_sensor(models, "a", origin, glitched).max() < 100


def test_change_target_can_forecast_beyond_training_range(trained):
    grid, _, models = trained
    shifted = grid.copy()
    shifted["a"] = shifted["a"] + 100
    origin, row = forecast.latest_row(shifted, models)
    assert forecast.forecast_sensor(models, "a", origin, row).min() > 90


def test_lag_summary_shape_and_shares(trained):
    _, meta, _ = trained
    e = meta["explanations"]["a"]
    assert e["horizons"] == [1, 2, 3]
    assert len(e["input_sensors"]["b"]["by_lag"]) == 24
    assert len(e["input_sensors"]["a"]["heatmap_hour"]) == 3
    assert sum(v["share"] for v in e["input_sensors"].values()) + e["clock_share"] == pytest.approx(1, abs=1e-2)


def test_saved_validation_matches_reported_skill(trained):
    grid, meta, models = trained
    v = models.validation
    row = meta["sensors"].index("a")
    h = 2
    # Reload proves it survives saving; truth must equal the real reading at the target time.
    origins = pd.to_datetime(v["origins"])
    truth = grid["a"].reindex(origins + h * pd.Timedelta(config.FREQ)).to_numpy()
    ok = ~np.isnan(truth)
    np.testing.assert_allclose(v["actual"][row, h - 1][ok], truth[ok])
    held = v["forecast"][row, h - 1][ok] - v["actual"][row, h - 1][ok]
    assert np.abs(held).mean() == pytest.approx(meta["skill"]["a"][h - 1]["mae"], rel=1e-6)


def test_backtest_reports_persistence(trained):
    _, meta, _ = trained
    row = meta["skill"]["a"][2]
    assert row["persistence_mae"] > 0 and row["n"] > 0


def test_model_round_trip_keeps_predictions(trained):
    grid, _, models = trained
    origin, row = forecast.latest_row(grid, models)
    reloaded = train.ModelSet(models.path)
    a = forecast.forecast_sensor(models, "b", origin, row)
    b = forecast.forecast_sensor(reloaded, "b", origin, row)
    pd.testing.assert_series_equal(a, b)
