"""Persistent global OAuth selection and dashboard session revocation."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import time

DB_PATH = 'db/dashboard_settings.db'
REQUIRED_SCOPES = ('identify', 'guilds')
OPTIONAL_SCOPES = ('connections', 'guilds.members.read')
ALL_SCOPES = ('identify', 'connections', 'guilds', 'guilds.members.read')


def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS dashboard_settings (id INTEGER PRIMARY KEY CHECK(id=1),scopes TEXT NOT NULL,updated_at INTEGER NOT NULL DEFAULT 0,updated_by TEXT NOT NULL DEFAULT "",revoked_before_ms INTEGER NOT NULL DEFAULT 0,last_logout_by TEXT NOT NULL DEFAULT "")')
    db.execute('INSERT OR IGNORE INTO dashboard_settings(id,scopes) VALUES(1,?)', (json.dumps(ALL_SCOPES),))
    db.commit()
    return db


def read():
    db = connect()
    try: row = dict(db.execute('SELECT * FROM dashboard_settings WHERE id=1').fetchone())
    finally: db.close()
    selected = set(json.loads(row.pop('scopes'))) | set(REQUIRED_SCOPES)
    row.pop('id')
    return {**row, 'scopes': [scope for scope in ALL_SCOPES if scope in selected],
            'required_scopes': list(REQUIRED_SCOPES), 'optional_scopes': list(OPTIONAL_SCOPES)}


def save(scopes, actor: str):
    if not isinstance(scopes, list) or any(not isinstance(scope, str) or scope not in ALL_SCOPES for scope in scopes):
        raise ValueError('invalid_scopes')
    if not set(REQUIRED_SCOPES) <= set(scopes): raise ValueError('required_scopes')
    selected = [scope for scope in ALL_SCOPES if scope in scopes]
    db = connect()
    try:
        with db:
            db.execute('UPDATE dashboard_settings SET scopes=?,updated_at=?,updated_by=? WHERE id=1',
                       (json.dumps(selected), int(time.time()), actor))
    finally: db.close()
    return read()


def revoke_everyone(actor: str):
    db = connect()
    try:
        with db:
            db.execute('UPDATE dashboard_settings SET revoked_before_ms=MAX(revoked_before_ms+1,?),last_logout_by=? WHERE id=1',
                       (int(time.time() * 1000), actor))
    finally: db.close()
    return read()['revoked_before_ms']


def revoked_before():
    return int(read()['revoked_before_ms'])
