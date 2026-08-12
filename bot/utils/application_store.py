"""
Bewerbungen -- Panels, Kategorien, Fragen und laufende Gespraeche.

Der Ablauf, den das abbildet:

  1. Im Dashboard legt man ein **Panel** an (hoechstens zwei pro Server)
     und darin bis zu acht **Kategorien** -- etwa "Moderator" oder
     "Supporter". Jede Kategorie hat ihre eigenen Fragen, drei bis
     zwanzig.
  2. Das Panel wird in einen Kanal geschickt: ein Auswahlmenue mit den
     Kategorien.
  3. Wer auswaehlt, bekommt eine DM. Der Bot stellt die Fragen einzeln
     und wartet auf die Antwort.
  4. Am Ende landet alles in einem Kanal, den das Team eingestellt hat,
     mit zwei Knoepfen: annehmen und ablehnen, beide mit Begruendung.

Zwei Entscheidungen, die den Aufbau erklaeren:

**Eine offene Bewerbung pro Person, serverweit uebergreifend.** Nicht
pro Kategorie und nicht pro Server: wer gleichzeitig auf fuenf Servern
bewirbt, verwechselt in der DM sowieso, welche Frage zu welcher
Bewerbung gehoert -- der Bot fragt ja im selben Gespraechsfenster. Die
Tabelle ``active_sessions`` hat deshalb die Nutzer-ID als
Primaerschluessel und nichts sonst.

**Der Fortschritt liegt in der Datenbank, nicht im Arbeitsspeicher.**
Ein ``wait_for`` haette nach jedem Neustart eine halbe Bewerbung im
Nichts hinterlassen. So wird der Faden nach einem Deploy einfach
weitergesponnen.
"""

from __future__ import annotations

import json
import time

from utils import db_paths

APP_DB = "db/applications.db"

MAX_PANELS = 2
MAX_CATEGORIES = 8
MIN_QUESTIONS = 3
# Beim Annehmen vergebene Rollen. Fuenf reicht fuer jede Staffelung,
# die man von Hand pflegen will -- darueber wird es unuebersichtlich.
MAX_ACCEPT_ROLES = 5
MAX_QUESTIONS = 20

# Eine Stunde pro Frage. Wer nachdenken will, soll das koennen; laenger
# offen zu halten hiesse, dass eine vergessene Bewerbung jemanden
# dauerhaft blockiert.
ANSWER_TIMEOUT = 3600

# Discord laesst 4000 Zeichen im Beschreibungsfeld eines Embeds zu.
# 1000 pro Antwort heisst: auch zwanzig Antworten passen noch in eine
# lesbare Zusammenfassung, wenn sie auf mehrere Felder verteilt werden.
MAX_ANSWER_LEN = 1000
MAX_QUESTION_LEN = 300

STATUS_OPEN = "open"
STATUS_ACCEPTED = "accepted"
STATUS_DENIED = "denied"
STATUS_CANCELLED = "cancelled"


async def ensure_schema(db) -> None:
    await db.execute(
        "CREATE TABLE IF NOT EXISTS app_panels ("
        " panel_id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL,"
        " name TEXT NOT NULL DEFAULT 'Bewerbungen',"
        " channel_id INTEGER,"
        " message_id INTEGER,"
        " results_channel_id INTEGER,"
        " embed_title TEXT DEFAULT 'Bewerbungen',"
        " embed_description TEXT DEFAULT '',"
        " embed_color INTEGER DEFAULT 3447003,"
        " embed_image_url TEXT,"
        " embed_thumbnail_url TEXT,"
        " placeholder TEXT DEFAULT 'Wofuer moechtest du dich bewerben?',"
        " deny_cooldown_enabled INTEGER DEFAULT 0,"
        " deny_cooldown_days INTEGER DEFAULT 7)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS app_categories ("
        " category_id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " panel_id INTEGER NOT NULL,"
        " guild_id INTEGER NOT NULL,"
        " name TEXT NOT NULL,"
        " emoji TEXT DEFAULT '',"
        " description TEXT DEFAULT '',"
        " questions TEXT DEFAULT '[]',"
        " results_channel_id INTEGER,"
        " accept_role_id INTEGER,"
        " accept_roles TEXT DEFAULT '',"
        " staff_roles TEXT DEFAULT '',"
        " position INTEGER DEFAULT 0)"
    )
    # Eine Zeile pro Person -- der Primaerschluessel ist der Grund,
    # warum niemand zwei Bewerbungen gleichzeitig laufen lassen kann.
    await db.execute(
        "CREATE TABLE IF NOT EXISTS active_sessions ("
        " user_id INTEGER PRIMARY KEY,"
        " guild_id INTEGER NOT NULL,"
        " category_id INTEGER NOT NULL,"
        " question_index INTEGER DEFAULT 0,"
        " answers TEXT DEFAULT '[]',"
        " started_at INTEGER NOT NULL,"
        " last_prompt_at INTEGER NOT NULL)"
    )
    await db.execute(
        "CREATE TABLE IF NOT EXISTS applications ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " guild_id INTEGER NOT NULL,"
        " category_id INTEGER NOT NULL,"
        " user_id INTEGER NOT NULL,"
        " answers TEXT DEFAULT '[]',"
        " status TEXT DEFAULT 'open',"
        " decided_by INTEGER,"
        " decided_at INTEGER,"
        " reason TEXT DEFAULT '',"
        " message_id INTEGER,"
        " created_at INTEGER NOT NULL)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_apps_lookup"
        " ON applications (guild_id, user_id, status)"
    )
    await db.execute(
        "CREATE INDEX IF NOT EXISTS idx_app_cats_panel"
        " ON app_categories (panel_id, position)"
    )

    # Spalten, die spaeter dazugekommen sind.
    #
    # CREATE TABLE IF NOT EXISTS aendert an einer bestehenden Tabelle
    # nichts. Auf einer Installation, die vor dieser Aenderung lief,
    # fehlt `accept_roles` deshalb -- und jede Abfrage scheitert mit
    # "no such column: accept_roles", also ist der ganze Reiter tot.
    # Nachgemessen, nicht vermutet.
    #
    # schema_guard traegt die Spalte beim Start ebenfalls nach; hier
    # steht es zusaetzlich, damit der Store fuer sich allein
    # funktioniert und nicht davon abhaengt, dass vorher jemand anderes
    # aufgeraeumt hat.
    async with db.execute("PRAGMA table_info(app_categories)") as cursor:
        spalten = {r[1] for r in await cursor.fetchall()}
    if spalten and "accept_roles" not in spalten:
        await db.execute(
            "ALTER TABLE app_categories ADD COLUMN accept_roles TEXT DEFAULT ''"
        )

    await db.commit()


# ── Panels ───────────────────────────────────────────────────────────

async def list_panels(guild_id: int) -> list[dict]:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT panel_id, name, channel_id, message_id, results_channel_id,"
            " embed_title, embed_description, embed_color, embed_image_url,"
            " embed_thumbnail_url, placeholder, deny_cooldown_enabled,"
            " deny_cooldown_days"
            " FROM app_panels WHERE guild_id = ? ORDER BY panel_id",
            (guild_id,),
        ) as cursor:
            zeilen = await cursor.fetchall()

        panels = []
        for r in zeilen:
            async with db.execute(
                "SELECT category_id, name, emoji, description, questions,"
                " results_channel_id, accept_role_id, accept_roles,"
                " staff_roles, position"
                " FROM app_categories WHERE panel_id = ?"
                " ORDER BY position, category_id",
                (r[0],),
            ) as cursor:
                kategorien = await cursor.fetchall()

            panels.append({
                "panel_id": int(r[0]),
                "name": r[1],
                # Als Zeichenkette: Discord-IDs sind groesser als das,
                # was JavaScript unfallfrei als Zahl haelt.
                "channel_id": str(r[2]) if r[2] else None,
                "message_id": str(r[3]) if r[3] else None,
                "results_channel_id": str(r[4]) if r[4] else None,
                "embed_title": r[5] or "",
                "embed_description": r[6] or "",
                "embed_color": int(r[7] or 3447003),
                "embed_image_url": r[8] or "",
                "embed_thumbnail_url": r[9] or "",
                "placeholder": r[10] or "",
                "deny_cooldown_enabled": bool(r[11]),
                "deny_cooldown_days": int(r[12] or 7),
                "categories": [_category_row(c) for c in kategorien],
            })
        return panels


def _category_row(c) -> dict:
    try:
        fragen = json.loads(c[4] or "[]")
    except (ValueError, TypeError):
        fragen = []
    # Mehrere Rollen beim Annehmen.
    #
    # Frueher war es genau eine, in `accept_role_id`. Die Spalte bleibt
    # stehen und wird mitgelesen: eine Kategorie, die vor dieser
    # Aenderung eingerichtet wurde, verlaere sonst still ihre Rolle, und
    # das faellt erst auf, wenn jemand angenommen wird.
    rollen = [x for x in (c[7] or "").split(",") if x]
    if not rollen and c[6]:
        rollen = [str(c[6])]

    return {
        "category_id": int(c[0]),
        "name": c[1],
        "emoji": c[2] or "",
        "description": c[3] or "",
        "questions": fragen if isinstance(fragen, list) else [],
        "results_channel_id": str(c[5]) if c[5] else None,
        # Bleibt fuer alte Aufrufer erhalten -- die erste der Rollen.
        "accept_role_id": rollen[0] if rollen else None,
        "accept_roles": rollen,
        "staff_roles": [x for x in (c[8] or "").split(",") if x],
        "position": int(c[9] or 0),
    }


async def create_panel(guild_id: int, name: str = "Bewerbungen") -> dict:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT COUNT(*) FROM app_panels WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if int(row[0] or 0) >= MAX_PANELS:
            raise ValueError(f"Mehr als {MAX_PANELS} Panels gehen nicht.")

        cursor = await db.execute(
            "INSERT INTO app_panels (guild_id, name) VALUES (?, ?)",
            (guild_id, (name or "Bewerbungen")[:80]),
        )
        await db.commit()
        return {"panel_id": int(cursor.lastrowid)}


PANEL_FIELDS = {
    "name": ("name", 80),
    "channel_id": ("channel_id", None),
    "results_channel_id": ("results_channel_id", None),
    "embed_title": ("embed_title", 250),
    "embed_description": ("embed_description", 4000),
    "embed_color": ("embed_color", None),
    "embed_image_url": ("embed_image_url", 500),
    "embed_thumbnail_url": ("embed_thumbnail_url", 500),
    "placeholder": ("placeholder", 140),
}


async def update_panel(guild_id: int, panel_id: int, data: dict) -> None:
    zuweisungen, werte = [], []

    for schluessel, (spalte, grenze) in PANEL_FIELDS.items():
        if schluessel not in data:
            continue
        wert = data[schluessel]
        if spalte.endswith("channel_id"):
            text = str(wert or "").strip()
            wert = int(text) if text.isdigit() else None
        elif spalte == "embed_color":
            try:
                wert = max(0, min(0xFFFFFF, int(wert)))
            except (TypeError, ValueError):
                continue
        elif grenze:
            wert = str(wert or "")[:grenze]
        zuweisungen.append(f"{spalte} = ?")
        werte.append(wert)

    if "deny_cooldown_enabled" in data:
        zuweisungen.append("deny_cooldown_enabled = ?")
        werte.append(int(bool(data["deny_cooldown_enabled"])))
    if "deny_cooldown_days" in data:
        try:
            tage = int(data["deny_cooldown_days"])
        except (TypeError, ValueError):
            tage = 7
        # Null Tage waere keine Sperre -- dafuer gibt es den Schalter.
        zuweisungen.append("deny_cooldown_days = ?")
        werte.append(max(1, min(365, tage)))

    if not zuweisungen:
        return

    werte += [panel_id, guild_id]
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        await db.execute(
            f"UPDATE app_panels SET {', '.join(zuweisungen)}"
            " WHERE panel_id = ? AND guild_id = ?",
            werte,
        )
        await db.commit()


async def set_message_id(panel_id: int, message_id: int | None) -> None:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "UPDATE app_panels SET message_id = ? WHERE panel_id = ?",
            (message_id, panel_id),
        )
        await db.commit()


async def delete_panel(guild_id: int, panel_id: int) -> bool:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "DELETE FROM app_categories WHERE panel_id = ? AND guild_id = ?",
            (panel_id, guild_id),
        )
        cursor = await db.execute(
            "DELETE FROM app_panels WHERE panel_id = ? AND guild_id = ?",
            (panel_id, guild_id),
        )
        await db.commit()
        return bool(cursor.rowcount)


# ── Kategorien ───────────────────────────────────────────────────────

def clean_questions(fragen) -> list[str]:
    """Fragen saeubern -- leere raus, gekuerzt, hoechstens zwanzig."""
    if not isinstance(fragen, list):
        return []
    sauber = []
    for f in fragen:
        text = str(f or "").strip()
        if text:
            sauber.append(text[:MAX_QUESTION_LEN])
        if len(sauber) >= MAX_QUESTIONS:
            break
    return sauber


async def upsert_category(guild_id: int, panel_id: int, data: dict) -> dict:
    kategorie_id = data.get("category_id")
    name = str(data.get("name", "")).strip()[:80]
    if not name:
        raise ValueError("Die Kategorie braucht einen Namen.")

    fragen = clean_questions(data.get("questions", []))
    # Unter drei Fragen ist es keine Bewerbung, sondern ein Formular mit
    # einem Feld -- und der Sinn der Sache geht verloren.
    if len(fragen) < MIN_QUESTIONS:
        raise ValueError(
            f"Mindestens {MIN_QUESTIONS} Fragen, aktuell {len(fragen)}."
        )

    ergebnis_kanal = str(data.get("results_channel_id") or "").strip()
    team = ",".join(
        str(r) for r in (data.get("staff_roles") or []) if str(r).isdigit()
    )

    # Die Rollen beim Annehmen. `accept_role_id` bleibt als Eingabe
    # erlaubt, damit ein alter Aufrufer nichts kaputtmacht -- doppelte
    # werden entfernt, ohne die Reihenfolge zu verlieren.
    roh = data.get("accept_roles")
    if roh is None and data.get("accept_role_id"):
        roh = [data["accept_role_id"]]
    rollen: list[str] = []
    for r in (roh or []):
        text = str(r).strip()
        if text.isdigit() and text not in rollen:
            rollen.append(text)
        if len(rollen) >= MAX_ACCEPT_ROLES:
            break
    accept_roles = ",".join(rollen)
    # Die alte Spalte mitschreiben: sonst zeigt eine Fassung des Bots,
    # die diese Aenderung noch nicht kennt, gar keine Rolle mehr an.
    erste = int(rollen[0]) if rollen else None

    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)

        if kategorie_id:
            await db.execute(
                "UPDATE app_categories SET name = ?, emoji = ?, description = ?,"
                " questions = ?, results_channel_id = ?, accept_role_id = ?,"
                " accept_roles = ?, staff_roles = ?"
                " WHERE category_id = ? AND guild_id = ?",
                (
                    name, str(data.get("emoji", ""))[:80],
                    str(data.get("description", ""))[:100],
                    json.dumps(fragen),
                    int(ergebnis_kanal) if ergebnis_kanal.isdigit() else None,
                    erste, accept_roles,
                    team, int(kategorie_id), guild_id,
                ),
            )
            await db.commit()
            return {"category_id": int(kategorie_id)}

        async with db.execute(
            "SELECT COUNT(*) FROM app_categories WHERE panel_id = ?", (panel_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if int(row[0] or 0) >= MAX_CATEGORIES:
            raise ValueError(f"Mehr als {MAX_CATEGORIES} Kategorien gehen nicht.")

        cursor = await db.execute(
            "INSERT INTO app_categories (panel_id, guild_id, name, emoji,"
            " description, questions, results_channel_id, accept_role_id,"
            " accept_roles, staff_roles, position)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                panel_id, guild_id, name, str(data.get("emoji", ""))[:80],
                str(data.get("description", ""))[:100], json.dumps(fragen),
                int(ergebnis_kanal) if ergebnis_kanal.isdigit() else None,
                erste, accept_roles,
                team, int(row[0] or 0),
            ),
        )
        await db.commit()
        return {"category_id": int(cursor.lastrowid)}


async def delete_category(guild_id: int, category_id: int) -> bool:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "DELETE FROM app_categories WHERE category_id = ? AND guild_id = ?",
            (category_id, guild_id),
        )
        await db.commit()
        return bool(cursor.rowcount)


async def get_category(category_id: int) -> dict | None:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT category_id, name, emoji, description, questions,"
            " results_channel_id, accept_role_id, accept_roles,"
            " staff_roles, position, panel_id, guild_id"
            " FROM app_categories WHERE category_id = ?",
            (category_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    eintrag = _category_row(row)
    eintrag["panel_id"] = int(row[9])
    eintrag["guild_id"] = str(row[10])
    return eintrag


async def get_panel(panel_id: int) -> dict | None:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT guild_id FROM app_panels WHERE panel_id = ?", (panel_id,)
        ) as cursor:
            row = await cursor.fetchone()
    if row is None:
        return None
    alle = await list_panels(int(row[0]))
    return next((p for p in alle if p["panel_id"] == panel_id), None)


async def grant_accept_roles(guild, member, kategorie: dict) -> tuple[list, list]:
    """
    Die Rollen beim Annehmen vergeben.

    Gibt ``(vergeben, gescheitert)`` zurueck -- beides Listen von Namen.
    Was scheitert, wird nicht verschwiegen: eine Rolle, die der Bot
    nicht vergeben darf, muss jemand von Hand nachtragen, und dafuer
    muss er davon wissen.

    Steht hier und nicht im Cog, weil zwei Wege annehmen koennen: die
    Knoepfe in Discord und das Dashboard. Zwei Fassungen davon liefen
    frueher oder spaeter auseinander -- eine vergisst die Rolle.
    """
    import discord

    if guild is None or member is None:
        return [], []

    vergeben, gescheitert = [], []
    for rollen_id in kategorie.get("accept_roles") or []:
        if not str(rollen_id).isdigit():
            continue
        rolle = guild.get_role(int(rollen_id))
        if rolle is None:
            gescheitert.append(f"Unbekannte Rolle ({rollen_id})")
            continue
        # Die eigene Rollenordnung vorher pruefen: Discord lehnt sonst
        # mit 403 ab, und der Grund steht nur im Log.
        if guild.me is not None and rolle >= guild.me.top_role:
            gescheitert.append(f"{rolle.name} (steht ueber der Bot-Rolle)")
            continue
        if rolle in member.roles:
            continue
        try:
            await member.add_roles(rolle, reason="Bewerbung angenommen")
            vergeben.append(rolle.name)
        except discord.Forbidden:
            gescheitert.append(f"{rolle.name} (keine Berechtigung)")
        except discord.HTTPException as exc:
            gescheitert.append(f"{rolle.name} ({exc})")

    return vergeben, gescheitert


# ── Laufende Gespraeche ──────────────────────────────────────────────

async def get_session(user_id: int) -> dict | None:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT user_id, guild_id, category_id, question_index, answers,"
            " started_at, last_prompt_at FROM active_sessions WHERE user_id = ?",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    try:
        antworten = json.loads(row[4] or "[]")
    except (ValueError, TypeError):
        antworten = []
    return {
        "user_id": int(row[0]),
        "guild_id": int(row[1]),
        "category_id": int(row[2]),
        "question_index": int(row[3] or 0),
        "answers": antworten,
        "started_at": int(row[5]),
        "last_prompt_at": int(row[6]),
    }


async def start_session(user_id: int, guild_id: int, category_id: int) -> None:
    jetzt = int(time.time())
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "INSERT INTO active_sessions (user_id, guild_id, category_id,"
            " question_index, answers, started_at, last_prompt_at)"
            " VALUES (?, ?, ?, 0, '[]', ?, ?)"
            " ON CONFLICT(user_id) DO UPDATE SET"
            " guild_id = excluded.guild_id, category_id = excluded.category_id,"
            " question_index = 0, answers = '[]',"
            " started_at = excluded.started_at,"
            " last_prompt_at = excluded.last_prompt_at",
            (user_id, guild_id, category_id, jetzt, jetzt),
        )
        await db.commit()


async def record_answer(user_id: int, answer: str) -> dict | None:
    """Eine Antwort ablegen und zur naechsten Frage weiterruecken."""
    sitzung = await get_session(user_id)
    if sitzung is None:
        return None

    antworten = list(sitzung["answers"])
    antworten.append(str(answer or "")[:MAX_ANSWER_LEN])
    jetzt = int(time.time())

    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "UPDATE active_sessions SET question_index = ?, answers = ?,"
            " last_prompt_at = ? WHERE user_id = ?",
            (sitzung["question_index"] + 1, json.dumps(antworten), jetzt, user_id),
        )
        await db.commit()

    sitzung["answers"] = antworten
    sitzung["question_index"] += 1
    sitzung["last_prompt_at"] = jetzt
    return sitzung


async def end_session(user_id: int) -> None:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        await db.execute("DELETE FROM active_sessions WHERE user_id = ?", (user_id,))
        await db.commit()


async def all_sessions() -> list[dict]:
    """
    Jedes laufende Gespraech.

    Wird nach einem Neustart gebraucht: die offene Frage muss noch
    einmal gestellt werden, sonst wartet der Bewerber auf eine
    Nachricht, die nie wieder kommt.
    """
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT user_id, guild_id, category_id, question_index, answers,"
            " started_at, last_prompt_at FROM active_sessions"
        ) as cursor:
            zeilen = await cursor.fetchall()

    ergebnis = []
    for r in zeilen:
        try:
            antworten = json.loads(r[4] or "[]")
        except (ValueError, TypeError):
            antworten = []
        ergebnis.append({
            "user_id": int(r[0]),
            "guild_id": int(r[1]),
            "category_id": int(r[2]),
            "question_index": int(r[3] or 0),
            "answers": antworten,
            "started_at": int(r[5]),
            "last_prompt_at": int(r[6]),
        })
    return ergebnis


async def withdraw(user_id: int) -> dict | None:
    """
    Eine abgeschickte Bewerbung zurueckziehen.

    Ohne das ist blockiert, wer sich vertippt hat: eine offene
    Bewerbung laesst keine zweite zu, und bis das Team entscheidet
    koennen Tage vergehen. Gibt die Bewerbung zurueck, damit der
    Aufrufer die Nachricht im Kanal entwerten kann.
    """
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT id FROM applications WHERE user_id = ? AND status = 'open'"
            " ORDER BY created_at DESC LIMIT 1",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        bewerbung_id = int(row[0])
        await db.execute(
            "UPDATE applications SET status = ?, decided_at = ?"
            " WHERE id = ? AND status = 'open'",
            (STATUS_CANCELLED, int(time.time()), bewerbung_id),
        )
        await db.commit()

    return await get_application(bewerbung_id)


async def stale_sessions(now: int | None = None) -> list[dict]:
    """Gespraeche, in denen zu lange nichts kam."""
    jetzt = int(now if now is not None else time.time())
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT user_id FROM active_sessions WHERE last_prompt_at < ?",
            (jetzt - ANSWER_TIMEOUT,),
        ) as cursor:
            zeilen = await cursor.fetchall()
    return [{"user_id": int(r[0])} for r in zeilen]


# ── Eingereichte Bewerbungen ─────────────────────────────────────────

async def submit(guild_id: int, category_id: int, user_id: int,
                 answers: list[str]) -> int:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        cursor = await db.execute(
            "INSERT INTO applications (guild_id, category_id, user_id, answers,"
            " status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
            (guild_id, category_id, user_id, json.dumps(answers), int(time.time())),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def attach_message(application_id: int, message_id: int) -> None:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        await db.execute(
            "UPDATE applications SET message_id = ? WHERE id = ?",
            (message_id, application_id),
        )
        await db.commit()


async def decide(application_id: int, status: str, decided_by: int,
                 reason: str = "") -> dict | None:
    """
    Annehmen oder ablehnen.

    Gibt die Bewerbung zurueck, oder ``None``, wenn es sie nicht gibt
    oder sie schon entschieden ist -- zwei Teammitglieder koennen
    gleichzeitig auf die Knoepfe druecken.
    """
    if status not in (STATUS_ACCEPTED, STATUS_DENIED):
        raise ValueError("status muss 'accepted' oder 'denied' sein.")

    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        # Die Bedingung auf 'open' ist der Schutz: der zweite Klick
        # aendert nichts mehr und rowcount bleibt null.
        cursor = await db.execute(
            "UPDATE applications SET status = ?, decided_by = ?, decided_at = ?,"
            " reason = ? WHERE id = ? AND status = 'open'",
            (status, decided_by, int(time.time()), str(reason or "")[:1000],
             application_id),
        )
        await db.commit()
        if not cursor.rowcount:
            return None

    return await get_application(application_id)


async def get_application(application_id: int) -> dict | None:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT id, guild_id, category_id, user_id, answers, status,"
            " decided_by, decided_at, reason, message_id, created_at"
            " FROM applications WHERE id = ?",
            (application_id,),
        ) as cursor:
            row = await cursor.fetchone()
    return _application_row(row) if row else None


def _application_row(r) -> dict:
    try:
        antworten = json.loads(r[4] or "[]")
    except (ValueError, TypeError):
        antworten = []
    return {
        "id": int(r[0]),
        "guild_id": str(r[1]),
        "category_id": int(r[2]),
        "user_id": str(r[3]),
        "answers": antworten,
        "status": r[5] or "open",
        "decided_by": str(r[6]) if r[6] else None,
        "decided_at": int(r[7] or 0),
        "reason": r[8] or "",
        "message_id": str(r[9]) if r[9] else None,
        "created_at": int(r[10] or 0),
    }


async def list_applications(guild_id: int, status: str | None = None,
                            limit: int = 100) -> list[dict]:
    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        if status:
            abfrage = (
                "SELECT id, guild_id, category_id, user_id, answers, status,"
                " decided_by, decided_at, reason, message_id, created_at"
                " FROM applications WHERE guild_id = ? AND status = ?"
                " ORDER BY created_at DESC LIMIT ?"
            )
            args: tuple = (guild_id, status, max(1, min(limit, 500)))
        else:
            abfrage = (
                "SELECT id, guild_id, category_id, user_id, answers, status,"
                " decided_by, decided_at, reason, message_id, created_at"
                " FROM applications WHERE guild_id = ?"
                " ORDER BY created_at DESC LIMIT ?"
            )
            args = (guild_id, max(1, min(limit, 500)))

        async with db.execute(abfrage, args) as cursor:
            zeilen = await cursor.fetchall()
    return [_application_row(r) for r in zeilen]


async def has_open_anywhere(user_id: int) -> dict | None:
    """
    Laeuft irgendwo schon eine Bewerbung dieser Person?

    Serveruebergreifend, und das mit Absicht: der Bot fragt in der DM,
    also im selben Gespraechsfenster. Zwei Bewerbungen gleichzeitig
    hiessen, dass niemand mehr weiss, welche Antwort wohin gehoert.
    """
    laufend = await get_session(user_id)
    if laufend is not None:
        return {"kind": "session", **laufend}

    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT id, guild_id, category_id, created_at FROM applications"
            " WHERE user_id = ? AND status = 'open' LIMIT 1",
            (user_id,),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None:
        return None
    return {
        "kind": "pending",
        "id": int(row[0]),
        "guild_id": int(row[1]),
        "category_id": int(row[2]),
        "created_at": int(row[3]),
    }


async def denied_until(user_id: int, category_id: int, cooldown_days: int
                       ) -> int | None:
    """
    Bis wann sperrt eine Ablehnung diese Kategorie?

    ``None`` heisst: frei. Gezaehlt wird ab der letzten Ablehnung in
    genau dieser Kategorie -- eine Absage als Moderator soll niemanden
    daran hindern, sich als Supporter zu bewerben.
    """
    if cooldown_days <= 0:
        return None

    async with db_paths.connect(APP_DB) as db:
        await ensure_schema(db)
        async with db.execute(
            "SELECT decided_at FROM applications WHERE user_id = ?"
            " AND category_id = ? AND status = 'denied'"
            " ORDER BY decided_at DESC LIMIT 1",
            (user_id, category_id),
        ) as cursor:
            row = await cursor.fetchone()

    if row is None or not row[0]:
        return None
    frei_ab = int(row[0]) + cooldown_days * 86400
    return frei_ab if frei_ab > int(time.time()) else None
