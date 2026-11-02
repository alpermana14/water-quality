import numpy as np
import pandas as pd

from app import config
from app.data.preprocess import fill_short_gaps, long_gaps, remove_spikes, sensor_freshness, to_grid
from app.ml.features import build_features, build_target, parse_feature
from app.ml.train import split_rows


def ramp_grid(n=400):
    index = pd.date_range("2026-01-01", periods=n, freq=config.FREQ)
    return pd.DataFrame({"a": np.arange(n, dtype=float), "b": np.arange(n, dtype=float) * 10}, index=index)


def test_lags_span_24h_and_lag0_is_latest():
    grid = ramp_grid()
    X = build_features(grid)
    assert len(X) == len(grid) - 288 + 1
    assert X.index[0] == grid.index[287]
    last = X.iloc[-1]
    assert last["a_lag0"] == 399 and last["a_lag287"] == 399 - 287
    assert last["b_lag5"] == 3940


def test_target_is_future_and_no_feature_sees_it():
    grid = ramp_grid()
    X = build_features(grid)
    t = X.index[10]
    target = build_target(grid, "a", 36)[t]
    assert target == grid["a"][t] + 36
    lag_cols = [c for c in X.columns if c.startswith("a_lag")]
    assert X.loc[t, lag_cols].max() == grid["a"][t]


def test_features_never_change_when_future_changes():
    grid = ramp_grid()
    t = grid.index[350]
    before = build_features(grid).loc[t]
    altered = grid.copy()
    altered.loc[altered.index > t, :] = -999.0
    pd.testing.assert_series_equal(before, build_features(altered).loc[t])


def test_nan_is_preserved_for_lightgbm():
    grid = ramp_grid()
    grid.iloc[-3, 0] = np.nan
    assert np.isnan(build_features(grid).iloc[-1]["a_lag2"])


def test_parse_feature():
    assert parse_feature("dissolved_oxygen_lag12") == ("dissolved_oxygen", 12)
    assert parse_feature("hour_sin") == (None, None)


def test_splits_are_chronological_and_purged():
    index = pd.date_range("2026-01-01", periods=30 * 288, freq=config.FREQ)
    tr, va, ho = split_rows(index)
    assert not (tr & va).any() and not (va & ho).any()
    horizon = pd.Timedelta(config.FREQ) * config.HORIZON_STEPS
    assert index[tr][-1] + horizon < index[va][0]
    assert index[va][-1] + horizon < index[ho][0]


def test_short_history_shrinks_validation_and_holdout():
    index = pd.date_range("2026-01-01", periods=4 * 288, freq=config.FREQ)
    tr, va, ho = split_rows(index)
    assert tr.sum() > 2 * 288
    assert 0 < va.sum() and 0 < ho.sum() <= 0.16 * len(index)


def test_short_gaps_filled_long_gaps_kept():
    grid = ramp_grid(100)[["a"]].astype(float)
    grid.iloc[10:16, 0] = np.nan      # 6 steps = 30 min
    grid.iloc[40:47, 0] = np.nan      # 7 steps
    grid.iloc[-3:, 0] = np.nan        # trailing: no later reading to draw towards
    out = fill_short_gaps(grid)
    assert out["a"].iloc[10:16].tolist() == list(range(10, 16))
    assert out["a"].iloc[40:47].isna().all()
    assert out["a"].iloc[-3:].isna().all()


def test_only_gaps_too_long_to_fill_are_reported():
    grid = ramp_grid(100)[["a"]].astype(float)
    grid.iloc[10:16, 0] = np.nan      # 6 steps: filled
    grid.iloc[40:47, 0] = np.nan      # 7 steps: kept
    grid.iloc[-2:, 0] = np.nan        # newest slots just have not arrived
    gaps = long_gaps(fill_short_gaps(grid)["a"])
    assert gaps == [(grid.index[40], grid.index[46])]


def test_grid_averages_off_grid_readings():
    index = pd.to_datetime(["2026-01-01 00:01", "2026-01-01 00:03", "2026-01-01 00:11"])
    grid = to_grid(pd.DataFrame({"a": [1.0, 3.0, 5.0]}, index=index))
    assert len(grid) == 3
    assert grid["a"].iloc[0] == 2.0
    assert np.isnan(grid["a"].iloc[1])
    assert grid["a"].iloc[2] == 5.0


def noisy_series(n=300):
    rng = np.random.default_rng(0)
    index = pd.date_range("2026-01-01", periods=n, freq=config.FREQ)
    return pd.DataFrame({"a": 7 + 0.3 * np.sin(np.arange(n) / 40) + rng.normal(0, 0.01, n)}, index=index)


def test_single_reading_spike_is_set_aside_and_kept_for_reporting():
    grid = noisy_series()
    grid.iloc[100, 0] = 9.0
    clean, spikes = remove_spikes(grid)
    assert np.isnan(clean["a"].iloc[100])
    assert spikes["a"].iloc[100] == 9.0
    assert spikes["a"].notna().sum() == 1


def test_newest_reading_spike_is_set_aside():
    grid = noisy_series()
    grid.iloc[-1, 0] = 9.0
    assert np.isnan(remove_spikes(grid)[0]["a"].iloc[-1])


def test_real_step_change_is_not_removed():
    grid = noisy_series()
    grid.iloc[150:, 0] += 2.0
    clean, spikes = remove_spikes(grid)
    assert spikes["a"].notna().sum() == 0
    assert clean["a"].notna().all()


def test_quantised_sensor_with_zero_mad_still_works():
    grid = noisy_series()
    grid["a"] = (grid["a"] * 16).round() / 16
    grid.iloc[50, 0] = 429.0
    clean, spikes = remove_spikes(grid)
    assert spikes["a"].notna().sum() == 1 and np.isnan(clean["a"].iloc[50])


def test_stale_after_an_hour():
    grid = ramp_grid(20)
    now = grid.index[-1]
    assert not sensor_freshness(grid, now)["a"]["stale"]
    assert sensor_freshness(grid, now + pd.Timedelta(hours=1))["a"]["stale"]
