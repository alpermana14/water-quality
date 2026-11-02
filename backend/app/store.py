"""Local SQLite state: forecast log, latest scores, episodes. MySQL stays read-only."""
import json
import sqlite3
import threading

import pandas as pd

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecasts (
    origin TEXT NOT NULL, sensor TEXT NOT NULL, horizon INTEGER NOT NULL,
    target_time TEXT NOT NULL, value REAL NOT NULL, model_version TEXT NOT NULL,
    PRIMARY KEY (origin, sensor, horizon));
CREATE INDEX IF NOT EXISTS idx_forecast_target ON forecasts (sensor, target_time);
CREATE TABLE IF NOT EXISTS episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT, sensor TEXT NOT NULL, started_at TEXT NOT NULL,
    last_flagged_at TEXT NOT NULL, min_score REAL, currently_flagged INTEGER NOT NULL DEFAULT 1,
    reviewed_at TEXT, reviewed_note TEXT);
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
FORECAST_RETENTION_DAYS = 14


class Store:
    def __init__(self, path=None):
        path = path or config.APP_DB
        if str(path) != ":memory:":
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def _write(self, sql, params=()):
        with self.lock, self.conn:
            return self.conn.execute(sql, params)

    def _query(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # ----- key/value -----
    def set(self, key, value):
        self._write("INSERT INTO kv VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, json.dumps(value)))

    def get(self, key, default=None):
        rows = self._query("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    # ----- forecasts -----
    def save_forecast(self, origin, sensor, series, version):
        rows = [(str(origin), sensor, h, str(ts), float(v), version)
                for h, (ts, v) in enumerate(series.items(), start=1)]
        with self.lock, self.conn:
            self.conn.executemany("INSERT OR REPLACE INTO forecasts VALUES (?, ?, ?, ?, ?, ?)", rows)
            cutoff = pd.Timestamp(origin) - pd.Timedelta(days=FORECAST_RETENTION_DAYS)
            self.conn.execute("DELETE FROM forecasts WHERE origin < ?", (str(cutoff),))

    def forecast_log(self, sensor, since) -> pd.DataFrame:
        rows = self._query("SELECT horizon, target_time, value FROM forecasts "
                           "WHERE sensor = ? AND target_time >= ?", (sensor, str(since)))
        return pd.DataFrame(rows, columns=["horizon", "target_time", "value"])

    # ----- episodes -----
    def update_episode(self, sensor, now, flagged, score):
        """Open on the first flag; keep open until reviewed, even after scores recover."""
        now = str(now)
        rows = self._query("SELECT * FROM episodes WHERE sensor = ? AND reviewed_at IS NULL "
                           "ORDER BY id DESC LIMIT 1", (sensor,))
        if rows:
            ep = rows[0]
            if flagged:
                low = min(score, ep["min_score"]) if ep["min_score"] is not None else score
                self._write("UPDATE episodes SET last_flagged_at = ?, min_score = ?, currently_flagged = 1 "
                            "WHERE id = ?", (now, low, ep["id"]))
            elif ep["currently_flagged"]:
                self._write("UPDATE episodes SET currently_flagged = 0 WHERE id = ?", (ep["id"],))
        elif flagged:
            self._write("INSERT INTO episodes (sensor, started_at, last_flagged_at, min_score) VALUES (?, ?, ?, ?)",
                        (sensor, now, now, score))

    def episodes(self, limit=100):
        return self._query("SELECT * FROM episodes ORDER BY reviewed_at IS NOT NULL, id DESC LIMIT ?", (limit,))

    def review_episode(self, episode_id, note=""):
        cur = self._write("UPDATE episodes SET reviewed_at = ?, reviewed_note = ?, currently_flagged = 0 "
                          "WHERE id = ? AND reviewed_at IS NULL",
                          (pd.Timestamp.now("UTC").isoformat(), note, episode_id))
        return cur.rowcount > 0
