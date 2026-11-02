"""Stand-in source for building and testing before MySQL is connected. It is not measured data.

Daily cycles drive linked sensors (temperature -> dissolved oxygen, rain -> turbidity and
conductivity), so cross-sensor lags have something real to find. Known anomalies are planted
inside the last 3 days and listed in ANOMALIES so tests can check the detector against them.
"""
import numpy as np
import pandas as pd

from .. import config
from .source import DataSource

DEFAULT_DAYS = 75
FUTURE_DAYS = 7
SEED = 7


def generate(end: pd.Timestamp, days: int = DEFAULT_DAYS, inject: bool = True, seed: int = SEED,
             plant_end: pd.Timestamp | None = None):
    """Readings ending at `end`, and the planted anomalies as (sensor, kind, start, stop).

    Anomalies are placed relative to plant_end, which defaults to `end`.
    """
    rng = np.random.default_rng(seed)
    end = pd.Timestamp(end).floor(config.FREQ)
    n = days * 24 * config.STEPS_PER_HOUR
    index = pd.date_range(end=end, periods=n, freq=config.FREQ)
    hours = index.hour + index.minute / 60
    day = 2 * np.pi * (hours - 9) / 24

    def ar1(phi, sigma):
        noise = rng.normal(0, sigma, n)
        out = np.zeros(n)
        for i in range(1, n):
            out[i] = phi * out[i - 1] + noise[i]
        return out

    seasonal = 0.8 * np.sin(2 * np.pi * np.arange(n) / (n * 2))
    temperature = 28 + 1.6 * np.sin(day) + seasonal + ar1(0.97, 0.03)

    # Rain pulses with a sharp rise and slow decay, up to one every few days.
    rain = np.zeros(n)
    for start in np.flatnonzero(rng.random(n) < 1 / (4 * 288)):
        size = rng.uniform(5, 25)
        tail = n - start
        rain[start:] += size * np.exp(-np.arange(tail) / 40.0)

    # Oxygen solubility falls with temperature, about 2 h behind it.
    dissolved_oxygen = 7.4 - 0.45 * (np.roll(temperature, 24) - 28) + 0.4 * np.sin(day) + ar1(0.95, 0.015)
    ph = 7.3 + 0.12 * np.sin(day - 0.5) - 0.006 * rain + ar1(0.96, 0.004)
    turbidity = 6 + 0.8 * rain + ar1(0.9, 0.12)
    conductivity = 420 - 3.0 * rain + 8 * np.sin(day + 1) + ar1(0.97, 0.5)

    df = pd.DataFrame({
        "temperature": temperature, "ph": ph, "dissolved_oxygen": dissolved_oxygen,
        "turbidity": np.clip(turbidity, 0.1, None), "conductivity": conductivity,
    }, index=index)

    anomalies = []
    if inject:
        anomalies = _inject(df, plant_end if plant_end is not None else end)
    return df.round(3).reindex(columns=config.SENSOR_KEYS), anomalies


def _inject(df, plant_end):
    n = int(df.index.get_indexer([plant_end.floor(config.FREQ)])[0]) + 1
    planted = []

    def at(hours_ago, length_h):
        start = n - int(hours_ago * config.STEPS_PER_HOUR)
        return start, start + int(length_h * config.STEPS_PER_HOUR)

    # A step in pH for 8 h (e.g. a discharge), inside the population.
    a, b = at(30, 8)
    df.iloc[a:b, df.columns.get_loc("ph")] -= 0.9
    planted.append(("ph", "step", df.index[a], df.index[b]))

    # Conductivity spike for 6 h.
    a, b = at(14, 6)
    df.iloc[a:b, df.columns.get_loc("conductivity")] += 180
    planted.append(("conductivity", "step", df.index[a], df.index[b]))

    # Dissolved oxygen sensor reads stuck for 7 h.
    a, b = at(48, 7)
    col = df.columns.get_loc("dissolved_oxygen")
    df.iloc[a:b, col] = df.iloc[a, col]
    planted.append(("dissolved_oxygen", "stuck", df.index[a], df.index[b]))

    # Turbidity logger offline for 90 minutes: a real gap, not a value change.
    a, b = at(4, 1.5)
    df.iloc[a:b, df.columns.get_loc("turbidity")] = np.nan
    planted.append(("turbidity", "gap", df.index[a], df.index[b]))
    return planted


class SyntheticSource(DataSource):
    name = "synthetic"

    def __init__(self, days: int = DEFAULT_DAYS):
        self.days = days
        self.series = None
        self.series_end = None

    def read(self, start=None):
        now = pd.Timestamp.now("UTC").tz_localize(None).floor(config.FREQ)
        if self.series is None or now > self.series_end:
            # One series reaching past the clock, revealed as time passes, so readings stay stable.
            anchor = now.floor("D")
            self.series_end = anchor + pd.Timedelta(days=FUTURE_DAYS)
            self.series, _ = generate(end=self.series_end, days=self.days + FUTURE_DAYS, plant_end=anchor)
        df = self.series[self.series.index <= now]
        return df if start is None else df[df.index >= start]
