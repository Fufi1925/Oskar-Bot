"""
Was der University Bot tut, nachdem der Template-Bot gebaut hat.

Der Template-Bot legt Rollen und Kanaele an, mehr nicht -- er kennt weder
Verify noch Tickets noch die Anti-Nuke. Diese Datei ist der zweite
Halbschritt: aus dem fertigen Geruest wird ein eingerichteter Server.

Zwei Entscheidungen, die den Aufbau erklaeren:

  * **Jeder Schritt einzeln, jeder Fehler einzeln.** Ein Schritt, der
    scheitert, darf die folgenden nicht mitreissen. Wenn Tickets an
    einem fehlenden Recht scheitern, sollen Verify und die Logs trotzdem
    stehen -- und im Terminal soll genau die eine Zeile rot sein, nicht
    alles.

  * **Nichts wird geraten.** Welcher Kanal der Verify-Kanal ist, sagt
    der Template-Bot in seiner Uebergabe (``channels.verify``). Ist der
    Wert nicht da, wird der Schritt uebersprungen und gemeldet. Ein
    ``"verify" in channel.name`` waere hier verlockend und falsch: die
    Kanalnamen stehen in Small Caps mit Emoji-Praefix, und ein Fehlgriff
    setzt die Schleuse in den falschen Kanal.

Die Schritte sind einzeln abwaehlbar -- das ist der "erweitert"-Teil im
Dashboard. Was nicht angehakt ist, wird nicht angefasst.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import aiosqlite

# Ein Schritt meldet Fortschritt hierueber. Signatur: (Text, Stufe).
LogHook = Callable[[str, str], Awaitable[None]]


@dataclass
class StepResult:
    key: str
    ok: bool
    detail: str = ""


@dataclass
class HandoverReport:
    steps: list[StepResult] = field(default_factory=list)

    def add(self, key: str, ok: bool, detail: str = "") -> StepResult:
        result = StepResult(key=key, ok=ok, detail=detail)
        self.steps.append(result)
        return result

    @property
    def failed(self) -> list[StepResult]:
        return [s for s in self.steps if not s.ok]

    def as_dict(self) -> dict:
        return {
            "steps": [
                {"key": s.key, "ok": s.ok, "detail": s.detail} for s in self.steps
            ],
            "ok": not self.failed,
        }


# --------------------------------------------------------------------- #
# Die Schritte, die das Dashboard anbietet
# --------------------------------------------------------------------- #
#
# ``default`` ist der Zustand von "Standard: alles". Wer den Baukasten
# aufklappt, sieht genau diese Liste und kann einzeln abwaehlen.

STEPS: dict[str, dict[str, Any]] = {
    "verify": {
        "label": "Verifizierung",
        "description": "Schleuse im Verify-Kanal, Rolle wird nach dem Klick vergeben.",
        "default": True,
        "needs": ["channels.verify", "roles.verified"],
    },
    "logging": {
        "label": "Logs",
        "description": "Jede Log-Art in ihren eigenen Kanal.",
        "default": True,
        "needs": ["log_channels"],
    },
    "antinuke": {
        "label": "Anti-Nuke",
        "description": "Schutz vor Massenlöschungen. Team-Rollen kommen auf die Whitelist.",
        "default": True,
        "needs": [],
    },
    "tickets": {
        "label": "Tickets",
        "description": "Ticket-Panel im Support-Kanal, Team-Rollen als Bearbeiter.",
        "default": True,
        "needs": ["channels.tickets"],
    },
    "welcome": {
        "label": "Begrüßung",
        "description": "Willkommensnachricht im Willkommens-Kanal.",
        "default": True,
        "needs": ["channels.welcome"],
    },
    "autorole": {
        "label": "Auto-Rolle",
        "description": "Neue Mitglieder bekommen sofort die Unverifiziert-Rolle.",
        "default": True,
        "needs": ["roles.unverified"],
    },
    "selfroles": {
        "label": "Rollen-Vergabe",
        "description": "Panel im Rollen-Kanal: jeder gibt sich seine Rollen selbst.",
        "default": True,
        "needs": ["channels.roles", "self_roles"],
    },
    "rules": {
        "label": "Regeln",
        "description": "Regeltext im Regel-Kanal, zum Anpassen gedacht.",
        "default": True,
        "needs": ["channels.rules"],
    },
    "counting": {
        "label": "Zählspiel",
        "description": "Der Zähl-Kanal wird scharf geschaltet und startet bei 1.",
        "default": True,
        "needs": ["channels.counting"],
    },
    "leveling": {
        "label": "Level-System",
        "description": "XP fürs Schreiben, Rangkarte mit Profilbild.",
        "default": True,
        "needs": [],
    },
    "tracking": {
        "label": "Einladungs-Log",
        "description": "Protokolliert, wer wen auf den Server geholt hat.",
        "default": True,
        "needs": [],
    },
    "j2c": {
        "label": "Join to Create",
        "description": "Wer den Sprachkanal betritt, bekommt einen eigenen.",
        "default": True,
        "needs": ["channels.j2c"],
    },
    "automod": {
        "label": "Automod",
        "description": "Spam, Massenpings und Einladungen werden gebremst.",
        # An by default: ein frischer Server ohne Spam-Bremse ist genau
        # das Ziel, das Werbe-Bots suchen. Team-Rollen sind
        # ausgenommen, und die Regeln greifen erst bei echtem Spam --
        # fuenf Nachrichten in zehn Sekunden schreibt niemand aus
        # Versehen.
        "default": True,
        "needs": [],
    },
}


def default_options() -> dict[str, bool]:
    return {key: bool(spec["default"]) for key, spec in STEPS.items()}


def normalise_options(raw: dict | None) -> dict[str, bool]:
    """Was das Dashboard schickt, auf die bekannten Schritte eindampfen.

    Unbekannte Schluessel fliegen raus statt durchgereicht zu werden --
    sonst wuerde ein Tippfehler im Browser stillschweigend nichts tun,
    und niemand koennte sagen, warum der Schritt fehlt.
    """

    options = default_options()
    for key, value in (raw or {}).items():
        if key in STEPS:
            options[key] = bool(value)
    return options


def _dig(data: dict, path: str):
    """``"channels.verify"`` aus dem Uebergabe-Dict holen."""

    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current or None


def missing_for(step: str, handover: dict) -> list[str]:
    """Was diesem Schritt fehlt. Leer heisst: kann laufen."""

    return [
        path
        for path in STEPS[step]["needs"]
        if not _dig(handover, path)
    ]


# --------------------------------------------------------------------- #
# Die einzelnen Schritte
# --------------------------------------------------------------------- #


async def _do_verify(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    from api.db_manager import db_manager
    from utils import verify_store as store

    channel_id = int(_dig(handover, "channels.verify"))
    role_id = int(_dig(handover, "roles.verified"))
    unverified = _dig(handover, "roles.unverified")

    channel = guild.get_channel(channel_id)
    role = guild.get_role(role_id)
    if channel is None or role is None:
        report.add("verify", False, "Kanal oder Rolle sind nicht mehr da.")
        await log("Verify: Kanal oder Rolle fehlt", "error")
        return

    db = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(db)
    settings = await store.save_settings(
        db,
        guild.id,
        {
            "enabled": True,
            "verification_channel_id": channel_id,
            "verified_role_id": role_id,
            "unverified_role_id": int(unverified) if unverified else None,
            "verification_method": "both",
        },
    )

    # Das Panel posten, sonst steht die Schleuse zwar in der Datenbank,
    # aber im Kanal ist nichts zu sehen -- und genau das ist der Zustand,
    # den Leute als "Verify geht nicht" melden.
    cog = bot.get_cog("Verification")
    if cog is None or not hasattr(cog, "build_panel"):
        report.add(
            "verify", False,
            "Eingerichtet, aber das Verify-Modul ist nicht geladen — Panel fehlt.",
        )
        await log("Verify eingerichtet, Panel konnte nicht gepostet werden", "warn")
        return

    try:
        view = cog.build_panel(guild, settings, role)
        message = await channel.send(view=view)
        await store.save_settings(
            db, guild.id,
            {"panel_message_id": message.id, "panel_channel_id": channel.id},
        )
    except Exception as exc:
        report.add("verify", False, f"Panel konnte nicht gepostet werden: {exc}")
        await log(f"Verify: Panel fehlgeschlagen ({type(exc).__name__})", "error")
        return

    report.add("verify", True, f"Schleuse steht in #{channel.name}.")
    await log(f"Verify eingerichtet — Panel in #{channel.name}", "success")


async def _do_logging(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    cog = bot.get_cog("Logging")
    if cog is None:
        report.add("logging", False, "Das Log-Modul ist nicht geladen.")
        await log("Logs: Modul nicht geladen", "error")
        return

    wanted = handover.get("log_channels") or {}
    channels: dict[str, int] = {}
    enabled: dict[str, bool] = {}
    for category, raw_id in wanted.items():
        channel = guild.get_channel(int(raw_id))
        if channel is None:
            continue
        channels[category] = int(raw_id)
        enabled[category] = True

    if not channels:
        report.add("logging", False, "Keiner der Log-Kanäle existiert noch.")
        await log("Logs: keine Kanäle gefunden", "error")
        return

    # Die Log-Kanäle selbst ausnehmen. Ohne das protokolliert jeder
    # Log-Eintrag den nächsten: der Bot schreibt in #nachrichten-logs,
    # das ist eine neue Nachricht, also schreibt er wieder hinein. Ein
    # Server mit zehn Log-Kanälen erzeugt so dauerhaft Grundrauschen.
    ignore_channels = sorted(set(channels.values()))

    await cog._save_log_config(
        guild.id, channels, enabled, ignore_channels, [], [], None
    )

    report.add(
        "logging", True,
        f"{len(channels)} Log-Arten verdrahtet, Log-Kanäle ausgenommen.",
    )
    await log(f"Logs eingerichtet — {len(channels)} Kanäle", "success")


async def _do_antinuke(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    from api.routes.antinuke import COLUMNS, DB_PATH, _ensure_schema

    async with aiosqlite.connect(DB_PATH) as db:
        await _ensure_schema(db)
        await db.execute(
            "INSERT INTO antinuke (guild_id, status) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET status = excluded.status",
            (guild.id, True),
        )

        # Der Server-Inhaber gehoert auf die Whitelist. Ohne ihn sperrt
        # sich der eigene Chef aus, sobald er zehn Kanaele umbenennt.
        owner_id = getattr(guild, "owner_id", None)
        if owner_id:
            columns = ", ".join(COLUMNS)
            values = ", ".join("1" for _ in COLUMNS)
            await db.execute(
                f"INSERT OR REPLACE INTO whitelisted_users "
                f"(guild_id, user_id, {columns}) VALUES (?, ?, {values})",
                (guild.id, int(owner_id)),
            )
        await db.commit()

    report.add("antinuke", True, "Anti-Nuke ist an, Inhaber steht auf der Whitelist.")
    await log("Anti-Nuke aktiviert", "success")


async def _do_tickets(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    from api import ticket_panels as panels
    from api.db_manager import db_manager

    channel_id = int(_dig(handover, "channels.tickets"))
    channel = guild.get_channel(channel_id)
    if channel is None:
        report.add("tickets", False, "Der Ticket-Kanal ist nicht mehr da.")
        await log("Tickets: Kanal fehlt", "error")
        return

    db = await db_manager.get_connection("db/ticket.db")
    await panels.ensure_schema(db)

    staff = [int(r) for r in (handover.get("staff_roles") or [])]

    # Ein zweiter Speedrun darf kein zweites Panel anlegen. Sonst stehen
    # nach zwei Laeufen zwei „Support“-Panels im selben Kanal, und
    # welches davon das aktive ist, sieht man erst am Verhalten.
    existing = await panels.list_panels(db, guild.id)
    mine = next(
        (p for p in existing if str(p.get("channel_id") or "") == str(channel_id)),
        None,
    )
    panel_id = (
        int(mine["panel_id"])
        if mine
        else await panels.create_panel(db, guild.id, "Support")
    )

    from utils import emoji as emoji_set

    # Die Discord-Kategorie, unter der die Ticket-Kanäle entstehen.
    #
    # Ohne sie bricht jeder Klick auf den Ticket-Knopf ab: der Cog liest
    # `discord_category_id`, findet nichts und antwortet "This ticket
    # category has been deleted or is misconfigured". Genau das war der
    # Fehler -- das Panel stand da und tat beim Öffnen nichts.
    ticket_home = getattr(channel, "category", None)

    await panels.update_panel(
        db, guild.id, panel_id,
        {
            "channel_id": channel_id,
            # Dropdown statt Knöpfe: die Liste bleibt auch mit mehreren
            # Kategorien lesbar, und Discord erlaubt nur fünf Knöpfe je
            # Reihe.
            "panel_type": "dropdown",
            "embed_title": f"{emoji_set.TICKET}  Support",
            "embed_description": (
                "Du brauchst Hilfe? Wähle unten aus, worum es geht — "
                "nur du und das Team sehen das Ticket."
            ),
            "staff_roles": staff,
        },
    )

    # Die Kategorien. Jede braucht die Team-Rollen (wer wird
    # benachrichtigt und darf mitlesen) und die Discord-Kategorie, unter
    # der der Kanal angelegt wird.
    #
    # Jedes Emoji genau einmal: zwei gleiche im selben Dropdown kann man
    # nicht auseinanderhalten.
    wanted = [
        ("Allgemeine Frage", emoji_set.INFO),
        ("Problem melden", emoji_set.WARNING),
        ("Beschwerde", emoji_set.SWORD),
    ]
    existing_names = {
        str(entry.get("name")) for entry in ((mine or {}).get("categories") or [])
    }
    for name, icon in wanted:
        if name in existing_names:
            continue
        await panels.upsert_category(
            db, guild.id, panel_id,
            {
                "name": name,
                "emoji": icon,
                "staff_roles": staff,
                "discord_category_id": ticket_home.id if ticket_home else None,
            },
        )

    # Die Übersicht im Dashboard liest guild_configs, nicht
    # ticket_panels. Ohne eine Zeile dort stand "Tickets" als "nicht
    # eingerichtet" da, obwohl das Panel im Kanal hing.
    await db.execute(
        "INSERT INTO guild_configs (guild_id, panel_channel_id, staff_roles)"
        " VALUES (?, ?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET"
        "  panel_channel_id = excluded.panel_channel_id,"
        "  staff_roles = excluded.staff_roles",
        (guild.id, channel_id, ",".join(str(r) for r in staff)),
    )
    await db.commit()

    # Und das Panel gleich posten. Es nur anzulegen hiess: der Kanal
    # bleibt leer, und man muesste den Reiter „Tickets“ suchen, um den
    # letzten Klick zu machen. Ein Speedrun, der auf halbem Weg stehen
    # bleibt, ist keiner.
    posted = await _post_ticket_panel(bot, guild, channel, db, panel_id)
    if posted:
        report.add("tickets", True, f"Panel steht in #{channel.name}.")
        await log(f"Tickets eingerichtet — Panel in #{channel.name}", "success")
    else:
        report.add(
            "tickets", False,
            f"Angelegt, aber das Panel ließ sich nicht in #{channel.name} "
            "posten. Nachholen im Reiter „Tickets“.",
        )
        await log(f"Tickets: Panel in #{channel.name} nicht gepostet", "warn")


async def _post_ticket_panel(bot, guild, channel, db, panel_id: int) -> bool:
    """Das Ticket-Panel in den Kanal stellen.

    Baut dieselbe View wie die Route ``/tickets/{guild}/panels/{id}/send``
    -- ein zweiter Nachbau der Knopf-Logik wuerde irgendwann von ihr
    abweichen, und dann verhielte sich der Speedrun anders als der
    Reiter.
    """

    import discord

    from api import ticket_panels as panels
    from utils.panels import ACCENT, Panel

    entries = await panels.list_panels(db, guild.id)
    panel = next((p for p in entries if p["panel_id"] == panel_id), None)
    if panel is None or not panel.get("categories"):
        return False

    # Knoepfe oder Dropdown -- genau das, was in panel_type steht.
    #
    # Hier wurden unbedingt Knoepfe gebaut, waehrend die Datenbank
    # "dropdown" sagte. Das Dashboard zeigte also ein Dropdown an und in
    # Discord standen Knoepfe. Schlimmer noch: der Cog baut die View
    # nach einem Neustart aus panel_type neu -- die Nachricht haette
    # nach dem naechsten Deploy anders ausgesehen als vorher.
    if (panel.get("panel_type") or "button") == "dropdown":
        controls = [
            discord.ui.Select(
                placeholder="Wähle eine Kategorie…",
                custom_id="create_ticket_select",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(
                        label=category["name"][:100],
                        value=str(category["category_id"]),
                        emoji=category["emoji"] or None,
                    )
                    # Discord erlaubt hoechstens 25 Eintraege.
                    for category in panel["categories"][:25]
                ],
            )
        ]
    else:
        controls = []
        for category in panel["categories"]:
            try:
                style = discord.ButtonStyle(int(category["button_style"]))
            except (ValueError, TypeError):
                style = discord.ButtonStyle.secondary
            controls.append(
                discord.ui.Button(
                    label=category["name"][:80],
                    emoji=category["emoji"] or None,
                    style=style,
                    custom_id=f"create_ticket_{category['category_id']}",
                )
            )

    view = Panel(
        panel["embed_title"] or panel["name"],
        panel["embed_description"] or "Klicke unten, um ein Ticket zu öffnen.",
        accent=panel["embed_color"] or ACCENT["brand"],
        buttons=controls,
    )

    try:
        message = await channel.send(view=view)
    except (discord.Forbidden, discord.HTTPException):
        return False

    await panels.set_message_id(db, guild.id, panel_id, message.id)
    # Ohne das hören die Knöpfe nach einem Neustart auf zu reagieren.
    try:
        bot.add_view(view, message_id=message.id)
    except Exception:
        pass
    return True


async def _do_welcome(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    channel_id = int(_dig(handover, "channels.welcome"))
    channel = guild.get_channel(channel_id)
    if channel is None:
        report.add("welcome", False, "Der Willkommens-Kanal ist nicht mehr da.")
        await log("Begrüßung: Kanal fehlt", "error")
        return

    async with aiosqlite.connect("db/welcome.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS welcome ("
            " guild_id INTEGER PRIMARY KEY, welcome_type TEXT,"
            " welcome_message TEXT, channel_id INTEGER,"
            " embed_data TEXT, auto_delete_duration INTEGER)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO welcome"
            " (guild_id, welcome_type, welcome_message, channel_id,"
            "  embed_data, auto_delete_duration)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                guild.id,
                "embed",
                "Willkommen auf **{server_name}**, {user}!",
                channel_id,
                json.dumps(
                    {
                        # Autorenzeile: Servername plus Servericon. Sie
                        # steht über dem Titel und macht die Nachricht
                        # sichtbar zu einer des Servers.
                        #
                        # Flache Schlüssel, kein verschachteltes Objekt:
                        # build_embed() liest "author_name"/"author_icon".
                        # Ein {"author": {...}} hätte es kommentarlos
                        # ignoriert -- die Zeile wäre einfach weggeblieben.
                        "author_name": "{server_name}",
                        "author_icon": "{server_icon}",
                        "title": "Willkommen!",
                        "description": (
                            "Schön, dass du da bist, {user}!\n\n"
                            "Du bist Mitglied Nummer "
                            "**{server_membercount}** auf "
                            "**{server_name}**.\n"
                            "Verifiziere dich, dann siehst du den ganzen Server."
                        ),
                        # Kleingedrucktes unten, wie bei einem Embed.
                        "footer_text": "by University Bot",
                    }
                ),
                None,
            ),
        )
        await db.commit()

    report.add("welcome", True, f"Begrüßung geht nach #{channel.name}.")
    await log(f"Begrüßung eingerichtet — #{channel.name}", "success")


async def _do_autorole(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    role_id = int(_dig(handover, "roles.unverified"))
    role = guild.get_role(role_id)
    if role is None:
        report.add("autorole", False, "Die Unverifiziert-Rolle ist nicht mehr da.")
        await log("Auto-Rolle: Rolle fehlt", "error")
        return

    me = guild.me
    if me is not None and role >= me.top_role:
        report.add(
            "autorole", False,
            f"„{role.name}“ steht über der Bot-Rolle — der Bot kann sie nicht vergeben.",
        )
        await log("Auto-Rolle: Rolle steht zu hoch", "error")
        return

    async with aiosqlite.connect("db/autorole.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS autorole ("
            " guild_id INTEGER PRIMARY KEY,"
            " bots TEXT NOT NULL DEFAULT '[]',"
            " humans TEXT NOT NULL DEFAULT '[]')"
        )
        # Das Cog liest diese Spalten als Python-Listen-Literal ein --
        # str([...]) ist hier also das erwartete Format, kein JSON.
        await db.execute(
            "INSERT OR REPLACE INTO autorole (guild_id, bots, humans)"
            " VALUES (?, ?, ?)",
            (guild.id, str([]), str([role_id])),
        )
        await db.commit()

    report.add("autorole", True, f"Neue Mitglieder bekommen „{role.name}“.")
    await log(f"Auto-Rolle eingerichtet — {role.name}", "success")


async def _do_automod(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    from api.db_manager import db_manager
    from utils import automod_store as store

    db = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(db)
    await store.save_settings(
        db,
        guild.id,
        {
            "enabled": True,
            "rules": {
                "spam": {"enabled": True},
                "mentions": {"enabled": True},
                "invites": {"enabled": True},
            },
            "ignored_roles": [int(r) for r in (handover.get("staff_roles") or [])],
        },
    )

    report.add("automod", True, "Spam, Massenpings und Einladungen sind aus.")
    await log("Automod eingerichtet", "success")


async def _do_selfroles(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    """Das Rollen-Panel posten und die Reaktionen eintragen.

    Der Template-Bot hatte hier fruher ein eigenes Dropdown. Das ist
    weggefallen, weil der Hauptbot die Rollen fuehrt -- ohne diesen
    Schritt blieb der Kanal danach aber leer. Das war mein Fehler: die
    alte Loesung entfernt, die neue nicht gebaut.
    """

    import discord

    from cogs.events import selfroles
    from utils import emoji as emoji_set
    from utils.panels import ACCENT, Panel

    channel_id = int(_dig(handover, "channels.roles"))
    channel = guild.get_channel(channel_id)
    if channel is None:
        report.add("selfroles", False, "Der Rollen-Kanal ist nicht mehr da.")
        await log("Rollen-Vergabe: Kanal fehlt", "error")
        return

    me = guild.me
    if me is not None and not me.guild_permissions.manage_roles:
        report.add("selfroles", False, "Dem Bot fehlt „Rollen verwalten“.")
        await log("Rollen-Vergabe: Recht fehlt", "error")
        return

    # Nur Rollen, die der Bot auch vergeben kann. Eine Rolle ueber der
    # Bot-Rolle laesst sich anklicken und passiert nichts -- schlimmer
    # als sie wegzulassen.
    usable = []
    for entry in handover.get("self_roles") or []:
        role = guild.get_role(int(entry["id"]))
        if role is None or role.managed:
            continue
        if me is not None and role >= me.top_role:
            continue
        usable.append((role, entry.get("emoji") or "🔹"))

    if not usable:
        report.add(
            "selfroles", False,
            "Keine vergebbare Rolle gefunden — stehen sie über der Bot-Rolle?",
        )
        await log("Rollen-Vergabe: keine passende Rolle", "warn")
        return

    # Ein Dropdown statt Reaktionen. Eine Reaktion ist ein einzelnes
    # Emoji -- zwei Rollen mit demselben Emoji kann niemand
    # auseinanderhalten, und von Hand entfernte Reaktionen laufen
    # stillschweigend aus dem Takt. Im Dropdown steht der Name daneben.
    options = []
    seen_emojis: set[str] = set()
    for role, icon in usable:
        # Jedes Emoji nur einmal: doppelte sind im Menü nicht zu
        # unterscheiden, und darum ging es beim Wechsel gerade.
        if icon in seen_emojis:
            icon = None
        elif icon:
            seen_emojis.add(icon)
        try:
            options.append(
                discord.SelectOption(
                    label=role.name[:100],
                    value=str(role.id),
                    emoji=icon or None,
                )
            )
        except Exception:
            # Ein Emoji, das Discord nicht kennt, darf nicht die ganze
            # Rolle kosten.
            options.append(
                discord.SelectOption(label=role.name[:100], value=str(role.id))
            )

    select = discord.ui.Select(
        placeholder="Rollen aussuchen…",
        custom_id=selfroles.CUSTOM_ID,
        min_values=0,
        # Alles gleichzeitig wählbar: abwählen nimmt die Rolle wieder
        # weg, das ist der ganze Bedienablauf.
        max_values=len(options),
        options=options,
    )

    panel = Panel(
        f"{emoji_set.U_ADMIN}  Rollen aussuchen",
        "Wähle unten aus, was auf dich zutrifft.\n"
        "Abwählen nimmt die Rolle wieder weg.",
        accent=ACCENT["brand"],
        buttons=[select],
    )

    try:
        message = await channel.send(view=panel)
    except (discord.Forbidden, discord.HTTPException) as exc:
        report.add("selfroles", False, f"Panel nicht gepostet: {exc}")
        await log("Rollen-Vergabe: Panel fehlgeschlagen", "error")
        return

    # Welche Rollen dieses Panel vergibt. Der Listener liest das beim
    # Klick nach -- ohne diesen Eintrag antwortet er "kennt keine Rollen".
    await selfroles.remember_panel(
        guild.id,
        message.id,
        [(role.id, role.name, icon) for role, icon in usable],
    )

    # Damit die Knöpfe auch nach einem Neustart reagieren.
    try:
        bot.add_view(panel, message_id=message.id)
    except Exception:
        pass

    report.add(
        "selfroles", True,
        f"{len(usable)} Rollen zur Auswahl in #{channel.name}.",
    )
    await log(f"Rollen-Vergabe eingerichtet — {len(usable)} Rollen", "success")


# Ein Regelwerk, das zu jedem Server passt und das man anpassen soll.
# Bewusst kurz: eine Wand aus zwanzig Punkten liest niemand, und was
# niemand liest, kann man auch nicht durchsetzen.
_DEFAULT_RULES = (
    ("Respekt", "Keine Beleidigungen, keine Belästigung, keine Diskriminierung."),
    ("Kein Spam", "Keine Nachrichtenfluten, keine Massenpings, keine Werbung."),
    ("Passende Kanäle", "Schreib dort, wo das Thema hingehört."),
    ("Keine NSFW-Inhalte", "Weder in Nachrichten noch im Profilbild oder Namen."),
    ("Privates bleibt privat", "Keine fremden Daten teilen, auch nicht als Scherz."),
    ("Discord-Regeln gelten", "Die Nutzungsbedingungen von Discord gelten hier auch."),
)


async def _do_rules(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    """Einen Regeltext in den Regel-Kanal stellen."""

    import discord

    from utils import emoji as emoji_set
    from utils.panels import ACCENT, Panel

    channel_id = int(_dig(handover, "channels.rules"))
    channel = guild.get_channel(channel_id)
    if channel is None:
        report.add("rules", False, "Der Regel-Kanal ist nicht mehr da.")
        await log("Regeln: Kanal fehlt", "error")
        return

    body = "\n\n".join(
        f"**{index}. {title}**\n{text}"
        for index, (title, text) in enumerate(_DEFAULT_RULES, start=1)
    )
    panel = Panel(
        f"{emoji_set.REDRULESBOOK}  Regeln auf {guild.name}",
        body + "\n\n*Diese Regeln sind eine Vorlage — passe sie an deinen "
               "Server an.*",
        accent=ACCENT["brand"],
    )

    try:
        await channel.send(view=panel)
    except (discord.Forbidden, discord.HTTPException) as exc:
        report.add("rules", False, f"Regeln nicht gepostet: {exc}")
        await log("Regeln: Posten fehlgeschlagen", "error")
        return

    report.add("rules", True, f"Regeln stehen in #{channel.name} (bitte anpassen).")
    await log(f"Regeln eingerichtet — #{channel.name}", "success")


async def _do_counting(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    """Das Zählspiel scharf schalten.

    Der Template-Bot legt den Kanal an und schreibt eine 1 hinein --
    aber im Hauptbot steht das Spiel auf ``enabled: False`` mit
    ``channel: None``. Ohne diesen Schritt sieht der Kanal fertig aus
    und reagiert auf keine Zahl.
    """

    from utils import extras_store as store

    channel_id = int(_dig(handover, "channels.counting"))
    channel = guild.get_channel(channel_id)
    if channel is None:
        report.add("counting", False, "Der Zähl-Kanal ist nicht mehr da.")
        await log("Zählspiel: Kanal fehlt", "error")
        return

    # Der Template-Bot hat die 1 schon gepostet, also geht es bei 1
    # weiter -- mit current=0 wuerde der Bot die naechste Zahl als 1
    # erwarten und die 2 als Fehler werten.
    store.counting_save(
        guild.id,
        {
            "enabled": True,
            "channel": channel_id,
            "current": 1,
            "mode": "reset",
            "delete_wrong": True,
            "react_success": True,
            "save_record": True,
        },
    )

    report.add("counting", True, f"Zählspiel läuft in #{channel.name}, Stand: 1.")
    await log(f"Zählspiel eingerichtet — #{channel.name}", "success")


# Ab welchem Level welche Rolle. Die Schlüssel sind Rollen-Keys aus der
# Übergabe.
#
# Bewusst flach gehalten: drei Stufen, die ersten beiden früh genug, dass
# man sie in der ersten Woche erreicht. Eine Leiter mit zehn Stufen sieht
# im Dashboard beeindruckend aus und niemand kommt je oben an.
_LEVEL_REWARDS = (
    (5, "member"),
    (15, "active"),
    (30, "vip"),
)


async def _do_leveling(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    from api.db_manager import db_manager
    from utils import leveling_store as store

    db = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(db)
    await store.save_settings(db, guild.id, {"enabled": True})

    # Rollen-Belohnungen. Ohne die sammelt man XP und bekommt nie etwas
    # dafür -- das Level-System ist dann eine Zahl ohne Folgen.
    me = guild.me
    roles = handover.get("roles") or {}
    given, skipped = [], []

    for level, key in _LEVEL_REWARDS:
        raw = roles.get(key)
        if not raw:
            continue
        role = guild.get_role(int(raw))
        if role is None or role.managed:
            continue
        # Eine Rolle über der Bot-Rolle kann er nicht vergeben. Sie
        # einzutragen hieße: beim Levelaufstieg passiert nichts, und
        # niemand weiß warum.
        if me is not None and role >= me.top_role:
            skipped.append(role.name)
            continue
        await store.set_reward(db, guild.id, level, role.id)
        given.append(f"Level {level} → {role.name}")

    detail = "XP fürs Schreiben ist an."
    if given:
        detail += " Belohnungen: " + ", ".join(given) + "."
    if skipped:
        detail += (
            " Nicht eingetragen (stehen über der Bot-Rolle): "
            + ", ".join(skipped)
            + "."
        )

    report.add("leveling", True, detail)
    await log(
        f"Level-System eingerichtet — {len(given)} Rollen-Belohnungen", "success"
    )


async def _do_tracking(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    """Einladungs-Protokoll: wer hat wen geholt.

    Braucht einen Kanal, in den geschrieben wird. Der Einladungs-Log aus
    dem Template ist dafür da; fehlt er, nimmt der Schritt den
    allgemeinen Log-Kanal.
    """

    import aiosqlite

    me = guild.me
    if me is not None and not me.guild_permissions.manage_guild:
        report.add(
            "tracking", False,
            "Dem Bot fehlt „Server verwalten“ — ohne das sieht er keine Einladungen.",
        )
        await log("Einladungs-Log: Recht fehlt", "error")
        return

    # Der eigene Einladungs-Kanal, sonst der Mitglieder-Log.
    logs = handover.get("log_channels") or {}
    raw = _dig(handover, "channels.invite_log") or logs.get("join_leave_events")
    channel = guild.get_channel(int(raw)) if raw else None
    if channel is None:
        report.add("tracking", False, "Kein Kanal für den Einladungs-Log gefunden.")
        await log("Einladungs-Log: kein Kanal", "warn")
        return

    async with aiosqlite.connect("db/invite.db") as db:
        await db.execute(
            "CREATE TABLE IF NOT EXISTS logging ("
            " guild_id INTEGER PRIMARY KEY, channel_id INTEGER)"
        )
        await db.execute(
            "INSERT OR REPLACE INTO logging (guild_id, channel_id) VALUES (?, ?)",
            (guild.id, channel.id),
        )
        await db.commit()

    report.add("tracking", True, f"Einladungs-Log geht nach #{channel.name}.")
    await log(f"Einladungs-Log eingerichtet — #{channel.name}", "success")


async def _do_j2c(bot, guild, handover: dict, report: HandoverReport, log: LogHook):
    from api.db_manager import db_manager
    from utils import voice_store as store

    channel_id = int(_dig(handover, "channels.j2c"))
    channel = guild.get_channel(channel_id)
    if channel is None:
        report.add("j2c", False, "Der Sprachkanal ist nicht mehr da.")
        await log("Join to Create: Kanal fehlt", "error")
        return

    db = await db_manager.get_connection("db/j2c_data.db")
    await store.j2c_ensure(db)

    category = getattr(channel, "category", None)
    await store.j2c_save(
        db,
        guild.id,
        {
            "join_channel_id": channel_id,
            "category_id": category.id if category is not None else None,
        },
    )

    report.add("j2c", True, f"Eigene Sprachkanäle über #{channel.name}.")
    await log(f"Join to Create eingerichtet — #{channel.name}", "success")


_RUNNERS: dict[str, Callable] = {
    "verify": _do_verify,
    "logging": _do_logging,
    "antinuke": _do_antinuke,
    "tickets": _do_tickets,
    "welcome": _do_welcome,
    "autorole": _do_autorole,
    "selfroles": _do_selfroles,
    "rules": _do_rules,
    "counting": _do_counting,
    "leveling": _do_leveling,
    "tracking": _do_tracking,
    "j2c": _do_j2c,
    "automod": _do_automod,
}

# Reihenfolge des Ablaufs. Verify zuerst, weil das der Schritt ist, den
# man im Server sofort sieht; Automod zuletzt, weil er am wenigsten
# dringend ist und am ehesten scheitert.
ORDER = (
    "verify",
    "rules",
    "selfroles",
    "autorole",
    "logging",
    "antinuke",
    "tickets",
    "welcome",
    "counting",
    "leveling",
    "tracking",
    "j2c",
    "automod",
)


async def run_handover(
    bot,
    guild,
    handover: dict,
    options: dict | None = None,
    log: LogHook | None = None,
    on_step: Callable[[str], Awaitable[None]] | None = None,
) -> HandoverReport:
    """Alle gewaehlten Schritte, einer nach dem anderen.

    Ein Schritt, der scheitert, stoppt die anderen nicht. Ohne das waere
    ein fehlendes Recht bei den Tickets genug, damit Verify, Logs und
    Anti-Nuke gar nicht erst versucht werden -- und der Server stuende
    halb eingerichtet da, ohne dass jemand sagen koennte, wo es hakte.
    """

    report = HandoverReport()
    chosen = normalise_options(options)

    async def noop(_text: str, _level: str = "info") -> None:
        return None

    say: LogHook = log or noop

    async def tick(key: str) -> None:
        """Einen erledigten Schritt melden -- egal wie er ausging.

        Auch ein übersprungener oder gescheiterter Schritt ist
        abgearbeitet. Nur die geglückten zu zählen ließe den
        Fortschrittsbalken bei einem unvollständigen Lauf für immer
        unter 100 % stehen.
        """

        if on_step is None:
            return
        try:
            await on_step(key)
        except Exception:  # pragma: no cover - Anzeige darf nie den Lauf kippen
            pass

    for key in ORDER:
        if not chosen.get(key):
            continue

        missing = missing_for(key, handover)
        if missing:
            label = STEPS[key]["label"]
            report.add(
                key, False,
                "Übersprungen — der Template-Bau hat nichts geliefert für: "
                + ", ".join(missing),
            )
            await say(f"{label} übersprungen — {', '.join(missing)} fehlt", "warn")
            await tick(key)
            continue

        try:
            await _RUNNERS[key](bot, guild, handover, report, say)
        except asyncio.CancelledError:
            # Ein Abbruch ist kein Fehler dieses Schritts -- er muss
            # durchgereicht werden, sonst läuft die Einrichtung nach dem
            # Klick auf "Abbrechen" einfach weiter.
            raise
        except Exception as exc:
            # Ein Schritt, der wirft, darf die anderen nicht mitnehmen.
            report.add(key, False, f"{type(exc).__name__}: {exc}")
            await say(
                f"{STEPS[key]['label']}: {type(exc).__name__}: {exc}", "error"
            )
        await tick(key)

    return report
