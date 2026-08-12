# ╔══════════════════════════════════════════════════════════════════╗
# ║   Team-Bewerbungen ueber die Website                             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Bewerbungen, die auf der Website ausgefuellt werden.

Nicht zu verwechseln mit ``application_store``: das sind die
Bewerbungen, die ein *Server* fuer sein eigenes Team einrichtet,
ausgefuellt per DM im Discord. Hier geht es um das Team **hinter dem
Bot** -- wer mitmachen will, klickt auf der Website auf »Team
beitreten«.

Warum das ueber Discord-Login laeuft
------------------------------------
Ohne Anmeldung koennte jeder beliebig viele Bewerbungen abschicken,
und niemand wuesste hinterher, wem die Rolle gegeben werden soll. Der
Discord-Login liefert beides: eine echte Nutzer-ID als Schluessel und
den Namen, den das Team im Server sieht.

**Eine Bewerbung pro Person.** Der Primaerschluessel ist die
Nutzer-ID, nicht ein Zaehler -- damit ist eine zweite technisch
unmoeglich, nicht nur unerwuenscht. Wer es trotzdem versucht,
bekommt seine Bewerbungsnummer und den Hinweis, dass er den
Fortschritt links einsehen kann.

Nach einer Entscheidung
-----------------------
Angenommen heisst: fertig, die Bewerbung bleibt stehen. Abgelehnt
heisst: die Bewerbung bleibt ebenfalls stehen, aber das Team kann sie
freigeben (``reopen``) -- dann darf die Person es erneut versuchen.
Automatisch neu bewerben geht nicht; sonst kaeme dieselbe Bewerbung
am naechsten Tag wieder.

Speicher
--------
``db/web_apply.db``. Braucht ein Railway-Volume, sonst sind alle
Bewerbungen nach dem naechsten Deploy weg -- mitten im Verfahren.
"""

from __future__ import annotations

import json
import time

from utils import db_paths

DB_PATH = "db/web_apply.db"

# ── Grenzen ──────────────────────────────────────────────────────────
MAX_ANSWER = 2000
MAX_REASON = 1000
MIN_ANSWER = 10          # kuerzer als zehn Zeichen ist keine Antwort
MAX_LIST = 200

STATUS_OPEN = "open"
STATUS_ACCEPTED = "accepted"
STATUS_DENIED = "denied"
STATUS_WITHDRAWN = "withdrawn"

# ── Die vier Rollen und ihre Fragen ──────────────────────────────────
#
# Je Rolle eigene Fragen. Ein gemeinsamer Fragebogen fuer alle waere
# kuerzer gewesen und haette bei jeder Rolle danebengelegen: einen
# Designer nach seiner Moderationserfahrung zu fragen bringt
# niemandem etwas.
#
# Die letzte Frage ist ueberall dieselbe (Zeit pro Woche), weil das
# die Frage ist, an der es in der Praxis scheitert.

ROLES: dict[str, dict] = {
    "content": {
        "key": "content",
        "label": "Content Creator",
        "short": "Videos, Clips und Beitraege fuer den Bot",
        "colour": "#f59e0b",
        "questions": [
            "Auf welchen Plattformen bist du aktiv? Bitte mit Link zu deinem Kanal oder Profil.",
            "Was fuer Inhalte machst du bisher, und wie viele Leute erreichst du damit ungefaehr?",
            "Welche Art von Inhalt wuerdest du fuer uns machen wollen — Tutorials, Kurzvideos, Ankuendigungen, etwas anderes?",
            "Zeig uns etwas, worauf du stolz bist: ein Video, ein Thumbnail, ein Beitrag.",
            "Womit schneidest oder gestaltest du? Und wie lange brauchst du ungefaehr fuer ein fertiges Stueck?",
            "Wie viel Zeit hast du pro Woche realistisch fuer das Team?",
        ],
    },
    "designer": {
        "key": "designer",
        "label": "Designer",
        "short": "Grafiken, Banner und das Aussehen des Bots",
        "colour": "#ec4899",
        "questions": [
            "Womit arbeitest du? (Photoshop, Figma, Illustrator, Affinity, GIMP …)",
            "Zeig uns dein Portfolio oder drei Arbeiten, die du selbst gemacht hast — Links genuegen.",
            "Was machst du am liebsten: Banner, Embeds, Logos, Icons, ganze Server-Gestaltung?",
            "Wie lange brauchst du ungefaehr fuer ein Server-Banner, und wie laeuft das bei dir ab?",
            "Wie gehst du mit Kritik um, wenn dein Entwurf zweimal geaendert werden soll?",
            "Wie viel Zeit hast du pro Woche realistisch fuer das Team?",
        ],
    },
    "moderator": {
        "key": "moderator",
        "label": "Moderator",
        "short": "Support-Server sauber und freundlich halten",
        "colour": "#22c55e",
        "questions": [
            "Wie alt bist du, und in welcher Zeitzone bist du unterwegs?",
            "Wo hast du schon moderiert? Bitte mit Servergroesse und wie lange.",
            "Jemand beleidigt im Support-Kanal einen anderen Nutzer. Was machst du — Schritt fuer Schritt?",
            "Ein Teammitglied trifft eine Entscheidung, die du fuer falsch haeltst. Wie gehst du damit um?",
            "Zwei Leute streiten, beide haben irgendwie recht. Wie loest du das, ohne dass einer sich uebergangen fuehlt?",
            "Warum willst du ausgerechnet bei uns moderieren?",
            "Wie viel Zeit hast du pro Woche realistisch fuer das Team?",
        ],
    },
    "tester": {
        "key": "tester",
        "label": "Tester",
        "short": "Neue Funktionen vor allen anderen ausprobieren",
        "colour": "#3b82f6",
        "questions": [
            "Welche Funktionen des Bots benutzt du selbst am meisten?",
            "Hast du schon einmal einen Fehler gemeldet? Was war es, und wie hast du ihn beschrieben?",
            "Du findest einen Fehler. Was schreibst du uns, damit wir ihn nachstellen koennen?",
            "Wie gruendlich probierst du etwas aus — klickst du einmal durch oder versuchst du, es kaputtzukriegen?",
            "Mit welchen Geraeten bist du unterwegs? (Handy, Rechner, beides — und welches Betriebssystem)",
            "Wie viel Zeit hast du pro Woche realistisch fuer das Team?",
        ],
    },
}

ROLE_KEYS = tuple(ROLES)


def role_list() -> list[dict]:
    """Die Rollen fuer die Website -- ohne die Fragen."""
    return [
        {
            "key": r["key"],
            "label": r["label"],
            "short": r["short"],
            "colour": r["colour"],
            "questions": len(r["questions"]),
        }
        for r in ROLES.values()
    ]


def questions_of(role: str) -> list[str]:
    eintrag = ROLES.get(role)
    return list(eintrag["questions"]) if eintrag else []


# ── Schema ───────────────────────────────────────────────────────────
#
# Die Spalten stehen an EINER Stelle und bauen die Tabelle UND tragen
# Fehlendes nach. Zwei handgepflegte Listen sind hier schon einmal
# auseinandergelaufen (team_update: updated_at fehlte im Nachtrag, und
# jedes Sichern scheiterte mit "no such column").
COLUMNS = (
    ("user_id", "INTEGER PRIMARY KEY"),
    ("user_name", "TEXT DEFAULT ''"),
    ("avatar", "TEXT DEFAULT ''"),
    ("role_key", "TEXT NOT NULL"),
    ("answers", "TEXT DEFAULT '[]'"),
    ("status", "TEXT DEFAULT 'open'"),
    ("decided_by", "TEXT DEFAULT ''"),
    ("decided_by_name", "TEXT DEFAULT ''"),
    ("decided_at", "INTEGER DEFAULT 0"),
    ("reason", "TEXT DEFAULT ''"),
    ("created_at", "INTEGER NOT NULL DEFAULT 0"),
    ("updated_at", "INTEGER DEFAULT 0"),
    # Welche Discord-Rolle beim Annehmen vergeben wurde -- fuer die
    # Nachvollziehbarkeit, falls jemand sie spaeter von Hand entfernt.
    ("granted_role_id", "TEXT DEFAULT ''"),
)


async def ensure_schema(db) -> None:
    spalten = ", ".join(f"{n} {t}" for n, t in COLUMNS)
    await db.execute(f"CREATE TABLE IF NOT EXISTS web_applications ({spalten})")

    # Nachtragen, was auf einer aelteren Installation fehlt.
    async with db.execute("PRAGMA table_info(web_applications)") as cursor:
        vorhanden = {r[1] for r in await cursor.fetchall()}
    for name, typ in COLUMNS:
        if vorhanden and name not in vorhanden:
            # PRIMARY KEY und NOT NULL lassen sich nachtraeglich nicht
            # setzen -- der nackte Typ genuegt hier.
            sauber = typ.split(" PRIMARY KEY")[0].replace(" NOT NULL", "")
            await db.execute(
                f"ALTER TABLE web_applications ADD COLUMN {name} {sauber}"
            )

    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_web_apply_status"
        " ON web_applications (status, created_at)"
    )

    # Die Einstellungen des Teams: welche Discord-Rolle eine
    # angenommene Bewerbung vergibt, wohin die Meldung geht.
    # Je Bewerbungsrolle: welcher Server, welche Rolle.
    #
    # Frueher gab es genau einen Server fuer alle vier. Das reicht
    # nicht: Tester gehoeren auf den Test-Server, Moderatoren auf den
    # Support-Server. Ein leeres ``guild_id`` faellt weiterhin auf den
    # allgemeinen Server zurueck -- wer nur einen hat, muss nichts
    # doppelt eintragen.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS web_apply_config ("
        " role_key TEXT PRIMARY KEY,"
        " discord_role_id TEXT DEFAULT '',"
        " guild_id TEXT DEFAULT '',"
        " open INTEGER DEFAULT 1)"
    )
    # Nachtragen, was auf einer aelteren Installation fehlt.
    async with db.execute("PRAGMA table_info(web_apply_config)") as cursor:
        spalten = {r[1] for r in await cursor.fetchall()}
    if spalten and "guild_id" not in spalten:
        await db.execute(
            "ALTER TABLE web_apply_config ADD COLUMN guild_id TEXT DEFAULT ''"
        )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS web_apply_settings ("
        " id INTEGER PRIMARY KEY CHECK (id = 1),"
        " guild_id TEXT DEFAULT '',"
        " channel_id TEXT DEFAULT '',"
        " dm_applicant INTEGER DEFAULT 1)"
    )
    await db.commit()


def _row(r) -> dict:
    try:
        antworten = json.loads(r["answers"] or "[]")
    except (ValueError, TypeError):
        antworten = []
    rolle = ROLES.get(r["role_key"], {})
    return {
        # Als Text: eine Discord-ID ist groesser als das, was
        # JavaScript unfallfrei als Zahl haelt.
        "user_id": str(r["user_id"]),
        "user_name": r["user_name"] or "",
        "avatar": r["avatar"] or "",
        "role_key": r["role_key"],
        "role_label": rolle.get("label", r["role_key"]),
        "role_colour": rolle.get("colour", "#5865f2"),
        "questions": rolle.get("questions", []),
        "answers": antworten if isinstance(antworten, list) else [],
        "status": r["status"] or STATUS_OPEN,
        "decided_by": r["decided_by"] or "",
        "decided_by_name": r["decided_by_name"] or "",
        "decided_at": int(r["decided_at"] or 0),
        "reason": r["reason"] or "",
        "created_at": int(r["created_at"] or 0),
        "updated_at": int(r["updated_at"] or 0),
        "granted_role_id": r["granted_role_id"] or "",
        # Die Bewerbungsnummer, die der Person angezeigt wird.
        # Abgeleitet statt gespeichert: die Nutzer-ID ist der
        # Schluessel, ein zweiter Zaehler waere eine zweite Wahrheit.
        "ticket": ticket_of(int(r["user_id"]), int(r["created_at"] or 0)),
    }


def ticket_of(user_id: int, created_at: int) -> str:
    """Eine kurze, gut vorlesbare Nummer.

    Aus Nutzer-ID und Zeitpunkt abgeleitet, damit sie sich nicht
    aendert und trotzdem nicht die Discord-ID verraet.
    """
    roh = (int(user_id) % 100000) * 7 + (int(created_at) % 9973)
    return f"BW-{roh % 100000:05d}"


# ── Lesen ────────────────────────────────────────────────────────────


async def get_application(user_id: int) -> dict | None:
    import aiosqlite

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM web_applications WHERE user_id = ?", (int(user_id),)
        ) as cursor:
            zeile = await cursor.fetchone()
    return _row(zeile) if zeile else None


async def list_applications(status: str = "", limit: int = MAX_LIST) -> list[dict]:
    import aiosqlite

    sql = "SELECT * FROM web_applications"
    werte: list = []
    if status:
        sql += " WHERE status = ?"
        werte.append(status)
    # Offene zuerst, dann die neuesten.
    sql += " ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, created_at DESC"
    sql += " LIMIT ?"
    werte.append(max(1, min(MAX_LIST, int(limit))))

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, werte) as cursor:
            zeilen = await cursor.fetchall()
    return [_row(z) for z in zeilen]


async def counts() -> dict[str, int]:
    out = {STATUS_OPEN: 0, STATUS_ACCEPTED: 0, STATUS_DENIED: 0,
           STATUS_WITHDRAWN: 0}
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT status, COUNT(*) FROM web_applications GROUP BY status"
        ) as cursor:
            for status, anzahl in await cursor.fetchall():
                if status in out:
                    out[status] = int(anzahl or 0)
    return out


# ── Schreiben ────────────────────────────────────────────────────────


class AlreadyApplied(Exception):
    """Es gibt schon eine Bewerbung dieser Person.

    Traegt die vorhandene mit, damit der Aufrufer Nummer und Status
    anzeigen kann statt nur »geht nicht«.
    """

    def __init__(self, vorhanden: dict):
        super().__init__("Es gibt bereits eine Bewerbung.")
        self.existing = vorhanden


async def submit(user_id: int, user_name: str, avatar: str, role_key: str,
                 answers: list[str]) -> dict:
    """
    Eine Bewerbung abgeben.

    Wirft ``AlreadyApplied``, wenn es schon eine gibt -- egal in
    welchem Zustand. Erst wenn das Team sie freigibt, geht eine neue.
    """
    if role_key not in ROLES:
        raise ValueError("Diese Rolle gibt es nicht.")

    # Die vorhandene Bewerbung ZUERST pruefen -- vor den Antworten.
    #
    # Nachgemessen, nicht vermutet: das Repro-Skript hat es gefunden.
    # Die Laengenpruefung lief vorher zuerst, und wer eine zweite
    # Bewerbung mit einer anderen Fragenzahl abschickte, bekam
    # "Frage 7 ist zu kurz" statt "du hast schon eine laufen". Also
    # ausgerechnet in dem Fall, den der Nutzer sieht, wenn er es fuer
    # eine andere Rolle versucht, kam die falsche Meldung -- und
    # weder Nummer noch Fortschritt.
    vorhandene = await get_application(user_id)
    if vorhandene is not None:
        raise AlreadyApplied(vorhandene)

    fragen = questions_of(role_key)
    sauber: list[str] = []
    for i, frage in enumerate(fragen):
        text = str((answers or [None] * len(fragen))[i] if i < len(answers or []) else "").strip()
        if len(text) < MIN_ANSWER:
            raise ValueError(
                f"Frage {i + 1} ist zu kurz — bitte mindestens "
                f"{MIN_ANSWER} Zeichen."
            )
        sauber.append(text[:MAX_ANSWER])

    jetzt = int(time.time())

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        import aiosqlite
        db.row_factory = aiosqlite.Row

        # Und noch einmal, jetzt in derselben Verbindung: zwischen der
        # Pruefung oben und diesem INSERT koennte eine zweite Anfrage
        # durchgelaufen sein. Der Primaerschluessel faengt das zwar
        # ohnehin ab, aber mit einer sprechenden Meldung statt einem
        # IntegrityError.
        async with db.execute(
            "SELECT * FROM web_applications WHERE user_id = ?", (int(user_id),)
        ) as cursor:
            vorhanden = await cursor.fetchone()
        if vorhanden is not None:
            raise AlreadyApplied(_row(vorhanden))

        await db.execute(
            "INSERT INTO web_applications"
            " (user_id, user_name, avatar, role_key, answers, status,"
            "  created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (int(user_id), str(user_name or "")[:100], str(avatar or "")[:300],
             role_key, json.dumps(sauber), STATUS_OPEN, jetzt, jetzt),
        )
        await db.commit()

    return await get_application(user_id)


async def decide(user_id: int, status: str, actor: str, actor_name: str,
                 reason: str = "", granted_role_id: str = "") -> dict | None:
    """
    Annehmen oder ablehnen.

    Gibt ``None`` zurueck, wenn die Bewerbung nicht mehr offen ist --
    dann hat in der Zwischenzeit jemand anderes entschieden, und der
    zweite Klick darf die erste Entscheidung nicht ueberschreiben.
    """
    if status not in (STATUS_ACCEPTED, STATUS_DENIED):
        raise ValueError("Nur annehmen oder ablehnen.")

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "UPDATE web_applications SET status = ?, decided_by = ?,"
            " decided_by_name = ?, decided_at = ?, reason = ?,"
            " granted_role_id = ?, updated_at = ?"
            " WHERE user_id = ? AND status = ?",
            (status, str(actor or "")[:40], str(actor_name or "")[:100],
             int(time.time()), str(reason or "")[:MAX_REASON],
             str(granted_role_id or "")[:40], int(time.time()),
             int(user_id), STATUS_OPEN),
        )
        await db.commit()
        if not cursor.rowcount:
            return None

    return await get_application(user_id)


async def reopen(user_id: int) -> bool:
    """
    Die Bewerbung loeschen, damit die Person es erneut versuchen darf.

    Bewusst ein Loeschen und kein Zuruecksetzen auf »offen«: sonst
    stuende die alte, abgelehnte Bewerbung wieder in der Liste des
    Teams, als waere sie neu.
    """
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "DELETE FROM web_applications WHERE user_id = ?", (int(user_id),)
        )
        await db.commit()
        return bool(cursor.rowcount)


async def withdraw(user_id: int) -> bool:
    """Die eigene Bewerbung zurueckziehen. Nur solange sie offen ist."""

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "UPDATE web_applications SET status = ?, updated_at = ?"
            " WHERE user_id = ? AND status = ?",
            (STATUS_WITHDRAWN, int(time.time()), int(user_id), STATUS_OPEN),
        )
        await db.commit()
        return bool(cursor.rowcount)


# ── Einstellungen ────────────────────────────────────────────────────


async def get_config() -> dict:
    """Welche Discord-Rolle je Bewerbungsrolle vergeben wird."""

    import aiosqlite

    rollen = {
        k: {"discord_role_id": "", "guild_id": "", "open": True}
        for k in ROLE_KEYS
    }
    einstellungen = {"guild_id": "", "channel_id": "", "dm_applicant": True}

    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM web_apply_config") as cursor:
            for zeile in await cursor.fetchall():
                if zeile["role_key"] in rollen:
                    rollen[zeile["role_key"]] = {
                        "discord_role_id": zeile["discord_role_id"] or "",
                        "guild_id": (
                            zeile["guild_id"]
                            if "guild_id" in zeile.keys() else ""
                        ) or "",
                        "open": bool(zeile["open"]),
                    }
        async with db.execute(
            "SELECT * FROM web_apply_settings WHERE id = 1"
        ) as cursor:
            zeile = await cursor.fetchone()
        if zeile is not None:
            einstellungen = {
                "guild_id": zeile["guild_id"] or "",
                "channel_id": zeile["channel_id"] or "",
                "dm_applicant": bool(zeile["dm_applicant"]),
            }

    return {"roles": rollen, **einstellungen}


def guild_for(config: dict, role_key: str) -> str:
    """
    Auf welchem Server die Rolle vergeben wird.

    Erst der eigene Server der Bewerbungsrolle, sonst der allgemeine.
    Ein leerer Rueckgabewert heisst: keiner eingestellt -- dann wird
    keine Rolle vergeben, die Bewerbung laesst sich aber trotzdem
    annehmen. Eine Zusage darf nicht daran scheitern, dass niemand
    einen Server ausgesucht hat.
    """
    eigener = str(
        (config.get("roles") or {}).get(role_key, {}).get("guild_id") or ""
    ).strip()
    if eigener.isdigit():
        return eigener
    allgemein = str(config.get("guild_id") or "").strip()
    return allgemein if allgemein.isdigit() else ""


async def save_config(data: dict) -> dict:
    async with db_paths.connect(DB_PATH) as db:
        await ensure_schema(db)

        for schluessel, wert in (data.get("roles") or {}).items():
            if schluessel not in ROLE_KEYS:
                continue
            rolle = str((wert or {}).get("discord_role_id") or "").strip()
            server = str((wert or {}).get("guild_id") or "").strip()
            await db.execute(
                "INSERT INTO web_apply_config"
                " (role_key, discord_role_id, guild_id, open)"
                " VALUES (?, ?, ?, ?)"
                " ON CONFLICT(role_key) DO UPDATE SET"
                " discord_role_id = excluded.discord_role_id,"
                " guild_id = excluded.guild_id,"
                " open = excluded.open",
                (schluessel, rolle if rolle.isdigit() else "",
                 server if server.isdigit() else "",
                 int(bool((wert or {}).get("open", True)))),
            )

        if any(k in data for k in ("guild_id", "channel_id", "dm_applicant")):
            vorher = await get_config()
            guild = str(data.get("guild_id", vorher["guild_id"]) or "").strip()
            kanal = str(data.get("channel_id", vorher["channel_id"]) or "").strip()
            dm = int(bool(data.get("dm_applicant", vorher["dm_applicant"])))
            await db.execute(
                "INSERT INTO web_apply_settings (id, guild_id, channel_id, dm_applicant)"
                " VALUES (1, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET"
                " guild_id = excluded.guild_id,"
                " channel_id = excluded.channel_id,"
                " dm_applicant = excluded.dm_applicant",
                (guild if guild.isdigit() else "",
                 kanal if kanal.isdigit() else "", dm),
            )

        await db.commit()

    return await get_config()
