"""
Einen Server einlesen und als Vorlage beschreiben.

Was gelesen wird
----------------
* **Kategorien und Kanaele** -- Name, Art, Thema, Reihenfolge, ob
  langsam geschrieben werden muss, ob NSFW.
* **Rollen** -- Name, Farbe, ob sie getrennt angezeigt wird, ob man
  sie erwaehnen darf, ihre Rechte.
* **Rechte je Kanal** -- welche Rolle darf was, wo weicht ein Kanal
  von der Serverregel ab.
* **Dashboard-Einstellungen** -- was in den Feature-Tabellen des Bots
  fuer diesen Server steht.

Wie Verweise ueberleben
-----------------------
Ein Kanal, der auf eine Rolle zeigt, kann seine ID nicht mitnehmen --
auf einem fremden Server gibt es sie nicht. Statt der ID steht in der
Vorlage ein Platzhalter mit dem *Namen*:

    "moderator_role_id": 1530378233579704370
    ->
    "moderator_role_id": "{role:Moderator}"

Beim Anwenden wird daraus wieder eine echte ID, sobald die Rolle
angelegt ist. Namen sind nicht eindeutig -- zwei Rollen koennen gleich
heissen -- aber sie sind das Einzige, was einen Server ueberlebt.

Warum die Rechte als Namen und nicht als Zahlen abgelegt werden
---------------------------------------------------------------
Discords Rechte sind ein Bitfeld. Eine Zahl wie 137411140374080 sagt
niemandem etwas, und wenn Discord ein Recht hinzufuegt, verschiebt
sich nichts -- aber niemand koennte die Vorlage lesen und pruefen, was
sie tut. Als Liste von Namen ist beides moeglich.
"""

from __future__ import annotations

from typing import Any

# Die Kanalarten, die eine Vorlage anlegen kann. Alles andere --
# Threads, Foren-Beitraege, Stage-Instanzen -- entsteht zur Laufzeit
# und gehoert nicht in eine Struktur.
CHANNEL_KINDS = {
    0: "text",
    2: "voice",
    4: "category",
    5: "news",
    13: "stage",
    15: "forum",
}

# Welche Feature-Tabellen zu welchem Reiter gehoeren. Der Schluessel
# ist, was im Dashboard angezeigt wird.
#
# Bewusst eine feste Liste statt "alles, was eine guild_id-Spalte hat":
# so kann keine neue Tabelle versehentlich mitgehen, ohne dass jemand
# geprueft hat, was darin steht.
FEATURE_TABLES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    # Schluessel        Anzeigename          Datei                  Tabellen
    #
    # Die Reihenfolge hier bestimmt die Reihenfolge im Dashboard.
    # Gruppiert nach dem, was im Reiter zusammengehoert.

    # ── Begruessung und Eintritt ────────────────────────────────
    "welcome": ("Willkommensnachricht", "db/welcome.db", ("welcome",)),
    # Panels, Kategorien und Fragen gehen mit. Die eingereichten
    # Bewerbungen und laufenden Gespraeche NICHT: das sind Daten
    # von Menschen, keine Einstellungen -- sie haetten auf einem
    # fremden Server nichts verloren.
    "applications": ("Bewerbungen", "db/applications.db",
                     ("app_panels", "app_categories")),
    # Der Abschied liegt in greet_extras -- zusammen mit dem
    # Bild-Schalter der Begruessung, die teilen sich eine Zeile.
    # Beim Uebertragen einer Vorlage gehen sie deshalb gemeinsam mit.
    # Bild-Schalter und Abschied liegen zusammen in einer Zeile von
    # greet_extras. Beide Reiter zeigen auf dieselbe Tabelle: sie
    # teilen sich den Datensatz, und beim Uebertragen einer Vorlage
    # gehen sie deshalb gemeinsam mit.
    "leave": ("Abschied", "db/greet_extras.db", ("greet_extras",)),
    "joindm": ("Willkommens-DM", "db/joindm.db", ("joindm",)),
    "autorole": ("Autorolle", "db/autorole.db", ("autorole",)),
    "verification": (
        "Verifizierung", "db/verification.db", ("verification_config",)
    ),

    # ── Sicherheit ──────────────────────────────────────────────
    "automod": (
        "Automod", "db/automod.db",
        ("automod", "automod_config", "automod_ignored", "automod_logging",
         "automod_punishments", "automod_rules"),
    ),
    "antinuke": (
        "Anti-Nuke", "db/anti.db", ("antinuke", "limit_settings", "punishment")
    ),
    "logging": ("Logs", "db/logging.db", ("logging",)),

    # ── Mitmachen ───────────────────────────────────────────────
    "leveling": (
        "Leveling", "db/leveling.db",
        ("leveling_settings", "level_rewards", "level_multipliers",
         "level_excluded"),
    ),
    "autoreact": ("Auto-Reaktionen", "db/autoreact.db", ("autoreact",)),
    "teamlist": (
        "Teamliste", "db/teamlist.db", ("teamlist", "teamlist_groups")
    ),
    # Team-Update: Einstellungen und Vorlagen gehen mit. Die Akte
    # NICHT -- wer wann befoerdert oder verwarnt wurde, sind Daten von
    # Menschen und haetten auf einem fremden Server nichts verloren.
    "teamupdate": (
        "Team-Update", "db/team_update.db", ("team_settings", "team_templates")
    ),

    # ── Rollen ──────────────────────────────────────────────────
    "vanityroles": ("Status-Rollen", "db/vanity.db", ("vanity_roles",)),
    "customroles": ("Eigene Rollen", "db/customrole.db", ("roles",)),
    "invcrole": ("Sprachkanal-Rollen", "db/invc.db", ("vcroles",)),
    "noprefix": ("Ohne Praefix", "db/np.db", ("np_roles",)),
    "nickname": ("Spitznamen-Regeln", "db/nickname.db", ("nickname_rules",)),

    # ── Kanaele ─────────────────────────────────────────────────
    "j2c": ("Join to Create", "db/j2c.db", ("j2c",)),
    "anonchat": ("Anonymer Chat", "db/anonchat.db", ("anon_channels",)),
    "tickets": (
        "Tickets", "db/ticket.db", ("guild_configs", "ticket_categories")
    ),
    "supportqueue": (
        "Support-Warteraum", "db/support_queue.db", ("support_queue",)
    ),

    # ── Sonstiges ───────────────────────────────────────────────
    "music": (
        "Musik", "db/music.db", ("music_settings", "music_playlists")
    ),
    "prefix": ("Befehls-Praefix", "db/prefix.db", ("prefixes",)),
    "settings": (
        "Server-Einstellungen", "db/settings.db", ("guild_extra_settings",)
    ),
    "invites": ("Einladungs-Logs", "db/invite.db", ("logging",)),
}

# Wozu eine Funktion gehoert -- fuer die Anzeige im Dashboard.
#
# Bei sechs Eintraegen war eine flache Liste in Ordnung. Bei
# dreiundzwanzig sucht man darin, und beim Abwaehlen uebersieht man
# etwas. Die Gruppen sind dieselben wie in der Seitenleiste, damit man
# nicht zweimal umdenken muss.
FEATURE_GROUPS: dict[str, str] = {
    "welcome": "Begrüßung",
    "applications": "Begrüßung",
    "leave": "Begrüßung",
    "joindm": "Begrüßung",
    "autorole": "Begrüßung",
    "verification": "Begrüßung",

    "automod": "Sicherheit",
    "antinuke": "Sicherheit",
    "logging": "Sicherheit",

    "leveling": "Mitmachen",
    "autoreact": "Mitmachen",
    "teamlist": "Mitmachen",
    "teamupdate": "Mitmachen",

    "vanityroles": "Rollen",
    "customroles": "Rollen",
    "invcrole": "Rollen",
    "noprefix": "Rollen",
    "nickname": "Rollen",

    "j2c": "Kanäle",
    "anonchat": "Kanäle",
    "tickets": "Kanäle",
    "supportqueue": "Kanäle",

    "music": "Sonstiges",
    "prefix": "Sonstiges",
    "settings": "Sonstiges",
    "invites": "Sonstiges",
}

# In welcher Reihenfolge die Gruppen erscheinen.
GROUP_ORDER = (
    "Begrüßung", "Sicherheit", "Mitmachen", "Rollen", "Kanäle", "Sonstiges"
)


# Was NIEMALS mitgeht, auch wenn es eine guild_id-Spalte hat.
#
# Das sind Nutzerdaten, keine Einstellungen: die XP jedes Mitglieds,
# wer wann verwarnt wurde, welche Tickets offen sind, wer gerade eine
# Status-Rolle traegt. Eine Vorlage gibt den *Aufbau* eines Servers
# weiter -- nicht die Leute darin.
#
# Die Liste ist bewusst dieselbe wie in `api/config_transfer.py`: dort
# steht sie seit Langem und ist geprueft. Zwei Listen fuer dieselbe
# Frage liefen frueher oder spaeter auseinander, und ausgerechnet hier
# waere das ein Datenleck -- eine hochgeladene Vorlage ist oeffentlich.
#
# `custom_roles` steht dort drin (Rolle je Mitglied), die Tabelle
# `roles` desselben Bestands dagegen ist die Einstellung -- deshalb
# geht oben nur `roles` mit.
NEVER_EXPORT = frozenset(
    {
        "vanity_holders",
        "anon_log",
        "anon_blocked",
        "levels",
        "user_xp",
        "warns",
        "warn_log",
        "open_tickets",
        "user_ticket_counts",
        "verification_logs",
        "custom_roles",
        "np",
        "whitelisted_users",
        "nuke_incidents",
        "restore_roles",
        "role_positions",
        "command_usage",
        "template_applies",
        "template_votes",
        # Die Team-Akte: wer wann befoerdert, verwarnt oder aus dem
        # Team genommen wurde. Personenbezogen -- eine hochgeladene
        # Vorlage ist oeffentlich, und auf einem fremden Server
        # staenden diese Leute ploetzlich in dessen Team.
        "team_members",
        "team_events",
        "team_warns",
        # Global, nicht je Server.
        "guild_blacklist",
        "user_blacklist",
        "broadcast_targets",
    }
)

# Spalten, die beim Uebernehmen NICHT mitgeschrieben werden.
#
# Sie zeigen auf etwas, das es auf dem Zielserver nicht gibt: die ID
# einer abgeschickten Nachricht, ein Zeitstempel von damals. Sie
# blieben sonst stehen und der Bot suchte nach einer Nachricht, die
# nie existierte -- das faellt erst auf, wenn eine Funktion still
# nicht mehr geht.
DROP_COLUMNS = frozenset(
    {
        "message_id",
        "panel_message_id",
        "created_at",
        "updated_at",
        "last_used",
        "current_status",
    }
)


def _permission_names(permissions) -> list[str]:
    """Ein Rechte-Bitfeld in lesbare Namen.

    Nur die gesetzten. Eine Liste aller 50 Rechte mit true/false waere
    dreimal so gross und genauso aussagekraeftig.
    """

    out = []
    try:
        for name, value in permissions:
            if value:
                out.append(name)
    except TypeError:
        return []
    return sorted(out)


def _colour_hex(colour) -> str | None:
    """Discords Farbe als #rrggbb.

    Rolle ohne Farbe heisst in Discord "0" und wird als *keine* Farbe
    behandelt -- nicht als Schwarz. Deshalb None statt "#000000".
    """

    try:
        value = int(getattr(colour, "value", colour) or 0)
    except (TypeError, ValueError):
        return None
    if value == 0:
        return None
    return f"#{value:06x}"


def scan_roles(guild) -> list[dict]:
    """Alle Rollen -- ausser @everyone und Bot-Rollen.

    @everyone gibt es auf jedem Server schon. Bot-Rollen ("managed")
    legt Discord selbst an, sobald der Bot eingeladen wird; sie
    nachzubauen ginge gar nicht.
    """

    roles = []
    for role in reversed(getattr(guild, "roles", [])):
        if getattr(role, "is_default", lambda: False)():
            continue
        if getattr(role, "managed", False):
            continue

        roles.append(
            {
                "name": role.name,
                "colour": _colour_hex(getattr(role, "colour", None)),
                "hoist": bool(getattr(role, "hoist", False)),
                "mentionable": bool(getattr(role, "mentionable", False)),
                "permissions": _permission_names(getattr(role, "permissions", [])),
                "position": int(getattr(role, "position", 0)),
            }
        )
    return roles


def _overwrites(channel) -> list[dict]:
    """Abweichende Rechte eines Kanals.

    Nur die Rollen -- Rechte fuer einzelne Mitglieder sind an eine
    Person gebunden und auf einem fremden Server sinnlos.
    """

    import discord

    out = []
    for target, overwrite in (getattr(channel, "overwrites", {}) or {}).items():
        if not isinstance(target, discord.Role):
            continue

        allow, deny = [], []
        for name, value in overwrite:
            if value is True:
                allow.append(name)
            elif value is False:
                deny.append(name)

        if not allow and not deny:
            continue

        label = (
            "@everyone"
            if getattr(target, "is_default", lambda: False)()
            else target.name
        )
        out.append({"role": label, "allow": sorted(allow), "deny": sorted(deny)})
    return out


def scan_channels(guild) -> tuple[list[dict], list[dict]]:
    """Kategorien und Kanaele, in ihrer Reihenfolge."""

    categories = []
    for category in getattr(guild, "categories", []):
        categories.append(
            {
                "name": category.name,
                "position": int(getattr(category, "position", 0)),
                "overwrites": _overwrites(category),
            }
        )

    channels = []
    for channel in getattr(guild, "channels", []):
        kind = CHANNEL_KINDS.get(int(getattr(channel.type, "value", -1)))
        if kind is None or kind == "category":
            continue

        entry = {
            "name": channel.name,
            "kind": kind,
            "category": (
                channel.category.name if getattr(channel, "category", None) else None
            ),
            "position": int(getattr(channel, "position", 0)),
            "overwrites": _overwrites(channel),
        }

        topic = getattr(channel, "topic", None)
        if topic:
            entry["topic"] = str(topic)[:1024]
        if getattr(channel, "nsfw", False):
            entry["nsfw"] = True
        slowmode = int(getattr(channel, "slowmode_delay", 0) or 0)
        if slowmode:
            entry["slowmode"] = slowmode
        limit = int(getattr(channel, "user_limit", 0) or 0)
        if limit:
            entry["user_limit"] = limit

        channels.append(entry)

    return categories, channels


def id_labels(guild) -> dict[int, str]:
    """Nachschlagewerk: ID -> lesbarer Platzhalter.

    Wird der Bereinigung mitgegeben, damit aus einer Kanal-ID in den
    Einstellungen `{channel:allgemein}` wird statt nur `{id}`. Beim
    Anwenden laesst sich daraus der neue Kanal finden.
    """

    labels: dict[int, str] = {}
    for channel in getattr(guild, "channels", []):
        labels[int(channel.id)] = f"channel:{channel.name}"
    for role in getattr(guild, "roles", []):
        if getattr(role, "is_default", lambda: False)():
            labels[int(role.id)] = "role:@everyone"
        else:
            labels[int(role.id)] = f"role:{role.name}"
    labels[int(guild.id)] = "guild"
    return labels


async def scan_features(guild_id: int) -> dict[str, Any]:
    """Die Dashboard-Einstellungen dieses Servers.

    Liest jede bekannte Feature-Tabelle. Fehlt eine Datei -- weil das
    Feature nie benutzt wurde -- wird sie uebersprungen, nicht als
    Fehler behandelt.

    Die Werte sind hier noch **roh**. Bereinigt wird eine Ebene
    darueber, in einem Zug mit allem anderen: so gibt es genau eine
    Stelle, an der Geheimnisse herausfallen, und nicht sechs.
    """

    import os

    import aiosqlite

    out: dict[str, Any] = {}

    for key, (label, path, tables) in FEATURE_TABLES.items():
        if not os.path.isfile(path):
            continue

        rows: dict[str, list[dict]] = {}
        try:
            async with aiosqlite.connect(path) as db:
                db.row_factory = aiosqlite.Row
                for table in tables:
                    # Der Riegel gegen Nutzerdaten -- hier, nicht nur
                    # in der Liste oben.
                    #
                    # Die Liste ist von Hand gepflegt; ein Tippfehler
                    # oder eine spaeter dazugeschriebene Zeile brächte
                    # sonst die XP jedes Mitglieds in eine
                    # oeffentliche Vorlage. Zwei Stellen, die
                    # unabhaengig voneinander dasselbe verhindern.
                    if table in NEVER_EXPORT:
                        continue
                    try:
                        async with db.execute(
                            f"SELECT * FROM {table} WHERE guild_id = ?", (guild_id,)
                        ) as cursor:
                            found = await cursor.fetchall()
                    except Exception:
                        # Tabelle gibt es (noch) nicht oder sie hat
                        # keine guild_id-Spalte. Kein Grund, den
                        # ganzen Scan abzubrechen.
                        continue
                    if found:
                        # Spalten, die auf dem Zielserver ins Leere
                        # zeigen, gar nicht erst mitnehmen.
                        rows[table] = [
                            {
                                column: value
                                for column, value in dict(entry).items()
                                if column not in DROP_COLUMNS
                            }
                            for entry in found
                        ]
        except Exception:
            continue

        if rows:
            out[key] = {"label": label, "tables": rows}

    return out


def describe_features(features: dict) -> list[dict]:
    """Eine lesbare Aufstellung: was ist eingestellt?

    Fuer den Reiter "Dashboard erweitert". Dort soll man sehen, welche
    Funktionen die Vorlage mitbringt, und jede einzeln abwaehlen
    koennen -- ohne die rohen Tabellenzeilen lesen zu muessen.
    """

    out = []
    for key, block in (features or {}).items():
        tables = block.get("tables") or {}
        count = sum(len(rows) for rows in tables.values())
        out.append(
            {
                "key": key,
                "label": block.get("label") or key,
                "entries": count,
                # Wozu die Funktion gehoert. Bei sechs Eintraegen war
                # eine flache Liste in Ordnung; bei dreiundzwanzig
                # sucht man darin.
                "group": FEATURE_GROUPS.get(key, "Sonstiges"),
                # Welche Tabellen dahinterstecken -- fuer den Fall,
                # dass jemand genau wissen will, was uebernommen wird.
                "tables": sorted(tables),
            }
        )

    # Nach Gruppe, dann nach Name. Die Reihenfolge der Gruppen kommt
    # aus `GROUP_ORDER`, nicht alphabetisch: "Begruessung" gehoert
    # nach oben, "Sonstiges" nach unten.
    return sorted(
        out,
        key=lambda item: (
            GROUP_ORDER.index(item["group"])
            if item["group"] in GROUP_ORDER
            else len(GROUP_ORDER),
            item["label"].lower(),
        ),
    )


async def build_payload(guild, *, include_features: bool = True) -> dict:
    """Den ganzen Server als Vorlage.

    Noch **unbereinigt** -- das macht der Aufrufer, damit es genau
    eine Stelle gibt, an der Geheimnisse herausfallen.
    """

    categories, channels = scan_channels(guild)
    roles = scan_roles(guild)

    payload: dict[str, Any] = {
        "version": 1,
        "source": {
            "name": guild.name,
            "member_count": int(getattr(guild, "member_count", 0) or 0),
        },
        "categories": categories,
        "channels": channels,
        "roles": roles,
        "features": {},
    }

    if include_features:
        payload["features"] = await scan_features(int(guild.id))

    return payload
