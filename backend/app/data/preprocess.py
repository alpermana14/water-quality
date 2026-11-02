"""Put raw readings on a regular 5-minute grid without inventing data across long gaps."""
import numpy as np
import pandas as pd

from .. import config


def to_grid(raw: pd.DataFrame) -> pd.DataFrame:
    """Mean per 5-minute slot, ending at the latest reading; slots with no reading stay NaN."""
    if raw.empty:
        return pd.DataFrame(columns=config.SENSOR_KEYS, dtype=float)
    df = raw.sort_index()
    return df[~df.index.isna()].resample(config.FREQ).mean()


def remove_spikes(grid: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Set aside readings far from their neighbours. Returns (clean grid, the spike values).

    The neighbours are the median of the surrounding readings, so a real step is kept because
    the readings after it agree with it. The newest reading has no later neighbours yet, so it is
    judged against earlier ones only and is judged again on every tick as readings arrive.
    """
    med = grid.rolling(config.SPIKE_WINDOW, center=True, min_periods=3).median()
    residual = (grid - med).abs()
    # Median of the non-zero residuals: quantised sensors can have a MAD of exactly zero.
    scale = config.MAD_SCALE * residual.where(residual > 0).median()
    spikes = residual > config.SPIKE_K * scale
    return grid.mask(spikes), grid.where(spikes)


def fill_short_gaps(grid: pd.DataFrame) -> pd.DataFrame:
    """Linear fill of gaps up to MAX_INTERPOLATE_STEPS. Longer gaps stay fully NaN."""
    return grid.apply(_fill_series)


def _fill_series(s: pd.Series) -> pd.Series:
    isna = s.isna()
    if not isna.any():
        return s
    run_id = (isna != isna.shift()).cumsum()
    run_len = isna.groupby(run_id).transform("size")
    # Only gaps closed on both sides: a gap at the end has no reading to draw a line to.
    inside = s.ffill().notna() & s.bfill().notna()
    fillable = isna & (run_len <= config.MAX_INTERPOLATE_STEPS) & inside
    filled = s.interpolate(method="linear", limit_area="inside")
    return s.where(~fillable, filled)


def long_gaps(filled: pd.Series) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """First and last empty slot of each gap too long to fill, as shown on the charts."""
    isna = filled.isna()
    runs = (isna != isna.shift()).cumsum()[isna]
    spans = [(g.index[0], g.index[-1]) for _, g in runs.groupby(runs)]
    return [(a, b) for a, b in spans
            if (b - a) / pd.Timedelta(config.FREQ) >= config.MAX_INTERPOLATE_STEPS]


def sensor_freshness(grid: pd.DataFrame, now: pd.Timestamp | None = None) -> dict:
    """Latest reading per sensor and whether it is older than STALE_STEPS."""
    now = pd.Timestamp(now) if now is not None else grid.index[-1]
    out = {}
    for col in grid.columns:
        valid = grid[col].dropna()
        last = valid.index[-1] if len(valid) else None
        age = (now - last) / pd.Timedelta(config.FREQ) if last is not None else np.inf
        out[col] = {"last_time": last, "last_value": float(valid.iloc[-1]) if len(valid) else None,
                    "stale": bool(age >= config.STALE_STEPS)}
    return out
