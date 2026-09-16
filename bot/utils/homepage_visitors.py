"""Echte Homepage-Aufrufe, nach Land aggregiert und je IP 10 Minuten entprellt.

Die IP wird nur zur Wiedererkennung im kurzen Zeitfenster verwendet. In SQLite
landet ausschließlich ein zufälliges HMAC-Abbild, niemals die lesbare Adresse.
Alte Abbilder werden nach einer Stunde entfernt. Dauerhaft bleiben nur
UTC-Tag, ISO-Ländercode und Anzahl.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import sqlite3
import time
import urllib.parse
import urllib.request

DB_PATH = os.path.join("db", "homepage_visitors.db")
COOLDOWN_SECONDS = 10 * 60
RECENT_RETENTION_SECONDS = 60 * 60


def _db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript(
        """CREATE TABLE IF NOT EXISTS homepage_country_daily(
        day TEXT NOT NULL,
        country TEXT NOT NULL,
        views INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(day, country));
        CREATE TABLE IF NOT EXISTS homepage_recent_visitors(
        visitor_hash TEXT PRIMARY KEY,
        country TEXT NOT NULL,
        last_seen INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS homepage_visitor_meta(
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL);"""
    )
    return db


def _day(now: int | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now or time.time()))


def _secret(db: sqlite3.Connection) -> bytes:
    row = db.execute("SELECT value FROM homepage_visitor_meta WHERE key='hmac_secret'").fetchone()
    if row:
        return bytes.fromhex(str(row[0]))
    value = secrets.token_hex(32)
    db.execute("INSERT INTO homepage_visitor_meta(key,value) VALUES('hmac_secret',?)", (value,))
    return bytes.fromhex(value)


def _fingerprint(db: sqlite3.Connection, ip: str) -> str:
    return hmac.new(_secret(db), ip.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def lookup_country(ip: str) -> str:
    """Ermittelt nur dann extern das Land, wenn der Hosting-Proxy keines liefert."""
    try:
        address = ipaddress.ip_address((ip or "").strip())
        if not address.is_global:
            return ""
        encoded = urllib.parse.quote(str(address), safe="")
        request = urllib.request.Request(
            f"https://api.country.is/{encoded}",
            headers={"Accept": "application/json", "User-Agent": "UniversityBot-Homepage/1.0"},
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        code = str(payload.get("country") or "").upper()
        return code if len(code) == 2 and code.isalpha() else ""
    except Exception:
        return ""


def recently_seen(ip: str, now: int | None = None) -> bool:
    """Vor dem Geo-Lookup prüfen, damit Wiederholungen keine Fremd-API aufrufen."""
    if not (ip or "").strip():
        return False
    current = int(now or time.time())
    with _db() as db:
        digest = _fingerprint(db, ip)
        row = db.execute(
            "SELECT last_seen FROM homepage_recent_visitors WHERE visitor_hash=?", (digest,)
        ).fetchone()
        return bool(row and current - int(row[0]) < COOLDOWN_SECONDS)


def record(ip: str, country: str, now: int | None = None) -> bool:
    """Zählt höchstens einmal je IP innerhalb von zehn Minuten."""
    code = (country or "").strip().upper()
    address = (ip or "").strip()
    if not address or len(code) != 2 or not code.isalpha() or code in {"XX", "ZZ"}:
        return False
    current = int(now or time.time())
    with _db() as db:
        db.execute("BEGIN IMMEDIATE")
        digest = _fingerprint(db, address)
        row = db.execute(
            "SELECT last_seen FROM homepage_recent_visitors WHERE visitor_hash=?", (digest,)
        ).fetchone()
        if row and current - int(row[0]) < COOLDOWN_SECONDS:
            return False
        db.execute(
            """INSERT INTO homepage_recent_visitors(visitor_hash,country,last_seen) VALUES(?,?,?)
            ON CONFLICT(visitor_hash) DO UPDATE SET country=excluded.country,last_seen=excluded.last_seen""",
            (digest, code, current),
        )
        db.execute(
            """INSERT INTO homepage_country_daily(day,country,views) VALUES(?,?,1)
            ON CONFLICT(day,country) DO UPDATE SET views=views+1""",
            (_day(current), code),
        )
        db.execute(
            "DELETE FROM homepage_recent_visitors WHERE last_seen<?",
            (current - RECENT_RETENTION_SECONDS,),
        )
    return True


def summary() -> dict:
    now = int(time.time())
    today = _day(now)
    current_start = _day(now - 6 * 86400)
    previous_start = _day(now - 13 * 86400)
    previous_end = _day(now - 7 * 86400)
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
        "updated_at": now,
        "metric": "homepage_page_views",
        "cooldown_seconds": COOLDOWN_SECONDS,
    }
