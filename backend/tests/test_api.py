import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import config
from app.data.source import DataSource
from app.data.synthetic import generate
from app.main import create_app
from app.pipeline import Pipeline, utc_now
from app.store import Store


class FixedSource(DataSource):
    name = "synthetic"

    def __init__(self, end):
        self.df, _ = generate(end, days=5)

    def read(self, start=None):
        return self.df if start is None else self.df[self.df.index >= start]


def make_client(monkeypatch, tmp_path, end):
    monkeypatch.setattr(config, "MODEL_DIR", tmp_path)
    pipeline = Pipeline(source=FixedSource(end), store=Store(":memory:"))
    pipeline.tick()
    return TestClient(create_app(pipeline, background=False)), pipeline


@pytest.fixture
def client(monkeypatch, tmp_path):
    test_client, _ = make_client(monkeypatch, tmp_path, utc_now().floor(config.FREQ))
    with test_client as c:
        yield c


def test_status_lists_every_sensor(client):
    body = client.get("/api/status").json()
    assert body["data_source"] == "synthetic"
    assert [s["key"] for s in body["sensors"]] == config.SENSOR_KEYS
    assert body["config"]["idk_width"] == 60 and body["config"]["idk_psi"] == 2


def test_times_are_utc_and_missing_values_are_null(client):
    body = client.get("/api/anomalies/turbidity").json()
    assert body["value_t"][0].endswith("Z")
    assert None in body["value_y"]
    assert None in body["scores"]


def test_short_gaps_are_joined_and_marked_estimated(monkeypatch, tmp_path):
    source = FixedSource(utc_now().floor(config.FREQ))
    source.df.iloc[-40:-38, source.df.columns.get_loc("ph")] = float("nan")
    monkeypatch.setattr(config, "MODEL_DIR", tmp_path)
    pipeline = Pipeline(source=source, store=Store(":memory:"))
    pipeline.tick()
    with TestClient(create_app(pipeline, background=False)) as c:
        body = c.get("/api/forecast/ph").json()
    assert None not in body["actual_y"]
    assert sum(body["actual_estimated"]) >= 2
    assert body["actual_estimated"][-40] and body["actual_estimated"][-39]
    assert body["gaps"] == []


def test_long_outage_stays_empty_and_is_reported(client):
    body = client.get("/api/anomalies/turbidity").json()
    assert len(body["gaps"]) == 1
    start, end = pd.Timestamp(body["gaps"][0]["start"]), pd.Timestamp(body["gaps"][0]["end"])
    assert end - start >= pd.Timedelta(minutes=30)
    missing = [t for t, y in zip(body["value_t"], body["value_y"]) if y is None]
    assert missing[0] == body["gaps"][0]["start"] and missing[-1] == body["gaps"][0]["end"]


def test_anomalies_payload(client):
    body = client.get("/api/anomalies/ph").json()
    assert len(body["scores"]) == 805 and len(body["value_y"]) == 864
    assert body["threshold"] is not None
    assert body["flagged_ranges"]


def test_forecast_without_models_explains_itself(client):
    body = client.get("/api/forecast/ph").json()
    assert body["forecast_y"] == [] and body["unavailable_reason"]
    assert len(body["actual_y"]) == 288


def test_unknown_sensor_is_404(client):
    assert client.get("/api/anomalies/nope").status_code == 404
    assert client.get("/api/forecast/nope").status_code == 404


def test_explain_without_models_is_503(client):
    assert client.get("/api/explain/ph/lags").status_code == 503


def test_episodes_open_on_first_start_and_can_be_reviewed(client, monkeypatch):
    monkeypatch.setenv("APPROVER_TOKENS", "aisha:secret-1")
    token = {"X-Approver-Token": "secret-1"}
    episodes = client.get("/api/episodes").json()
    assert episodes
    target = episodes[0]["id"]
    assert client.post(f"/api/episodes/{target}/review", json={"note": "checked"}, headers=token).status_code == 200
    assert client.post(f"/api/episodes/{target}/review", json={"note": ""}, headers=token).status_code == 404
    reviewed = [e for e in client.get("/api/episodes").json() if e["id"] == target][0]
    assert reviewed["reviewed_at"] and reviewed["reviewed_note"] == "aisha: checked"


def test_review_is_refused_without_a_valid_token(client, monkeypatch):
    target = client.get("/api/episodes").json()[0]["id"]
    monkeypatch.setenv("APPROVER_TOKENS", "aisha:secret-1")
    assert client.post(f"/api/episodes/{target}/review", json={}).status_code == 401
    wrong = client.post(f"/api/episodes/{target}/review", json={}, headers={"X-Approver-Token": "nope"})
    assert wrong.status_code == 401
    assert client.get("/api/episodes").json()[0]["reviewed_at"] is None


def test_review_is_disabled_when_no_approvers_are_configured(client, monkeypatch):
    monkeypatch.delenv("APPROVER_TOKENS", raising=False)
    target = client.get("/api/episodes").json()[0]["id"]
    response = client.post(f"/api/episodes/{target}/review", json={}, headers={"X-Approver-Token": "anything"})
    assert response.status_code == 503


def test_cors_only_allows_configured_origins(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CORS_ORIGINS", ["https://water.example.com"])
    test_client, _ = make_client(monkeypatch, tmp_path, utc_now().floor(config.FREQ))
    with test_client as c:
        good = c.get("/api/sensors", headers={"Origin": "https://water.example.com"})
        bad = c.get("/api/sensors", headers={"Origin": "https://evil.example.com"})
    assert good.headers["access-control-allow-origin"] == "https://water.example.com"
    assert "access-control-allow-origin" not in bad.headers


def test_repeat_tick_does_not_duplicate_episodes(monkeypatch, tmp_path):
    test_client, pipeline = make_client(monkeypatch, tmp_path, utc_now().floor(config.FREQ))
    with test_client as c:
        before = len(c.get("/api/episodes").json())
        pipeline.tick()
        assert len(c.get("/api/episodes").json()) == before


def test_old_data_is_stale(monkeypatch, tmp_path):
    test_client, _ = make_client(monkeypatch, tmp_path, utc_now().floor(config.FREQ) - pd.Timedelta(hours=3))
    with test_client as c:
        body = c.get("/api/status").json()
        assert {s["status"] for s in body["sensors"]} == {"stale"}
        assert "No reading" in c.get("/api/forecast/ph").json()["unavailable_reason"]
