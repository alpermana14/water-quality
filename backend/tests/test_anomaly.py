import numpy as np
import pandas as pd
import pytest

from app import config
from app.ml import anomaly
from app.store import Store


def clean_series(n=864, seed=1, scale=1.0, offset=0.0):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=n, freq=config.FREQ)
    day = 2 * np.pi * np.arange(n) / 288
    return pd.Series(offset + scale * (np.sin(day) + rng.normal(0, 0.05, n)), index=index)


def test_864_points_give_805_scores_aligned_to_window_ends():
    s = clean_series()
    r = anomaly.score_sensor(s, "x")
    assert len(r["scores"]) == 805
    assert r["times"][0] == s.index[59]
    assert r["times"][-1] == s.index[-1]


def test_same_input_same_scores():
    s = clean_series()
    a, b = anomaly.score_sensor(s, "x"), anomaly.score_sensor(s, "x")
    np.testing.assert_array_equal(a["scores"], b["scores"])


def test_large_units_behave_like_small_units():
    small = anomaly.score_sensor(clean_series(), "x")
    large = anomaly.score_sensor(clean_series(scale=50000.0, offset=50000.0), "x")
    np.testing.assert_allclose(small["scores"], large["scores"], atol=1e-9)


def test_step_change_is_flagged():
    s = clean_series()
    s.iloc[500:580] += 6
    r = anomaly.score_sensor(s, "x")
    hit = r["flags"][(r["times"] >= s.index[500]) & (r["times"] <= s.index[640])]
    assert hit.any()


def test_clean_series_has_low_flag_rate():
    rates = [anomaly.score_sensor(clean_series(seed=i), "x")["flags"].mean() for i in range(5)]
    assert np.mean(rates) < 0.1


def test_warming_up():
    assert anomaly.score_sensor(clean_series(n=500), "x")["status"] == anomaly.WARMING_UP


def test_constant_population_is_flatline():
    s = clean_series() * 0 + 7.0
    assert anomaly.score_sensor(s, "x")["status"] == anomaly.FLATLINE


def test_stuck_latest_window_is_flatline():
    s = clean_series()
    s.iloc[-70:] = s.iloc[-71]
    assert anomaly.score_sensor(s, "x")["status"] == anomaly.FLATLINE


def test_mad_zero_is_undetermined(monkeypatch):
    monkeypatch.setattr(anomaly, "window_scores", lambda v, k: np.full(805, 0.5))
    r = anomaly.score_sensor(clean_series(), "x")
    assert r["status"] == anomaly.UNDETERMINED and not r["flags"].any()


def test_gappy_windows_are_excluded_from_scoring():
    s = clean_series()
    s.iloc[300:330] = np.nan     # 30 of 60 is over the 20% limit
    r = anomaly.score_sensor(s, "x")
    covered = (r["times"] >= s.index[300]) & (r["times"] <= s.index[389])
    assert np.isnan(r["scores"]).sum() > 0
    assert not r["flags"][np.isnan(r["scores"])].any()
    assert np.isnan(r["scores"][covered]).any()


def test_gap_at_the_end_is_insufficient():
    s = clean_series()
    s.iloc[-40:] = np.nan
    assert anomaly.score_sensor(s, "x")["status"] == anomaly.INSUFFICIENT


@pytest.fixture
def store():
    return Store(":memory:")


def test_episode_review_survives_restart(tmp_path):
    path = tmp_path / "app.db"
    first = Store(path)
    first.update_episode("ph", pd.Timestamp("2026-01-01"), True, 0.1)
    assert first.review_episode(first.episodes()[0]["id"], "checked")
    first.conn.close()

    episode = Store(path).episodes()[0]
    assert episode["reviewed_at"] and episode["reviewed_note"] == "checked"


def test_episode_stays_open_after_scores_recover(store):
    t = pd.date_range("2026-01-01", periods=4, freq=config.FREQ)
    store.update_episode("ph", t[0], True, 0.1)
    store.update_episode("ph", t[1], False, 0.5)
    ep = store.episodes()
    assert len(ep) == 1 and ep[0]["reviewed_at"] is None and not ep[0]["currently_flagged"]

    store.update_episode("ph", t[2], True, 0.05)
    ep = store.episodes()
    assert len(ep) == 1 and ep[0]["min_score"] == 0.05

    assert store.review_episode(ep[0]["id"], "checked")
    assert not store.review_episode(ep[0]["id"], "again")
    store.update_episode("ph", t[3], True, 0.1)
    assert len(store.episodes()) == 2
