# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Licence keys for the template bot's premium features.

The shape of it:

  1. Someone buys premium in Discord.
  2. A team member runs /key on the support server. That mints a
     16-character key with a chosen duration and DMs it to them.
  3. The buyer types the key into the dashboard. It is bound to *their*
     Discord account at that moment and cannot be moved.
  4. The template bot asks us "does user X have premium?" and gets a
     yes/no plus an expiry.

Keys are stored hashed, never in the clear. A leaked database still
cannot be used to activate anything, the same reason passwords are not
stored plainly. The formatted key exists exactly once: in the DM.

The alphabet deliberately drops I, O, 0, 1 and similar. People retype
these from a phone screen, and "was that an O or a zero" is the kind of
detail that turns into a support ticket.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.path.join("db", "premium.db")

# No I, O, 0, 1, U — visually ambiguous or awkward when read aloud.
ALPHABET = "ABCDEFGHJKLMNPQRSTVWXYZ23456789"

KEY_LENGTH = 16
GROUP_SIZE = 4

# Peppering the hash: a stolen database alone is not enough to check
# guesses offline without also stealing the environment.
PEPPER_ENV = "PREMIUM_KEY_PEPPER"


def _pepper() -> bytes:
    return os.getenv(PEPPER_ENV, "").encode("utf-8")


def normalise(key: str) -> str:
    """
    Strip the formatting a human adds.

    People paste "abcd-efgh ijkl mnop" with lowercase, spaces and dashes
    in whatever combination their keyboard produced. All of it means the
    same key.
    """
    return "".join(ch for ch in (key or "").upper() if ch in ALPHABET)


def format_key(raw: str) -> str:
    """Group into blocks of four so it can be read out loud."""
    raw = normalise(raw)
    return "-".join(raw[i:i + GROUP_SIZE] for i in range(0, len(raw), GROUP_SIZE))


def hash_key(key: str) -> str:
    """
    One-way hash of a key.

    HMAC-SHA256 rather than a bare digest so the pepper actually keys
    the function instead of being a prefix that length-extends.
    """
    raw = normalise(key).encode("utf-8")
    return hmac.new(_pepper(), raw, hashlib.sha256).hexdigest()


def generate_key() -> str:
    """A fresh key, formatted. secrets, not random: this guards money."""
    raw = "".join(secrets.choice(ALPHABET) for _ in range(KEY_LENGTH))
    return format_key(raw)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    """Create the table. Safe to call on every access."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS premium_keys (
                key_hash    TEXT PRIMARY KEY,
                product     TEXT NOT NULL DEFAULT 'template_bot',
                duration    INTEGER NOT NULL DEFAULT 0,
                created_at  INTEGER NOT NULL,
                created_by  TEXT NOT NULL,
                note        TEXT NOT NULL DEFAULT '',
                redeemed_by TEXT,
                redeemed_at INTEGER,
                expires_at  INTEGER,
                revoked     INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS premium_keys_user "
            "ON premium_keys (redeemed_by)"
        )


def create_key(created_by: int | str, duration_days: int = 0,
               product: str = "template_bot", note: str = "") -> dict[str, Any]:
    """
    Mint a key.

    duration_days of 0 means it never expires. The clock only starts on
    redemption, so a key sitting in a DM for a week is not eaten by its
    own duration.
    """
    ensure()
    key = generate_key()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO premium_keys "
            "(key_hash, product, duration, created_at, created_by, note) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (hash_key(key), product, max(0, int(duration_days)),
             int(time.time()), str(created_by), str(note or "")[:200]),
        )
    return {"key": key, "duration_days": max(0, int(duration_days)),
            "product": product}


def lookup(key: str) -> Optional[dict[str, Any]]:
    """The stored row for a key, or None."""
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM premium_keys WHERE key_hash = ?", (hash_key(key),)
        ).fetchone()
    return dict(row) if row else None


def redeem(key: str, user_id: int | str) -> dict[str, Any]:
    """
    Bind a key to a Discord account.

    Returns {"ok": bool, "error": str, ...}. Errors are returned rather
    than raised because every one of them is a normal thing a user does:
    a typo, a key already used, a key someone revoked.
    """
    ensure()
    cleaned = normalise(key)
    if len(cleaned) != KEY_LENGTH:
        return {"ok": False, "error": "invalid_format"}

    user_id = str(user_id)
    now = int(time.time())

    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM premium_keys WHERE key_hash = ?", (hash_key(cleaned),)
        ).fetchone()

        if row is None:
            return {"ok": False, "error": "unknown"}
        if row["revoked"]:
            return {"ok": False, "error": "revoked"}

        if row["redeemed_by"]:
            # Re-entering your own key is not an error, it is someone
            # checking that it worked.
            if str(row["redeemed_by"]) == user_id:
                return {"ok": True, "already": True,
                        "expires_at": row["expires_at"],
                        "product": row["product"]}
            return {"ok": False, "error": "already_used"}

        expires_at = now + row["duration"] * 86400 if row["duration"] else None
        conn.execute(
            "UPDATE premium_keys SET redeemed_by = ?, redeemed_at = ?, "
            "expires_at = ? WHERE key_hash = ?",
            (user_id, now, expires_at, row["key_hash"]),
        )

    return {"ok": True, "already": False, "expires_at": expires_at,
            "product": row["product"]}


def status(user_id: int | str, product: str = "template_bot") -> dict[str, Any]:
    """
    Whether this Discord account currently has premium.

    This is what the template bot asks. An expired or revoked key counts
    as no premium, but the row stays so history is not lost.
    """
    ensure()
    user_id = str(user_id)
    now = int(time.time())

    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM premium_keys WHERE redeemed_by = ? AND product = ? "
            "AND revoked = 0",
            (user_id, product),
        ).fetchall()

    best: Optional[int] = None
    lifetime = False
    duration = 0
    for row in rows:
        if row["expires_at"] is None:
            lifetime = True
        elif row["expires_at"] > now:
            if best is None or int(row["expires_at"]) > best:
                best = int(row["expires_at"])
                # The duration of the licence that runs longest, so the
                # dashboard can draw "how much is left of it". Reporting
                # any other row's duration would give a bar that does not
                # match the date next to it.
                duration = int(row["duration"] or 0)

    active = lifetime or best is not None

    # Die Probewoche des Template-Bots zaehlt mit.
    #
    # Sie steht in einer eigenen Tabelle, weil sie kein Key ist: sie
    # wird nicht verkauft, nicht gesperrt und gilt genau einmal pro
    # Konto. Beantwortet wird die Frage aber hier -- `status()` ist die
    # eine Stelle, die „hat dieser Nutzer Premium?" beantwortet.
    # Dashboard, Speedrun und der Template-Bot fragen alle darueber.
    #
    # Der Import steht in der Funktion: utils/__init__ laedt diese
    # Datei, oben stuende ein Ringschluss.
    trial: Optional[dict[str, Any]] = None
    if product == "template_bot":
        try:
            from utils import premium_trial

            eintrag = premium_trial.get(user_id)
            if eintrag and eintrag["active"]:
                trial = eintrag
                active = True
                # Ein gekaufter Key laeuft laenger? Dann bleibt dessen
                # Datum stehen -- sonst verkuerzte die Probewoche eine
                # bezahlte Lizenz.
                if not lifetime and (best is None or eintrag["expires_at"] > best):
                    best = eintrag["expires_at"]
                    duration = eintrag["duration_days"]
        except Exception:
            # Eine kaputte Probewochen-Tabelle darf niemandem Premium
            # wegnehmen, den er bezahlt hat.
            trial = None

    # Tester bekommen Premium ohne Key.
    #
    # Die Pruefung sitzt hier und nicht bei den Aufrufern: `status()`
    # ist die eine Stelle, die "hat dieser Nutzer Premium?" beantwortet
    # -- Dashboard, Speedrun und der Template-Bot fragen alle darueber.
    # Den Bypass an jedem Aufrufer einzeln einzubauen hiesse, ihn
    # irgendwann irgendwo zu vergessen.
    #
    # Der Import steht bewusst in der Funktion: dashboard_roles laedt
    # utils/, und utils/__init__ importiert wiederum diese Datei --
    # oben stuende ein Ringschluss.
    tester = False
    if not active:
        try:
            from utils import dashboard_roles

            tester = dashboard_roles.is_tester(user_id)
        except Exception:
            # Eine kaputte Rollenabfrage darf niemandem Premium
            # wegnehmen, den er bezahlt hat -- und keinem geben.
            tester = False

    if tester:
        active = True
        lifetime = True

    return {
        "user_id": user_id,
        "product": product,
        "premium": active,
        # Damit die Oberflaeche "Tester-Zugang" statt "Lifetime-Key"
        # anzeigen kann -- und der Nutzer nicht glaubt, er haette
        # bezahlt.
        "via_tester": tester,
        # Damit die Oberflaeche „7 Tage kostenlos" statt „Premium"
        # schreiben kann -- und der Nutzer weiss, dass es endet.
        "via_trial": trial is not None,
        "trial": trial,
        # None means "forever" when active, and nothing at all when not.
        "expires_at": None if lifetime else best,
        "lifetime": lifetime,
        # 0 when unknown or unlimited; the caller must not divide by it.
        "duration_days": 0 if lifetime else duration,
    }


def revoke(key: str) -> bool:
    """Turn a key off. Returns whether a row was touched."""
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE premium_keys SET revoked = 1 WHERE key_hash = ?",
            (hash_key(key),),
        )
        return cur.rowcount > 0


def revoke_hash(key_hash: str) -> bool:
    """
    Revoke by hash, which is all the admin list ever sees.

    The key itself is not stored, so a support request of the shape
    "please cancel this person's licence" can only be served this way.
    """
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE premium_keys SET revoked = 1 WHERE key_hash = ?",
            (str(key_hash),),
        )
        return cur.rowcount > 0


def unrevoke_hash(key_hash: str) -> bool:
    """Undo a revoke. Revoking the wrong row should not be permanent."""
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE premium_keys SET revoked = 0 WHERE key_hash = ?",
            (str(key_hash),),
        )
        return cur.rowcount > 0


def delete_hash(key_hash: str) -> bool:
    """
    Remove a key row for good.

    Revoking keeps the row so the history stays readable; deleting is for
    rows that should not be there at all — a test key, a wrong duration,
    a mistaken entry. It cannot be undone, which is why the dashboard
    asks first.

    Note this frees the key itself again in principle, but since only the
    hash was ever stored and the key was 16 characters of 31, that is not
    a practical concern.
    """
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM premium_keys WHERE key_hash = ?", (str(key_hash),)
        )
        return cur.rowcount > 0


def purge(what: str = "revoked") -> int:
    """
    Delete a whole group of rows at once.

    "revoked"   — blocked keys
    "expired"   — redeemed keys whose time ran out
    "unclaimed" — keys nobody ever redeemed

    Deliberately no "all": clearing the table would also remove the rows
    that are currently granting people premium.
    """
    ensure()
    now = int(time.time())

    clauses = {
        "revoked": ("revoked = 1", ()),
        "expired": (
            "redeemed_by IS NOT NULL AND expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        ),
        "unclaimed": ("redeemed_by IS NULL AND revoked = 0", ()),
    }
    if what not in clauses:
        raise ValueError(f"unknown group: {what}")

    where, params = clauses[what]
    with _connect() as conn:
        cur = conn.execute(f"DELETE FROM premium_keys WHERE {where}", params)
        return cur.rowcount


def stats(product: str = "template_bot") -> dict[str, int]:
    """Counts for the admin overview, computed in one pass."""
    ensure()
    now = int(time.time())
    with _connect() as conn:
        rows = conn.execute(
            "SELECT redeemed_by, expires_at, revoked, created_at "
            "FROM premium_keys WHERE product = ?",
            (product,),
        ).fetchall()

    out = {
        "total": len(rows),
        "active": 0,
        "unclaimed": 0,
        "expired": 0,
        "revoked": 0,
        "lifetime": 0,
        "expiring_soon": 0,
        "created_30d": 0,
    }
    week = now + 7 * 86400
    month_ago = now - 30 * 86400

    for row in rows:
        if row["created_at"] and int(row["created_at"]) >= month_ago:
            out["created_30d"] += 1
        if row["revoked"]:
            out["revoked"] += 1
        elif not row["redeemed_by"]:
            out["unclaimed"] += 1
        elif row["expires_at"] is None:
            out["active"] += 1
            out["lifetime"] += 1
        elif int(row["expires_at"]) > now:
            out["active"] += 1
            if int(row["expires_at"]) <= week:
                out["expiring_soon"] += 1
        else:
            out["expired"] += 1

    return out


def owner_of_hash(key_hash: str) -> Optional[str]:
    """Which account a key belongs to, or None if nobody redeemed it."""
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT redeemed_by FROM premium_keys WHERE key_hash = ?",
            (str(key_hash),),
        ).fetchone()
    if row is None or not row["redeemed_by"]:
        return None
    return str(row["redeemed_by"])


def premium_user_ids(product: str = "template_bot") -> set[str]:
    """
    Everyone whose premium is currently valid.

    Used to decide who should hold the premium role. Expired and revoked
    rows drop out here, which is what makes the role come off again.
    """
    ensure()
    now = int(time.time())
    with _connect() as conn:
        rows = conn.execute(
            "SELECT redeemed_by, expires_at FROM premium_keys "
            "WHERE product = ? AND revoked = 0 AND redeemed_by IS NOT NULL",
            (product,),
        ).fetchall()

    return {
        str(row["redeemed_by"])
        for row in rows
        if row["expires_at"] is None or int(row["expires_at"]) > now
    }


def list_keys(limit: int = 100) -> list[dict[str, Any]]:
    """
    Recent keys for the admin view.

    The key itself cannot be listed — only its hash is stored, which is
    the whole point. A lost key has to be revoked and reissued.
    """
    ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT key_hash, product, duration, created_at, created_by, note, "
            "redeemed_by, redeemed_at, expires_at, revoked "
            "FROM premium_keys ORDER BY created_at DESC LIMIT ?",
            (max(1, min(500, int(limit))),),
        ).fetchall()
    return [dict(row) for row in rows]


# ── Premium ohne Key: die Beta ────────────────────────────────────────
#
# Wer in die Beta aufgenommen wird, bekommt Premium ohne einen Key
# eintippen zu muessen. Technisch ist es trotzdem ein Key -- er wird
# nur sofort erzeugt und gleich dem Konto zugeschrieben, statt in
# einer DM zu landen.
#
# Warum kein zweiter Weg: `status()` beantwortet die Frage „hat dieser
# Nutzer Premium?" fuer Dashboard, Speedrun und den Template-Bot. Ein
# zweiter Speicherort waere eine zweite Wahrheit, und die laeuft
# auseinander.


def grant_direct(user_id: int | str, *, duration_days: int = 0,
                 product: str = "main_bot", note: str = "") -> dict[str, Any]:
    """Einem Konto Premium geben, ohne dass es einen Key eintippt.

    Gibt es fuer dieses Produkt schon eine gueltige Lizenz, passiert
    nichts -- zwei parallele Lizenzen waeren nicht falsch, aber sie
    machen jede spaetere Frage „wann laeuft es ab?" mehrdeutig.
    """
    ensure()
    user_id = str(user_id)

    vorhanden = status(user_id, product=product)
    if vorhanden.get("premium"):
        return {"ok": True, "already": True, **vorhanden}

    key = generate_key()
    now = int(time.time())
    expires = None if duration_days <= 0 else now + duration_days * 86400

    with _connect() as conn:
        conn.execute(
            "INSERT INTO premium_keys "
            "(key_hash, product, duration, created_at, created_by, note, "
            " redeemed_by, redeemed_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (hash_key(key), product, max(0, int(duration_days)), now,
             "beta", str(note or "")[:200], user_id, now, expires),
        )

    return {"ok": True, "already": False, **status(user_id, product=product)}


def revoke_user(user_id: int | str, product: str = "main_bot") -> int:
    """Jede Lizenz dieses Kontos fuer dieses Produkt sperren.

    Die Zeilen bleiben stehen und werden nur als gesperrt markiert --
    so bleibt nachvollziehbar, dass jemand einmal Premium hatte.
    """
    ensure()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE premium_keys SET revoked = 1 "
            "WHERE redeemed_by = ? AND product = ? AND revoked = 0",
            (str(user_id), product),
        )
        return cur.rowcount or 0
