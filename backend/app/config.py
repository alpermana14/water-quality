"""Settings and model constants. Everything site-specific comes from .env."""
import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env")

# ===================== SAMPLING =====================
STEP_MINUTES = 5
STEPS_PER_HOUR = 60 // STEP_MINUTES
FREQ = f"{STEP_MINUTES}min"

# ===================== FORECAST =====================
LAG_STEPS = 24 * STEPS_PER_HOUR      # 288: last 24 h
HORIZON_STEPS = 3 * STEPS_PER_HOUR   # 36: next 3 h
TRAIN_DAYS = int(os.getenv("TRAIN_DAYS", "60"))
HOLDOUT_DAYS = int(os.getenv("HOLDOUT_DAYS", "7"))
VALIDATION_DAYS = int(os.getenv("VALIDATION_DAYS", "3"))
SPLIT_MAX_SHARE = 0.15               # with short history, holdout and validation shrink to this share
MIN_TRAIN_DAYS = 3
FULL_HISTORY_DAYS = 14               # below this the dashboard says history is limited
ANCHOR_STEPS = 3                     # recent level = median of the last 3 readings
EXPLAIN_SAMPLE_ROWS = int(os.getenv("EXPLAIN_SAMPLE_ROWS", "300"))
RETRAIN_HOUR = int(os.getenv("RETRAIN_HOUR", "2"))

LGB_PARAMS = {
    "objective": "regression",
    "metric": "rmse",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_child_samples": 40,
    "feature_fraction": 0.3,
    "reg_lambda": 1.0,
    "verbosity": -1,
    "seed": 42,
    "num_threads": int(os.getenv("LGB_THREADS", "0")),
}
LGB_MAX_ROUNDS = int(os.getenv("LGB_MAX_ROUNDS", "300"))
LGB_EARLY_STOPPING = 20

# ===================== s-IDK =====================
IDK_WIDTH = 5 * STEPS_PER_HOUR       # 60: 5 h window
IDK_PSI = 2
IDK_T = int(os.getenv("IDK_T", "500"))
IDK_POPULATION = int(os.getenv("IDK_POPULATION", str(3 * 24 * STEPS_PER_HOUR)))  # 864: 3 days
HAMPEL_K = float(os.getenv("HAMPEL_K", "3"))
MAD_SCALE = 1.4826

# ===================== DATA QUALITY =====================
SPIKE_WINDOW = 7                     # readings compared around each point
SPIKE_K = float(os.getenv("SPIKE_K", "12"))
MAX_INTERPOLATE_STEPS = 6            # 30 min
MAX_WINDOW_IMPUTED = 0.2             # share of a window that may be missing
STALE_STEPS = STEPS_PER_HOUR         # no reading for 1 h

# ===================== SOURCE =====================
DATA_SOURCE = os.getenv("DATA_SOURCE", "synthetic").lower()
DB_TABLE = os.getenv("DB_TABLE", "")
DB_TIME_COLUMN = os.getenv("DB_TIME_COLUMN", "datetime")
DB_FORMAT = os.getenv("DB_FORMAT", "wide").lower()   # wide | long
DB_SENSOR_COLUMN = os.getenv("DB_SENSOR_COLUMN", "sensor")
DB_VALUE_COLUMN = os.getenv("DB_VALUE_COLUMN", "value")
DB_TIMEZONE = os.getenv("DB_TIMEZONE", "UTC")
DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "Asia/Kuala_Lumpur")


# ===================== ACCESS =====================
# Comma-separated frontend origins allowed to call the API when deployed on its own domain.
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]


def approvers() -> dict:
    """APPROVER_TOKENS=name1:token1,name2:token2. With none set, reviews are refused (fail closed)."""
    pairs = [p.split(":", 1) for p in os.getenv("APPROVER_TOKENS", "").split(",") if ":" in p]
    return {token.strip(): name.strip() for name, token in pairs if name.strip() and token.strip()}


@dataclass(frozen=True)
class Sensor:
    key: str
    label: str
    unit: str


DEFAULT_SENSORS = [
    {"key": "temperature", "label": "Temperature", "unit": "°C"},
    {"key": "ph", "label": "pH", "unit": "pH"},
    {"key": "dissolved_oxygen", "label": "Dissolved oxygen", "unit": "mg/L"},
    {"key": "turbidity", "label": "Turbidity", "unit": "NTU"},
    {"key": "conductivity", "label": "Conductivity", "unit": "µS/cm"},
]


def load_sensors() -> list[Sensor]:
    """SENSORS is a JSON list of {key, label, unit}; key is the column or sensor name in MySQL."""
    raw = os.getenv("SENSORS")
    return [Sensor(**s) for s in (json.loads(raw) if raw else DEFAULT_SENSORS)]


SENSORS = load_sensors()
SENSOR_KEYS = [s.key for s in SENSORS]

# ===================== PATHS =====================
DATA_DIR = Path(os.getenv("DATA_DIR", BACKEND_DIR / "data"))
MODEL_DIR = DATA_DIR / "models"
APP_DB = Path(os.getenv("APP_DB", DATA_DIR / "app.db"))
