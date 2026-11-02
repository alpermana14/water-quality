"""Direct forecasting: one LightGBM model per sensor per horizon.

Chronological split, oldest to newest: train | validation (early stopping) | holdout (backtest).
Rows are purged where a target would reach into the next block, so no future value is used.

Models learn the change from the recent level, not the absolute value. Trees cannot predict
beyond the range they were trained on, so absolute targets fail when a sensor drifts into new
territory; with a change target, forecast = recent level + predicted change.
"""
import json
import shutil
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from .. import config
from . import explain
from .features import anchor, build_features, build_target


def split_rows(index: pd.DatetimeIndex):
    """Boolean masks for train, validation and holdout, with a horizon-long purge between them."""
    end = index[-1]
    purge = pd.Timedelta(config.FREQ) * config.HORIZON_STEPS
    cap = (end - index[0]) * config.SPLIT_MAX_SHARE
    hold_start = end - min(pd.Timedelta(days=config.HOLDOUT_DAYS), cap)
    val_start = hold_start - min(pd.Timedelta(days=config.VALIDATION_DAYS), cap)
    train = index < val_start - purge
    val = (index >= val_start) & (index < hold_start - purge)
    hold = index >= hold_start
    return train, val, hold


def enough_history(grid: pd.DataFrame) -> bool:
    return len(grid) >= config.MIN_TRAIN_DAYS * 24 * config.STEPS_PER_HOUR


def _fit(X, y, tr, va):
    use_tr = tr & y.notna().to_numpy()
    use_va = va & y.notna().to_numpy()
    dtrain = lgb.Dataset(X[use_tr], y[use_tr], free_raw_data=True)
    dval = lgb.Dataset(X[use_va], y[use_va], reference=dtrain, free_raw_data=True)
    return lgb.train(config.LGB_PARAMS, dtrain, num_boost_round=config.LGB_MAX_ROUNDS,
                     valid_sets=[dval], callbacks=[lgb.early_stopping(config.LGB_EARLY_STOPPING, verbose=False)])


def _skill_row(y, pred, base):
    ok = y.notna().to_numpy() & ~np.isnan(pred) & ~np.isnan(base)
    if not ok.any():
        return {"mae": None, "rmse": None, "persistence_mae": None, "skill": None, "n": 0}
    err, err_base = pred[ok] - y[ok], base[ok] - y[ok]
    mae, mae_base = float(np.abs(err).mean()), float(np.abs(err_base).mean())
    return {"mae": mae, "rmse": float(np.sqrt((err ** 2).mean())), "persistence_mae": mae_base,
            "skill": 1 - mae / mae_base if mae_base > 0 else None, "n": int(ok.sum())}


def train_all(grid: pd.DataFrame, version: str | None = None, sensors=None, progress=print) -> dict:
    """Train every sensor and horizon, and save the set to a new folder. Returns its metadata."""
    version = version or pd.Timestamp.now("UTC").strftime("%Y%m%dT%H%M%SZ")
    started = time.time()
    X = build_features(grid)
    tr, va, ho = split_rows(X.index)
    sensors = sensors or list(grid.columns)
    sample = X[ho].iloc[np.linspace(0, ho.sum() - 1, min(config.EXPLAIN_SAMPLE_ROWS, int(ho.sum()))).astype(int)]

    tmp = config.MODEL_DIR / f".{version}.tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    skill, rounds = {}, []
    explain_acc = {}
    shape = (len(sensors), config.HORIZON_STEPS, int(ho.sum()))
    held_forecast, held_actual = np.full(shape, np.nan), np.full(shape, np.nan)
    held_persistence = np.full((len(sensors), int(ho.sum())), np.nan)
    for s_i, sensor in enumerate(sensors):
        skill[sensor] = []
        explain_acc[sensor] = explain.LagAccumulator(list(X.columns))
        latest = X[f"{sensor}_lag0"].to_numpy()
        level = anchor(X, sensor)
        for h in range(1, config.HORIZON_STEPS + 1):
            y = build_target(grid, sensor, h).reindex(X.index)
            model = _fit(X, y - level, tr, va)
            rounds.append(model.best_iteration)
            model.save_model(tmp / f"{sensor}__h{h:02d}.txt")
            pred = level[ho].to_numpy() + model.predict(X[ho], num_iteration=model.best_iteration)
            skill[sensor].append({"horizon": h, **_skill_row(y[ho], pred, latest[ho])})
            held_forecast[s_i, h - 1], held_actual[s_i, h - 1] = pred, y[ho].to_numpy()
            held_persistence[s_i] = latest[ho]
            explain_acc[sensor].add(h, model, sample)
        progress(f"[train] {sensor} done ({s_i + 1}/{len(sensors)}, {time.time() - started:.0f} s)")

    explanations = {s: a.summary() for s, a in explain_acc.items()}
    meta = {
        "version": version,
        "trained_at": pd.Timestamp.now("UTC").isoformat(),
        "data_end": str(grid.index[-1]),
        "sensors": sensors,
        "feature_names": list(X.columns),
        "rows": {"train": int(tr.sum()), "validation": int(va.sum()), "holdout": int(ho.sum())},
        "history_days": round(len(grid) / (24 * config.STEPS_PER_HOUR), 1),
        "holdout_hours": round(int(ho.sum()) / config.STEPS_PER_HOUR, 1),
        "models": len(sensors) * config.HORIZON_STEPS,
        "train_seconds": round(time.time() - started, 1),
        "median_rounds": int(np.median(rounds)),
        "skill": skill,
        "explanations": explanations,
    }
    (tmp / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
    np.savez_compressed(tmp / "validation.npz", origins=np.array(X.index[ho].strftime("%Y-%m-%d %H:%M:%S"), dtype="U19"),
                        forecast=held_forecast, actual=held_actual, persistence=held_persistence)
    final = config.MODEL_DIR / version
    if final.exists():
        shutil.rmtree(final)
    tmp.rename(final)
    return meta


class ModelSet:
    """A complete saved set of models, loaded once and then only read."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.meta = json.loads((self.path / "meta.json").read_text(encoding="utf-8"))
        self.boosters = {
            (s, h): lgb.Booster(model_file=str(self.path / f"{s}__h{h:02d}.txt"))
            for s in self.meta["sensors"] for h in range(1, config.HORIZON_STEPS + 1)
        }
        held = self.path / "validation.npz"
        self.validation = dict(np.load(held)) if held.exists() else None

    @property
    def version(self):
        return self.meta["version"]


def latest_model_dir() -> Path | None:
    if not config.MODEL_DIR.exists():
        return None
    done = [p for p in config.MODEL_DIR.iterdir() if p.is_dir() and (p / "meta.json").exists()]
    return max(done, key=lambda p: p.name) if done else None


def prune_models(keep: int = 2) -> None:
    done = sorted((p for p in config.MODEL_DIR.iterdir() if p.is_dir() and not p.name.startswith(".")),
                  key=lambda p: p.name)
    for old in done[:-keep]:
        shutil.rmtree(old, ignore_errors=True)
