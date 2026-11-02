"""How lag features influence the forecast, using LightGBM's built-in TreeSHAP (pred_contrib).

Models predict the change from the recent level. Each contribution is in the target sensor's
units, and for any row: recent level + base value + sum(contributions) = forecast.

Neighbouring lags are nearly copies of each other, so credit is split among them arbitrarily.
The summaries therefore group lags into 1-hour buckets by default.
"""
import numpy as np

from .. import config
from .features import parse_feature


def contributions(model, row: np.ndarray) -> tuple[np.ndarray, float]:
    """Per-feature contribution and base value for a single row."""
    out = model.predict(row, pred_contrib=True, num_iteration=model.best_iteration or None)[0]
    return out[:-1], float(out[-1])


class LagAccumulator:
    """Collects mean |contribution| per input sensor and lag, per horizon, for one target sensor."""

    def __init__(self, feature_names: list[str]):
        self.feature_names = feature_names
        parsed = [parse_feature(f) for f in feature_names]
        position = {p: i for i, p in enumerate(parsed)}
        self.input_sensors = list(dict.fromkeys(s for s, _ in parsed if s))
        self.columns = {s: np.array([position[(s, k)] for k in range(config.LAG_STEPS)])
                        for s in self.input_sensors}
        self.clock = [i for i, (s, _) in enumerate(parsed) if s is None]
        self.mean_abs = {}
        self.gain = {}

    def add(self, horizon: int, model, sample) -> None:
        out = model.predict(sample, pred_contrib=True, num_iteration=model.best_iteration)
        self.mean_abs[horizon] = np.abs(out[:, :-1]).mean(axis=0)
        self.gain[horizon] = model.feature_importance("gain", iteration=model.best_iteration)

    def summary(self) -> dict:
        horizons = sorted(self.mean_abs)
        per_hour = config.STEPS_PER_HOUR
        hours = config.LAG_STEPS // per_hour
        by_sensor, gain_totals = {}, {}
        for s in self.input_sensors:
            cols = self.columns[s]
            lag_grid = np.array([self.mean_abs[h][cols] for h in horizons])  # horizon x lag
            bucket = np.add.reduceat(lag_grid, np.arange(0, config.LAG_STEPS, per_hour), axis=1)
            by_sensor[s] = {
                "by_lag": _rounded(lag_grid.mean(axis=0)),
                "by_lag_hour": _rounded(bucket.mean(axis=0)),
                "heatmap_hour": [_rounded(r) for r in bucket],
                "share": float(lag_grid.sum()),
            }
            gain_totals[s] = float(sum(self.gain[h][cols].sum() for h in horizons))

        clock = float(sum(self.mean_abs[h][self.clock].sum() for h in horizons))
        total = sum(v["share"] for v in by_sensor.values()) + clock
        for v in by_sensor.values():
            v["share"] = round(v["share"] / total, 4) if total else 0.0
        return {
            "horizons": horizons,
            "lag_hours": list(range(hours)),
            "input_sensors": by_sensor,
            "clock_share": round(clock / total, 4) if total else 0.0,
            "gain_share": _shares(gain_totals),
        }


def _rounded(values) -> list[float]:
    return [round(float(v), 5) for v in values]


def _shares(totals: dict) -> dict:
    whole = sum(totals.values())
    return {k: round(v / whole, 4) if whole else 0.0 for k, v in totals.items()}


def local_explanation(model, feature_names: list[str], row: np.ndarray, level: float, top: int = 10) -> dict:
    """Waterfall for one forecast: largest lag contributions in 1-hour buckets, the rest folded."""
    contrib, base = contributions(model, row)
    buckets: dict[tuple, float] = {}
    for name, value in zip(feature_names, contrib):
        sensor, lag = parse_feature(name)
        key = ("time_of_day", None) if sensor is None else (sensor, lag // config.STEPS_PER_HOUR)
        buckets[key] = buckets.get(key, 0.0) + float(value)

    ranked = sorted(buckets.items(), key=lambda kv: abs(kv[1]), reverse=True)
    items = [{"sensor": s, "lag_hour": h, "contribution": round(v, 5)} for (s, h), v in ranked[:top]]
    rest = sum(v for _, v in ranked[top:])
    return {
        "recent_level": round(level, 5),
        "base_value": round(base, 5),
        "prediction": round(level + base + float(contrib.sum()), 5),
        "items": items,
        "others": round(rest, 5),
    }
