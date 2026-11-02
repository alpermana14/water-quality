"""s-IDK scoring per sensor, the Hampel alarm rule, and shift episodes.

s-IDK returns one similarity per sliding window and only ranks them: low means unlike the rest.
Following machine_status.py in the reference repo, a window is flagged when its similarity falls
below median - K * 1.4826 * MAD of the population, and a first detection stays open as an episode
until reviewed. A lasting change turns into the majority of the population after about half of
it, its scores then recover, and only the open episode still shows it happened.
"""
import random
import sys

import numpy as np
import pandas as pd

from .. import config

sys.path.insert(0, str(config.BACKEND_DIR / "third_party" / "idk"))
from IDK_square_sliding import IDK_square_sliding  # noqa: E402

FLAGGED = "flagged"
NORMAL = "normal"
WARMING_UP = "warming_up"
FLATLINE = "flatline"
UNDETERMINED = "undetermined"
INSUFFICIENT = "insufficient_data"


def window_scores(values: np.ndarray, seed_key: str) -> np.ndarray:
    """Scores for a gap-free population, one per window ending at each point from WIDTH-1 on."""
    # Z-scored because IK_inne_fm masks its diagonal with 99999999 on squared distances, a value
    # sensors in large units can reach. Scaling is linear, so it does not change the ranking.
    X = ((values - values.mean()) / values.std()).reshape(-1, 1)
    # The stdlib generator is what IDK.py samples from; seeding makes each run reproducible.
    random.seed(seed_key)
    return np.asarray(IDK_square_sliding(X, width=config.IDK_WIDTH, psi1=config.IDK_PSI,
                                         psi2=config.IDK_PSI, t=config.IDK_T)).ravel()


def hampel_threshold(scores: np.ndarray) -> tuple[float, float, float]:
    s = scores[np.isfinite(scores)]
    med = float(np.median(s))
    mad = float(np.median(np.abs(s - med)))
    return med - config.HAMPEL_K * config.MAD_SCALE * mad, med, mad


def score_sensor(series: pd.Series, sensor: str) -> dict:
    """Score the latest population of one sensor. `series` is the grid before any gap filling."""
    pop = series.iloc[-config.IDK_POPULATION:]
    empty = {"status": WARMING_UP, "times": [], "scores": [], "flags": [], "threshold": None,
             "latest_score": None, "latest_flag": False, "population": len(pop)}
    if len(pop) < config.IDK_POPULATION:
        return empty

    missing = pop.isna().to_numpy()
    window_missing = pd.Series(missing).rolling(config.IDK_WIDTH).mean().to_numpy()[config.IDK_WIDTH - 1:]
    usable = window_missing <= config.MAX_WINDOW_IMPUTED
    times = pop.index[config.IDK_WIDTH - 1:]

    # s-IDK cannot take NaN. Bridge long gaps for scoring only; those windows are excluded below.
    values = pop.interpolate(limit_direction="both").to_numpy(dtype=float)
    if np.isnan(values).any():
        return {**empty, "status": INSUFFICIENT}
    if values.std() == 0:
        return {**empty, "status": FLATLINE}

    seed_key = f"{sensor}-{pop.index[-1]}"
    scores = window_scores(values, seed_key)
    scores[~usable] = np.nan

    latest_usable = bool(usable[-1])
    if not usable.any():
        return {**empty, "status": INSUFFICIENT}

    threshold, median, mad = hampel_threshold(scores)
    result = {"times": times, "scores": scores, "threshold": None, "median": median, "mad": mad,
              "latest_score": None if np.isnan(scores[-1]) else float(scores[-1]),
              "population": len(pop)}
    if mad == 0:
        # More than half the windows score the same: the median is not a meaningful boundary.
        return {**result, "status": UNDETERMINED, "flags": np.zeros(len(scores), bool), "latest_flag": False}

    # A sensor stuck at a normal value looks unremarkable to a distribution method, so s-IDK misses
    # it. Measured readings that do not change for a whole window are flagged directly.
    measured = np.lib.stride_tricks.sliding_window_view(pop.to_numpy(dtype=float), config.IDK_WIDTH)
    stuck = (measured.max(axis=1) - measured.min(axis=1)) == 0
    flags = (np.nan_to_num(scores, nan=np.inf) < threshold) | stuck
    if stuck[-1]:
        status = FLATLINE
    else:
        status = (FLAGGED if flags[-1] else NORMAL) if latest_usable else INSUFFICIENT
    return {**result, "status": status, "threshold": threshold, "flags": flags, "stuck": stuck,
            "latest_flag": bool(flags[-1])}
