"""Owner-only step-up authentication and a minimal, expiring OAuth snapshot.

OAuth credentials are never stored here. Grants are hashed, bound to the
dashboard login, and invalidated when the authenticator key changes.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import struct
import time
import uuid

DB_PATH = 'db/owner_louckup.db'
GRANT_SECONDS = 600
SNAPSHOT_SECONDS = 30 * 86400


def owner_ids() -> set[str]:
    # No ADMIN_IDS, database roles, application-team membership or fallback.
    return {x.strip() for x in os.getenv('OWNER_IDS', '').split(',') if valid_id(x.strip())}


def valid_id(value) -> bool:
    return bool(re.fullmatch(r'[0-9]{17,20}', str(value)) and 0 < int(value) < 2**64)


def authenticator_key() -> bytes | None:
    value = re.sub(r'\s+', '', os.getenv('OWNER_LOUCKUP_TOTP_SECRET', '')).upper().rstrip('=')
    if not re.fullmatch(r'[A-Z2-7]{32,128}', value):
        return None
    try:
        key = base64.b32decode(value + '=' * (-len(value) % 8))
        return key if len(key) >= 20 else None
    except ValueError:
        return None


def totp(key: bytes, step: int) -> str:
    digest = hmac.new(key, struct.pack('>Q', step), hashlib.sha1).digest()
    offset = digest[-1] & 15
    number = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7fffffff
    return f'{number % 1_000_000:06d}'


@contextmanager
def connect():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS louckup_security (
          actor TEXT PRIMARY KEY, fingerprint TEXT, last_step INTEGER DEFAULT -1,
          failures INTEGER DEFAULT 0, window_start INTEGER DEFAULT 0, blocked_until INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS louckup_grants (
          hash TEXT PRIMARY KEY, actor TEXT, binding TEXT, fingerprint TEXT, expires INTEGER);
        CREATE TABLE IF NOT EXISTS louckup_oauth (
          user_id TEXT PRIMARY KEY, profile TEXT, guilds TEXT, scopes TEXT,
          source TEXT, captured INTEGER, expires INTEGER, complete INTEGER);
        CREATE TABLE IF NOT EXISTS louckup_audit (
          id INTEGER PRIMARY KEY AUTOINCREMENT, actor TEXT, target TEXT,
          event TEXT, created INTEGER);
    ''')
    # Serialize the additive migration, including deployments with old snapshots.
    db.execute('BEGIN IMMEDIATE')
    columns = {row[1] for row in db.execute('PRAGMA table_info(louckup_oauth)')}
    for name, declaration in (
        ('connections', "TEXT NOT NULL DEFAULT '[]'"),
        ('memberships', "TEXT NOT NULL DEFAULT '[]'"),
        ('connections_complete', 'INTEGER NOT NULL DEFAULT 0'),
        ('memberships_complete', 'INTEGER NOT NULL DEFAULT 0'),
        ('collection_status', "TEXT NOT NULL DEFAULT 'ready'"),
        ('capture_id', "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in columns:
            db.execute(f'ALTER TABLE louckup_oauth ADD COLUMN {name} {declaration}')
    db.commit()
    try:
        now = int(time.time())
        db.execute('DELETE FROM louckup_grants WHERE expires<=?', (now,))
        db.execute('DELETE FROM louckup_oauth WHERE expires<=?', (now,))
        db.execute('DELETE FROM louckup_audit WHERE created<?', (now - 90 * 86400,))
        db.commit()
        yield db
        db.commit()
    finally:
        db.close()


class AuthError(Exception):
    def __init__(self, status: int, reason: str, retry: int = 0):
        self.status, self.reason, self.retry = status, reason, retry


def purge_expired():
    with connect():
        pass


def unlock(actor: str, binding: str, code: str) -> dict:
    key = authenticator_key()
    if key is None:
        raise AuthError(503, 'not_configured')
    now = int(time.time())
    fingerprint = hashlib.sha256(key).hexdigest()
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO louckup_security(actor) VALUES(?)', (actor,))
        row = dict(db.execute('SELECT * FROM louckup_security WHERE actor=?', (actor,)).fetchone())
        if row['blocked_until'] > now:
            raise AuthError(429, 'rate_limited', row['blocked_until'] - now)
        if row['fingerprint'] != fingerprint:
            row.update(last_step=-1, failures=0, window_start=now)
        if now - row['window_start'] >= 300:
            row.update(failures=0, window_start=now)
        step = now // 30
        matched = None
        if re.fullmatch(r'[0-9]{6}', str(code)):
            matched = next((candidate for candidate in (step, step - 1, step + 1)
                            if candidate >= 0 and hmac.compare_digest(str(code), totp(key, candidate))), None)
        if matched is None or matched <= row['last_step']:
            failures = row['failures'] + 1
            blocked = now + 300 if failures >= 5 else 0
            db.execute('UPDATE louckup_security SET fingerprint=?,last_step=?,failures=?,window_start=?,blocked_until=? WHERE actor=?',
                       (fingerprint, row['last_step'], failures, row['window_start'], blocked, actor))
            db.execute('INSERT INTO louckup_audit(actor,target,event,created) VALUES(?,?,?,?)', (actor, '', 'unlock_denied', now))
            db.commit()  # A failed request must still retain its rate limit.
            raise AuthError(429 if blocked else 401, 'rate_limited' if blocked else 'invalid_code', 300 if blocked else 0)
        db.execute('UPDATE louckup_security SET fingerprint=?,last_step=?,failures=0,window_start=?,blocked_until=0 WHERE actor=?',
                   (fingerprint, matched, now, actor))
        grant = secrets.token_urlsafe(32)
        db.execute('INSERT INTO louckup_grants VALUES(?,?,?,?,?)',
                   (hashlib.sha256(grant.encode()).hexdigest(), actor, binding, fingerprint, now + GRANT_SECONDS))
        db.execute('INSERT INTO louckup_audit(actor,target,event,created) VALUES(?,?,?,?)', (actor, '', 'unlocked', now))
    return {'grant': grant, 'expires_at': now + GRANT_SECONDS}


def grant_expires(actor: str, binding: str, grant: str) -> int:
    key = authenticator_key()
    if not key or not grant or not binding:
        return 0
    with connect() as db:
        row = db.execute('SELECT * FROM louckup_grants WHERE hash=? AND actor=? AND binding=?',
                         (hashlib.sha256(grant.encode()).hexdigest(), actor, binding)).fetchone()
    return int(row['expires']) if row and row['fingerprint'] == hashlib.sha256(key).hexdigest() and row['expires'] > time.time() else 0


def lock(grant: str):
    with connect() as db:
        db.execute('DELETE FROM louckup_grants WHERE hash=?', (hashlib.sha256(grant.encode()).hexdigest(),))


def record_lookup(actor: str, target: str):
    with connect() as db:
        db.execute('INSERT INTO louckup_audit(actor,target,event,created) VALUES(?,?,?,?)', (actor, target, 'lookup', int(time.time())))


def capture_oauth(data: dict, *, capture_id: str | None = None):
    user = data.get('user') or {}
    uid = str(user.get('id', ''))
    scopes = set(str(data.get('scope', '')).split()) & {'identify', 'connections', 'guilds', 'guilds.members.read', 'guilds.join'}
    if not valid_id(uid) or not {'identify', 'guilds'} <= scopes:
        raise ValueError('Invalid OAuth snapshot')
    profile = {'id': uid}
    for field in ('username', 'global_name', 'discriminator', 'avatar', 'banner'):
        if isinstance(user.get(field), str): profile[field] = user[field][:128]
    for field in ('public_flags', 'accent_color'):
        if type(user.get(field)) is int: profile[field] = user[field]
    if type(user.get('bot')) is bool: profile['bot'] = user['bot']
    guilds, seen = [], set()
    for guild in (data.get('guilds') or [])[:1000]:
        if not isinstance(guild, dict) or not valid_id(guild.get('id')) or str(guild['id']) in seen: continue
        gid = str(guild['id']); seen.add(gid)
        permissions = str(guild.get('permissions', '0'))
        guilds.append({'id': gid, 'name': str(guild.get('name') or gid)[:100],
                       'icon': guild.get('icon') if isinstance(guild.get('icon'), str) and re.fullmatch(r'[a-zA-Z0-9_]{1,128}', guild['icon']) else None,
                       'owner': guild.get('owner') is True,
                       'permissions': permissions if re.fullmatch(r'[0-9]{1,24}', permissions) else '0'})
    connections = []
    if 'connections' in scopes:
        for item in (data.get('connections') or [])[:100]:
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not isinstance(item.get('type'), str): continue
            connection = {field: item[field][:128] for field in ('id', 'name', 'type') if isinstance(item.get(field), str)}
            for field in ('verified', 'friend_sync', 'show_activity', 'two_way_link'):
                if type(item.get(field)) is bool: connection[field] = item[field]
            if item.get('visibility') in (0, 1): connection['visibility'] = int(item['visibility'])
            connections.append(connection)
    memberships, member_seen = [], set()
    if 'guilds.members.read' in scopes:
        for item in (data.get('memberships') or [])[:1000]:
            if not isinstance(item, dict) or str(item.get('guild_id')) not in seen or str(item['guild_id']) in member_seen: continue
            gid = str(item['guild_id']); member_seen.add(gid)
            member = {'guild_id': gid, 'roles': [str(role) for role in (item.get('roles') or [])[:250] if valid_id(role)]}
            for field in ('nick', 'avatar', 'joined_at', 'premium_since', 'communication_disabled_until'):
                if isinstance(item.get(field), str): member[field] = item[field][:128]
            for field in ('pending', 'deaf', 'mute'):
                if type(item.get(field)) is bool: member[field] = item[field]
            if type(item.get('flags')) is int: member['flags'] = item['flags']
            memberships.append(member)
    status = data.get('collection_status')
    status = status if status in ('collecting', 'ready', 'partial') else 'ready'
    values = (json.dumps(profile), json.dumps(guilds), json.dumps(sorted(scopes)), json.dumps(connections),
              json.dumps(memberships), int('connections' in scopes and data.get('connections_complete') is True),
              int('guilds.members.read' in scopes and data.get('memberships_complete') is True),
              int(data.get('complete') is True), status)
    now = int(time.time())
    with connect() as db:
        if capture_id is not None:
            # An older collector must not overwrite a new consent or recreate erased data.
            db.execute('UPDATE louckup_oauth SET profile=?,guilds=?,scopes=?,connections=?,memberships=?,connections_complete=?,memberships_complete=?,complete=?,collection_status=? WHERE user_id=? AND capture_id=? AND expires>?',
                       (*values, uid, capture_id, now))
        else:
            capture_id = uuid.uuid4().hex
            db.execute('INSERT OR REPLACE INTO louckup_oauth (profile,guilds,scopes,connections,memberships,connections_complete,memberships_complete,complete,collection_status,user_id,source,captured,expires,capture_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (*values, uid, 'verification' if data.get('source') == 'verification' else 'dashboard', now, now + SNAPSHOT_SECONDS, capture_id))
    return capture_id


def oauth_snapshot(user_id: str) -> dict | None:
    with connect() as db:
        row = db.execute('SELECT * FROM louckup_oauth WHERE user_id=?', (user_id,)).fetchone()
    if not row: return None
    return {'profile': json.loads(row['profile']), 'guilds': json.loads(row['guilds']),
            'connections': json.loads(row['connections']), 'memberships': json.loads(row['memberships']),
            'connections_complete': bool(row['connections_complete']), 'memberships_complete': bool(row['memberships_complete']),
            'collection_status': 'partial' if row['collection_status'] == 'collecting' and int(time.time()) - row['captured'] > 180 else row['collection_status'],
            'scopes': json.loads(row['scopes']), 'source': row['source'], 'captured_at': row['captured'],
            'expires_at': row['expires'], 'complete': bool(row['complete'])}


def login_summary(user_id: str) -> dict | None:
    path = Path('db/admin_config.db')
    if not path.exists(): return None
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) if path.is_absolute() else sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    try:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT first_seen,last_seen,login_count FROM dashboard_logins WHERE user_id=?', (user_id,)).fetchone()
        return dict(row) if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        db.close()
