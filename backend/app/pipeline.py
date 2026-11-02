"""One tick: read readings, forecast, score anomalies, update episodes. Plus the retrain job."""
import threading
import traceback

import numpy as np
import pandas as pd

from . import config
from .data.preprocess import fill_short_gaps, remove_spikes, sensor_freshness, to_grid
from .data.source import get_source
from .ml import anomaly, forecast, train
from .store import Store


def utc_now() -> pd.Timestamp:
    return pd.Timestamp.now("UTC").tz_localize(None)


class Pipeline:
    def __init__(self, source=None, store=None):
        self.source = source or get_source()
        self.store = store or Store()
        self.models = None
        self.grid = None
        self.display = None    # grid with gaps up to 30 min filled, for charts and forecasting
        self.spikes = None
        self.row = None
        self.origin = None
        self.freshness = {}
        self.forecasts = {}
        self.scores = {}
        self.last_tick = None
        self.last_error = None
        self.training = False
        self.lock = threading.Lock()   # guards the swap of tick results and of the model set
        self.tick_lock = threading.Lock()
        self.load_models()

    def load_models(self) -> None:
        path = train.latest_model_dir()
        if path is not None:
            models = train.ModelSet(path)
            if models.meta["sensors"] == config.SENSOR_KEYS:
                with self.lock:
                    self.models = models

    # ----- tick -----
    def tick(self) -> None:
        """Skips rather than queues if the previous tick is still running."""
        if not self.tick_lock.acquire(blocking=False):
            return
        try:
            self._tick()
            self.last_error = None
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            self.tick_lock.release()

    def _tick(self) -> None:
        now = utc_now()
        lookback = pd.Timedelta(config.FREQ) * (config.IDK_POPULATION + config.LAG_STEPS + 12)
        raw = self.source.read(start=now - lookback)
        grid = to_grid(raw)
        if grid.empty:
            raise RuntimeError("Data source returned no readings")
        grid, spikes = remove_spikes(grid)
        display = fill_short_gaps(grid)
        freshness = sensor_freshness(grid, now)

        scores = {s: anomaly.score_sensor(grid[s], s) for s in config.SENSOR_KEYS}
        for sensor, result in scores.items():
            self._update_episodes(sensor, result)

        forecasts, origin, row = {}, None, None
        models = self.models
        if models is not None and len(grid) >= config.LAG_STEPS:
            origin, row = forecast.latest_row(display, models)
            for sensor in config.SENSOR_KEYS:
                if not freshness[sensor]["stale"]:
                    forecasts[sensor] = forecast.forecast_sensor(models, sensor, origin, row,
                                                                 freshness[sensor]["last_value"])
                    self.store.save_forecast(origin, sensor, forecasts[sensor], models.version)

        with self.lock:
            self.grid, self.display, self.spikes = grid, display, spikes
            self.freshness, self.scores = freshness, scores
            self.forecasts, self.origin, self.row = forecasts, origin, row
            self.last_tick = now

    def _update_episodes(self, sensor: str, result: dict) -> None:
        """Walk every window newer than the last one seen, so downtime and first start lose nothing."""
        if not len(result["times"]):
            return
        key = f"episodes_seen:{sensor}"
        seen = self.store.get(key)
        times, flags, scores = result["times"], result["flags"], result["scores"]
        for i in np.flatnonzero(times > pd.Timestamp(seen)) if seen else range(len(times)):
            if np.isnan(scores[i]):
                continue
            self.store.update_episode(sensor, times[i], bool(flags[i]), float(scores[i]))
        self.store.set(key, str(times[-1]))

    # ----- retrain -----
    def retrain(self) -> None:
        if self.training:
            return
        self.training = True
        try:
            start = utc_now() - pd.Timedelta(days=config.TRAIN_DAYS)
            grid = fill_short_gaps(remove_spikes(to_grid(self.source.read(start=start)))[0])
            if not train.enough_history(grid):
                self.store.set("train_blocked", f"{len(grid)} rows; need {config.MIN_TRAIN_DAYS} days")
                return
            self.store.set("train_blocked", None)
            meta = train.train_all(grid)
            models = train.ModelSet(config.MODEL_DIR / meta["version"])
            with self.lock:
                self.models = models
            train.prune_models()
            self.tick()
        except Exception as exc:
            self.last_error = f"retrain: {type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            self.training = False
