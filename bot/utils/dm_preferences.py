"""Persistent, account-wide language preferences for the bot's direct messages."""
from pathlib import Path
import sqlite3
from contextlib import contextmanager
import time

DB_PATH = 'db/dm_preferences.db'


@contextmanager
def _connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.execute('CREATE TABLE IF NOT EXISTS dm_preferences(user_id INTEGER PRIMARY KEY, language TEXT NOT NULL DEFAULT "en", offered INTEGER NOT NULL DEFAULT 0, updated_at INTEGER NOT NULL DEFAULT 0)')
    try:
        yield db
        db.commit()
    finally:
        db.close()


def language(user_id):
    with _connect() as db:
        row = db.execute('SELECT language FROM dm_preferences WHERE user_id=?', (int(user_id),)).fetchone()
    return row[0] if row and row[0] in ('en', 'de') else 'en'


def was_offered(user_id):
    with _connect() as db:
        row = db.execute('SELECT offered FROM dm_preferences WHERE user_id=?', (int(user_id),)).fetchone()
    return bool(row and row[0])


def mark_offered(user_id):
    with _connect() as db:
        db.execute('INSERT INTO dm_preferences(user_id,offered,updated_at) VALUES(?,1,?) ON CONFLICT(user_id) DO UPDATE SET offered=1,updated_at=excluded.updated_at', (int(user_id), int(time.time())))


def select(user_id, language):
    if language not in ('en', 'de'):
        raise ValueError('Unsupported DM language.')
    with _connect() as db:
        db.execute('INSERT INTO dm_preferences(user_id,language,offered,updated_at) VALUES(?,?,1,?) ON CONFLICT(user_id) DO UPDATE SET language=excluded.language,offered=1,updated_at=excluded.updated_at', (int(user_id), language, int(time.time())))
