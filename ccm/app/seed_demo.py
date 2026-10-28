"""Seed the database with a realistic 30-day history for demos and development.

Run from the ccm/ folder:  python -m app.seed_demo [--force]

The pattern is deliberate: ~28 normal days, then 2 days where the pet eats
about 40% less - enough for analytics.detect_anomalies to raise an insight.
"""
from __future__ import annotations

import random
import sys
import time

from . import db

DAYS = 30
NORMAL_DAILY_G = 85
LOW_DAILY_G = 48  # ~40% below normal -> triggers the anomaly insight
LOW_DAYS = 2  # trailing days at the low level
MEALS = [(8 * 60, 40), (18 * 60, 45)]  # 08:00 / 18:00, grams


def seed(force: bool = False) -> None:
    db.init()
    if db.rows("SELECT id FROM feed_events LIMIT 1") and not force:
        print("feed_events already has data; use --force to reseed")
        return

    rng = random.Random(42)
    now = time.time()
    today_start = now - (now % 86400)  # good enough for a demo

    with db.conn() as c:
        if force:
            for table in ("feed_events", "pets", "schedule", "alerts", "weight_readings"):
                c.execute(f"DELETE FROM {table}")

        c.execute(
            "INSERT INTO pets(name, species, weight_kg, daily_grams) VALUES(?,?,?,?)",
            ("Luna", "cat", 4.2, NORMAL_DAILY_G),
        )
        for minute, grams in MEALS:
            c.execute(
                "INSERT INTO schedule(minute_of_day, grams, days_mask) VALUES(?,?,127)",
                (minute, grams),
            )

        cmd = 0
        for day in range(DAYS - 1, -1, -1):  # oldest first
            low = day < LOW_DAYS
            daily = LOW_DAILY_G if low else NORMAL_DAILY_G
            for minute, grams in MEALS:
                portion = round(grams * (daily / NORMAL_DAILY_G) * rng.uniform(0.9, 1.1))
                if portion <= 0:
                    continue
                cmd += 1
                ts = today_start - day * 86400 + minute * 60 + rng.randint(0, 300)
                c.execute(
                    "INSERT INTO feed_events(cmd_id, ts, target_g, actual_g, source) VALUES(?,?,?,?,?)",
                    (0x80000000 | cmd, ts, portion, portion + rng.randint(-2, 2), "schedule"),
                )

    print(f"seeded {DAYS} days ({cmd} meals); last {LOW_DAYS} days at ~{LOW_DAILY_G} g/day")


if __name__ == "__main__":
    seed(force="--force" in sys.argv)
