"""Dashboard API. All times are UTC with a Z suffix; the frontend converts for display."""
import secrets
from contextlib import asynccontextmanager

import numpy as np
import pandas as pd
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, scheduler
from .data.preprocess import long_gaps
from .ml import forecast, validation
from .pipeline import Pipeline

LIVE_ERROR_WINDOW = pd.Timedelta(hours=24)
VALIDATION_WINDOW = pd.Timedelta(days=14)
SKILL_HIGHLIGHTS = {"+30 min": 6, "+1 h": 12, "+3 h": 36}


def iso(ts) -> str | None:
    return None if ts is None or pd.isna(ts) else pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%SZ")


def numbers(values, digits=4) -> list:
    return [None if v is None or not np.isfinite(v) else round(float(v), digits) for v in values]


def authorise(token: str | None) -> str:
    """The named approver for a token. Follows the reference repo: no approvers, no reviews."""
    known = config.approvers()
    if not known:
        raise HTTPException(503, detail="Review is disabled: no approvers are configured.")
    for candidate, name in known.items():
        if token and secrets.compare_digest(token, candidate):
            return name
    raise HTTPException(401, detail="Invalid or missing approver token.")


def chart_series(p: Pipeline, sensor: str, steps: int) -> tuple[pd.Series, list, list]:
    """Latest values with short gaps joined, which points were estimated, and the long gaps left."""
    values = p.display[sensor].iloc[-steps:]
    estimated = (p.grid[sensor].iloc[-steps:].isna() & values.notna()).tolist()
    gaps = [{"start": iso(a), "end": iso(b)} for a, b in long_gaps(values)]
    return values, estimated, gaps


def create_app(pipeline: Pipeline | None = None, background: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pipeline = pipeline or Pipeline()
        jobs = scheduler.start(app.state.pipeline) if background else None
        yield
        if jobs:
            jobs.shutdown(wait=False)
        app.state.pipeline.source.close()

    app = FastAPI(title="Water Quality Monitoring", lifespan=lifespan)
    if config.CORS_ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", "X-Approver-Token"])

    def ready() -> Pipeline:
        p = app.state.pipeline
        if p.grid is None:
            raise HTTPException(503, detail=p.last_error or "First data read in progress")
        return p

    def known(sensor: str) -> str:
        if sensor not in config.SENSOR_KEYS:
            raise HTTPException(404, detail=f"Unknown sensor {sensor!r}. Available: {config.SENSOR_KEYS}")
        return sensor

    def sensor_status(p: Pipeline, sensor: str) -> str:
        if p.freshness[sensor]["stale"]:
            return "stale"
        return p.scores[sensor]["status"]

    @app.get("/api/status")
    def status():
        p = app.state.pipeline
        models = p.models
        base = {
            "data_source": p.source.name,
            "display_timezone": config.DISPLAY_TIMEZONE,
            "last_tick": iso(p.last_tick),
            "last_error": p.last_error,
            "training": p.training,
            "train_blocked": p.store.get("train_blocked"),
            "model": None if models is None else {
                "version": models.version, "trained_at": models.meta["trained_at"],
                "data_end": iso(models.meta["data_end"]), "models": models.meta["models"],
                "train_seconds": models.meta["train_seconds"], "rows": models.meta["rows"],
                "history_days": models.meta["history_days"], "holdout_hours": models.meta["holdout_hours"],
                "limited_history": models.meta["history_days"] < config.FULL_HISTORY_DAYS,
            },
            "config": {
                "step_minutes": config.STEP_MINUTES, "lags": config.LAG_STEPS, "horizon": config.HORIZON_STEPS,
                "idk_width": config.IDK_WIDTH, "idk_psi": config.IDK_PSI, "idk_population": config.IDK_POPULATION,
            },
        }
        if p.grid is None:
            return {**base, "latest_reading": None, "sensors": []}
        rows = []
        for s in config.SENSORS:
            f = p.freshness[s.key]
            tail = p.display[s.key].iloc[-config.STEPS_PER_HOUR * 6:]
            rows.append({"key": s.key, "label": s.label, "unit": s.unit, "status": sensor_status(p, s.key),
                         "value": f["last_value"], "time": iso(f["last_time"]), "spark": numbers(tail.values, 3),
                         "forecast_3h": None if s.key not in p.forecasts else round(float(p.forecasts[s.key].iloc[-1]), 3)})
        return {**base, "latest_reading": iso(p.grid.index[-1]), "sensors": rows}

    @app.get("/api/sensors")
    def sensors():
        return [{"key": s.key, "label": s.label, "unit": s.unit} for s in config.SENSORS]

    @app.get("/api/forecast/{sensor}")
    def get_forecast(sensor: str):
        p, sensor = ready(), known(sensor)
        actual, estimated, gaps = chart_series(p, sensor, config.LAG_STEPS)
        pred = p.forecasts.get(sensor)
        return {
            "actual_t": [iso(t) for t in actual.index], "actual_y": numbers(actual.values),
            "actual_estimated": estimated, "gaps": gaps,
            "forecast_t": [] if pred is None else [iso(t) for t in pred.index],
            "forecast_y": [] if pred is None else numbers(pred.values),
            "origin": iso(p.origin),
            "unavailable_reason": None if pred is not None else _forecast_gap_reason(p, sensor),
        }

    def _forecast_gap_reason(p: Pipeline, sensor: str) -> str:
        if p.freshness[sensor]["stale"]:
            return "No reading in the last hour, so no forecast is shown."
        if p.training:
            return "Models are training."
        blocked = p.store.get("train_blocked")
        return f"Not enough history to train: {blocked}." if blocked else "No trained model yet."

    @app.get("/api/forecast/{sensor}/skill")
    def forecast_skill(sensor: str):
        p, sensor = ready(), known(sensor)
        models = p.models
        if models is None:
            return {"backtest": [], "highlights": [], "live": []}
        backtest = models.meta["skill"][sensor]
        highlights = [{"label": label, **backtest[h - 1]} for label, h in SKILL_HIGHLIGHTS.items()]
        return {"backtest": backtest, "highlights": highlights, "live": _live_error(p, sensor)}

    @app.get("/api/forecast/{sensor}/validation")
    def forecast_validation(sensor: str, horizon: int = Query(12, ge=1, le=config.HORIZON_STEPS)):
        p, sensor = ready(), known(sensor)
        if p.models is None:
            raise HTTPException(503, detail="No trained model yet")
        now = p.grid.index[-1]
        log = p.store.forecast_log(sensor, now - VALIDATION_WINDOW)
        result = validation.compare(p.models, p.grid, log, sensor, horizon)

        def rows(frame):
            return {"t": [iso(t) for t in frame.index], "forecast": numbers(frame["forecast"].values),
                    "actual": numbers(frame["actual"].values), "persistence": numbers(frame["persistence"].values)}

        return {"horizon": horizon, "backtest": rows(result["backtest"]), "live": rows(result["live"]),
                "summary": result["summary"]}

    def _live_error(p: Pipeline, sensor: str) -> list:
        """Mean absolute error of stored forecasts whose target time has now been observed."""
        now = p.grid.index[-1]
        log = p.store.forecast_log(sensor, now - LIVE_ERROR_WINDOW)
        if log.empty:
            return []
        log["target_time"] = pd.to_datetime(log["target_time"])
        log = log[log["target_time"] <= now]
        log["actual"] = p.grid[sensor].reindex(log["target_time"]).to_numpy()
        log = log.dropna(subset=["actual"])
        log["ae"] = (log["value"] - log["actual"]).abs()
        by_h = log.groupby("horizon")["ae"].agg(["mean", "size"])
        return [{"label": label, "mae": round(float(by_h.loc[h, "mean"]), 4), "n": int(by_h.loc[h, "size"])}
                for label, h in SKILL_HIGHLIGHTS.items() if h in by_h.index]

    @app.get("/api/anomalies/{sensor}")
    def get_anomalies(sensor: str):
        p, sensor = ready(), known(sensor)
        r = p.scores[sensor]
        pop, estimated, gaps = chart_series(p, sensor, config.IDK_POPULATION)
        return {
            "status": sensor_status(p, sensor),
            "threshold": r["threshold"], "latest_score": r["latest_score"],
            "times": [iso(t) for t in r["times"]], "scores": numbers(r["scores"], 5),
            "value_t": [iso(t) for t in pop.index], "value_y": numbers(pop.values),
            "value_estimated": estimated, "gaps": gaps,
            "flagged_ranges": _flag_ranges(r),
            "spikes": [{"t": iso(t), "y": round(float(v), 3)}
                       for t, v in p.spikes[sensor].iloc[-config.IDK_POPULATION:].dropna().items()],
            "window_hours": config.IDK_WIDTH / config.STEPS_PER_HOUR,
        }

    def _flag_ranges(r: dict) -> list:
        """Merged spans of the data covered by flagged windows (a score belongs to its window's end)."""
        if not len(r["times"]):
            return []
        width = pd.Timedelta(config.FREQ) * (config.IDK_WIDTH - 1)
        ranges = []
        for t in r["times"][r["flags"]]:
            if ranges and t - width <= ranges[-1][1]:
                ranges[-1][1] = t
            else:
                ranges.append([t - width, t])
        return [{"start": iso(a), "end": iso(b)} for a, b in ranges]

    @app.get("/api/explain/{sensor}/lags")
    def explain_lags(sensor: str):
        p, sensor = ready(), known(sensor)
        if p.models is None:
            raise HTTPException(503, detail="No trained model yet")
        return p.models.meta["explanations"][sensor]

    @app.get("/api/explain/{sensor}/local")
    def explain_local(sensor: str, horizon: int = Query(36, ge=1, le=config.HORIZON_STEPS)):
        p, sensor = ready(), known(sensor)
        if p.models is None or p.row is None:
            raise HTTPException(503, detail="No forecast available yet")
        return {"origin": iso(p.origin), "horizon": horizon,
                "target_time": iso(p.origin + horizon * pd.Timedelta(config.FREQ)),
                **forecast.explain_forecast(p.models, sensor, horizon, p.row, p.freshness[sensor]["last_value"])}

    @app.get("/api/episodes")
    def episodes():
        rows = app.state.pipeline.store.episodes()
        for r in rows:
            r["started_at"], r["last_flagged_at"] = iso(r["started_at"]), iso(r["last_flagged_at"])
            r["currently_flagged"] = bool(r["currently_flagged"])
        return rows

    class Review(BaseModel):
        note: str = ""

    @app.post("/api/episodes/{episode_id}/review")
    def review(episode_id: int, body: Review, x_approver_token: str | None = Header(default=None)):
        reviewer = authorise(x_approver_token)
        note = f"{reviewer}: {body.note.strip()}" if body.note.strip() else reviewer
        if not app.state.pipeline.store.review_episode(episode_id, note):
            raise HTTPException(404, detail="No open episode with that id")
        return {"reviewed": True}

    dist = config.ROOT_DIR / "frontend" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app


app = create_app()
