"""Train the full model set once and print the results. The app also does this nightly."""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import config  # noqa: E402
from app.data.preprocess import fill_short_gaps, remove_spikes, to_grid  # noqa: E402
from app.data.source import get_source  # noqa: E402
from app.ml import train  # noqa: E402


def main():
    source = get_source()
    start = pd.Timestamp.now("UTC").tz_localize(None) - pd.Timedelta(days=config.TRAIN_DAYS)
    clean, spikes = remove_spikes(to_grid(source.read(start=start)))
    grid = fill_short_gaps(clean)
    print(f"[data] {source.name}: {len(grid)} rows, {grid.index[0]} to {grid.index[-1]}")
    print(f"[data] single-reading spikes set aside: {spikes.notna().sum().to_dict()}")
    if not train.enough_history(grid):
        sys.exit(f"Need {config.MIN_TRAIN_DAYS} days of history")
    meta = train.train_all(grid)
    print(json.dumps({k: meta[k] for k in ("version", "models", "train_seconds", "median_rounds", "rows")}))
    for sensor, rows in meta["skill"].items():
        at = {r["horizon"]: r for r in rows}
        beat = sum(1 for r in rows if r["skill"] is not None and r["skill"] > 0)
        line = "  ".join(f"h{h}: MAE {at[h]['mae']:.4f} vs {at[h]['persistence_mae']:.4f}" for h in (1, 12, 36))
        print(f"[skill] {sensor}: {line}  beats persistence at {beat}/{len(rows)} horizons")


if __name__ == "__main__":
    main()
