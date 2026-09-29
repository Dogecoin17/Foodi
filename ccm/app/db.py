"""Tiny SQLite data layer (stdlib only)."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS pets(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, species TEXT, weight_kg REAL, daily_grams INTEGER);
CREATE TABLE IF NOT EXISTS schedule(
  id INTEGER PRIMARY KEY, minute_of_day INTEGER NOT NULL, grams INTEGER NOT NULL, days_mask INTEGER NOT NULL DEFAULT 127);
CREATE TABLE IF NOT EXISTS feed_events(
  id INTEGER PRIMARY KEY, cmd_id INTEGER, ts REAL NOT NULL, target_g INTEGER, actual_g INTEGER, source TEXT);
CREATE TABLE IF NOT EXISTS weight_readings(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, weight_g INTEGER, food_level_pct INTEGER);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY, ts REAL NOT NULL, level TEXT, message TEXT);
"""


@contextmanager
def conn():
    c = sqlite3.connect(settings.db_path)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init() -> None:
    with conn() as c:
        c.executescript(SCHEMA)


def rows(sql: str, params: tuple = ()) -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple = ()) -> int:
    with conn() as c:
        return c.execute(sql, params).lastrowid


def replace_schedule(entries: list[dict]) -> None:
    with conn() as c:
        c.execute("DELETE FROM schedule")
        c.executemany(
            "INSERT INTO schedule(minute_of_day, grams, days_mask) VALUES(?,?,?)",
            [(e["minute_of_day"], e["grams"], e["days_mask"]) for e in entries],
        )


def add_feed_event(cmd_id: int, target_g: int, actual_g: int, source: str) -> None:
    execute(
        "INSERT INTO feed_events(cmd_id, ts, target_g, actual_g, source) VALUES(?,?,?,?,?)",
        (cmd_id, time.time(), target_g, actual_g, source),
    )


def add_alert(level: str, message: str) -> None:
    execute("INSERT INTO alerts(ts, level, message) VALUES(?,?,?)", (time.time(), level, message))


def add_reading(weight_g: int, food_level_pct: int) -> None:
    execute(
        "INSERT INTO weight_readings(ts, weight_g, food_level_pct) VALUES(?,?,?)",
        (time.time(), weight_g, food_level_pct),
    )


def daily_dispensed(days: int = 30) -> list[float]:
    """Grams dispensed per day, oldest first.
    TODO (Phase 7): switch to *consumed* grams once bowl-weight meal tracking exists."""
    data = rows(
        "SELECT date(ts,'unixepoch','localtime') d, SUM(actual_g) g FROM feed_events "
        "GROUP BY d ORDER BY d DESC LIMIT ?",
        (days,),
    )
    return [float(r["g"] or 0) for r in reversed(data)]


def today_dispensed() -> int:
    r = rows("SELECT COALESCE(SUM(actual_g),0) g FROM feed_events WHERE date(ts,'unixepoch','localtime')=date('now','localtime')")
    return int(r[0]["g"])
