"""Anonyme, aggregierte Homepage-Aufrufe je Land und Tag.

Es werden weder IP-Adressen noch Nutzer-, Geräte- oder Sitzungskennungen
abgelegt. Ein Eintrag ist ausschließlich: UTC-Tag, ISO-Ländercode, Anzahl.
"""
from __future__ import annotations

import os
import sqlite3
import time

DB_PATH = os.path.join("db", "homepage_visitors.db")


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        """CREATE TABLE IF NOT EXISTS homepage_country_daily(
        day TEXT NOT NULL,
        country TEXT NOT NULL,
        views INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(day, country))"""
    )
    return db


def _day(offset_seconds: int = 0) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(time.time() + offset_seconds))


def record(country: str) -> bool:
    code = (country or "").strip().upper()
    if len(code) != 2 or not code.isalpha() or code in {"XX", "ZZ"}:
        return False
    with _db() as db:
        db.execute(
            """INSERT INTO homepage_country_daily(day,country,views) VALUES(?,?,1)
            ON CONFLICT(day,country) DO UPDATE SET views=views+1""",
            (_day(), code),
        )
    return True


def summary() -> dict:
    today = _day()
    current_start = _day(-6 * 86400)
    previous_start = _day(-13 * 86400)
    previous_end = _day(-7 * 86400)
    with _db() as db:
        countries = [dict(row) for row in db.execute(
            "SELECT country,SUM(views) AS views FROM homepage_country_daily GROUP BY country ORDER BY views DESC"
        )]
        total = int(db.execute("SELECT COALESCE(SUM(views),0) FROM homepage_country_daily").fetchone()[0])
        today_total = int(db.execute(
            "SELECT COALESCE(SUM(views),0) FROM homepage_country_daily WHERE day=?", (today,)
        ).fetchone()[0])
        current = int(db.execute(
            "SELECT COALESCE(SUM(views),0) FROM homepage_country_daily WHERE day BETWEEN ? AND ?",
            (current_start, today),
        ).fetchone()[0])
        previous = int(db.execute(
            "SELECT COALESCE(SUM(views),0) FROM homepage_country_daily WHERE day BETWEEN ? AND ?",
            (previous_start, previous_end),
        ).fetchone()[0])
    trend = None if previous == 0 else round(((current - previous) / previous) * 100, 1)
    return {
        "total": total,
        "today": today_total,
        "trend_7d": trend,
        "countries": countries,
        "updated_at": int(time.time()),
        "metric": "homepage_page_views",
    }
