# ╔══════════════════════════════════════════════════════════════════╗
# ║   Befehlsverzeichnis                                             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Alle Befehle des Bots, fuer die oeffentliche Seite ``/commands``.

Eine Route:

  GET /  jeder Befehl mit Kategorie, Beschreibung, Aliasen und der
         Angabe, ob es ihn als Slash-Befehl gibt

Warum aus dem laufenden Bot und nicht aus einer Liste
-----------------------------------------------------
Eine gepflegte Liste ist am Tag nach dem naechsten neuen Befehl
falsch. Hier wird ``bot.walk_commands()`` und der Slash-Baum
befragt -- was der Bot anbietet, steht auf der Seite, ohne dass
jemand daran denken muss.

Die »besten 100«
----------------
Sortiert nach echter Nutzung aus ``command_stats``. Solange dort
nichts steht -- frischer Deploy, leere Datenbank --, faellt die
Reihenfolge auf eine handverlesene Rangfolge der Kategorien zurueck.
Beides zusammen, damit die Seite nie leer oder zufaellig aussieht.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends

from api.dependencies import get_bot
from utils import command_stats

if TYPE_CHECKING:
    from core.universitybot import universitybot

logger = logging.getLogger(__name__)
router = APIRouter()

# Wie viele oben stehen.
TOP_COUNT = 100

# Cog-Name -> Anzeigename und Rang.
#
# Der Rang entscheidet die Reihenfolge, solange keine Nutzungszahlen
# vorliegen. Kleinere Zahl heisst weiter oben: Moderation und Tickets
# sind das, wofuer der Bot geholt wird; Spiele sind Beiwerk.
KATEGORIEN: dict[str, tuple[str, int]] = {
    "Moderation": ("Moderation", 0),
    "Ban": ("Moderation", 0),
    "Unban": ("Moderation", 0),
    "Kick": ("Moderation", 0),
    "Mute": ("Moderation", 0),
    "Unmute": ("Moderation", 0),
    "Warn": ("Moderation", 0),
    "Lock": ("Moderation", 0),
    "Unlock": ("Moderation", 0),
    "Hide": ("Moderation", 0),
    "Unhide": ("Moderation", 0),
    "Role": ("Moderation", 0),
    "Message": ("Moderation", 0),
    "Jail": ("Moderation", 0),
    "Snipe": ("Moderation", 1),
    "TicketCog": ("Tickets", 1),
    "Applications": ("Bewerbungen", 1),
    "TeamUpdate": ("Team", 1),
    "TeamList": ("Team", 1),
    "Antinuke": ("Schutz", 2),
    "Automod": ("Schutz", 2),
    "Whitelist": ("Schutz", 2),
    "Unwhitelist": ("Schutz", 2),
    "Emergency": ("Schutz", 2),
    "Verification": ("Schutz", 2),
    "Music": ("Musik", 3),
    "Leveling": ("Level", 3),
    "Welcomer": ("Willkommen", 4),
    "greet": ("Willkommen", 4),
    "Giveaway": ("Aktivität", 4),
    "Counting": ("Aktivität", 4),
    "AutoResponder": ("Automatisch", 5),
    "AutoReaction": ("Automatisch", 5),
    "AutoRole": ("Automatisch", 5),
    "Logging": ("Logs", 5),
    "Voice": ("Sprache", 5),
    "Invcrole": ("Sprache", 5),
    "Customrole": ("Rollen", 6),
    "SelfRoles": ("Rollen", 6),
    "General": ("Allgemein", 6),
    "Extra": ("Allgemein", 6),
    "Help": ("Allgemein", 6),
    "Utility": ("Werkzeuge", 7),
    "Embed": ("Werkzeuge", 7),
    "Media": ("Werkzeuge", 7),
    "Steal": ("Werkzeuge", 7),
    "Tracking": ("Werkzeuge", 7),
    "AI": ("KI", 7),
    "Fun": ("Spaß", 8),
    "Games": ("Spiele", 9),
    "Slots": ("Spiele", 9),
    "Blackjack": ("Spiele", 9),
    "Owner": ("Besitzer", 99),
    "Badges": ("Besitzer", 99),
    "Extraowner": ("Besitzer", 99),
    "Blacklist": ("Besitzer", 99),
    "Block": ("Besitzer", 99),
    "Premium": ("Besitzer", 99),

    # Nachgetragen, nachdem ein Durchlauf gegen den echten Bot 164
    # Befehle unter "Sonstiges" zeigte. Die Namen sind aus
    # ``bot.walk_commands()`` abgelesen, nicht geraten -- mehrere
    # Cogs heissen anders, als der Dateiname vermuten laesst
    # (z. B. "Ticket System" mit Leerzeichen, "_leveling" mit
    # Unterstrich).
    "Booster": ("Aktivität", 4),
    "__boost": ("Aktivität", 4),
    "_Counting": ("Aktivität", 4),
    "Ignore": ("Werkzeuge", 7),
    "encryption": ("Werkzeuge", 7),
    "ImageCommands": ("Werkzeuge", 7),
    "Timer": ("Werkzeuge", 7),
    "Stats": ("Werkzeuge", 7),
    "TopCheck": ("Werkzeuge", 7),
    "NoPrefix": ("Rollen", 6),
    "VanityRoles": ("Rollen", 6),
    "ReactionRoles": ("Rollen", 6),
    "Global": ("Allgemein", 6),
    "Ticket System": ("Tickets", 1),
    "TicketNotify": ("Tickets", 1),
    "StaffDMCog": ("Tickets", 1),
    "AnonChat": ("Aktivität", 4),
    "StickyMessage": ("Werkzeuge", 7),
    "_sticky": ("Werkzeuge", 7),
    "JoinDM": ("Willkommen", 4),
    "FastGreet": ("Willkommen", 4),
    "NotifCommands": ("Benachrichtigungen", 5),
    "Nightmode": ("Schutz", 2),
    "FilterCog": ("Schutz", 2),
    "_verify": ("Schutz", 2),
    "JoinToCreate": ("Sprache", 5),
    "_J2C": ("Sprache", 5),
    "inviteTracker": ("Werkzeuge", 7),
    "_ai": ("KI", 7),
    "_leveling": ("Level", 3),
}

# Cogs, deren Befehle niemanden ausserhalb des Teams betreffen.
VERSTECKT = {"Owner", "Badges", "Extraowner", "Blacklist", "Block",
             "Errors", "Guild", "Mention"}


def _kategorie(cog_name: str) -> tuple[str, int]:
    return KATEGORIEN.get(cog_name, ("Sonstiges", 50))


def _slash_namen(bot) -> set[str]:
    """Jeder Name im Slash-Baum, Untergruppen eingeschlossen."""

    from discord import app_commands

    namen: set[str] = set()

    def geh(befehl, eltern=""):
        voll = f"{eltern} {befehl.name}".strip()
        if isinstance(befehl, app_commands.Group):
            for kind in befehl.commands:
                geh(kind, voll)
        else:
            namen.add(voll)

    baum = getattr(bot, "tree", None)
    if baum is None:
        return namen
    try:
        for befehl in baum.get_commands():
            geh(befehl)
    except Exception as exc:  # pragma: no cover - defensiv
        logger.debug(f"[commands] Slash-Baum nicht lesbar: {exc}")
    return namen


@router.get("/", summary="Alle Befehle des Bots")
async def alle(bot: "universitybot" = Depends(get_bot), days: int = 30):
    slash = _slash_namen(bot)

    # Die Nutzungszahlen. Fehlen sie, ist das kein Fehler -- dann
    # zaehlt allein die handverlesene Rangfolge.
    nutzung: dict[str, int] = {}
    try:
        zahlen = await command_stats.summary(days=days)
        for eintrag in zahlen.get("commands", []):
            name = str(eintrag.get("command", "")).lstrip("/")
            nutzung[name] = max(nutzung.get(name, 0), int(eintrag.get("uses", 0)))
    except Exception as exc:
        logger.debug(f"[commands] Nutzung nicht lesbar: {exc}")

    befehle: list[dict] = []
    gesehen: set[str] = set()

    for befehl in bot.walk_commands():
        if befehl.hidden:
            continue
        cog = befehl.cog_name or ""
        if cog in VERSTECKT:
            continue
        name = befehl.qualified_name
        if name in gesehen:
            continue
        gesehen.add(name)

        gruppe, rang = _kategorie(cog)
        beschreibung = (
            (befehl.help or befehl.description or "").strip().split("\n")[0]
        )

        befehle.append({
            "name": name,
            "category": gruppe,
            "rank": rang,
            "description": beschreibung[:200],
            "aliases": list(befehl.aliases or [])[:5],
            "slash": name in slash,
            # Wie viele Pflichtangaben der Befehl braucht -- das
            # Dashboard zeigt daraus die Benutzung.
            "signature": str(befehl.signature or "").strip()[:120],
            "uses": nutzung.get(name, 0),
        })

    # Slash-Befehle, die es nicht als Prefix gibt.
    for name in sorted(slash):
        if name in gesehen:
            continue
        befehle.append({
            "name": name, "category": "Slash", "rank": 8,
            "description": "", "aliases": [], "slash": True,
            "signature": "", "uses": nutzung.get(name, 0),
        })

    # Sortierung: erst nach echter Nutzung, dann nach Rang, dann
    # alphabetisch. Ohne Zahlen greift Stufe zwei -- die Seite sieht
    # also auch auf einem frischen Deploy geordnet aus.
    befehle.sort(key=lambda c: (-c["uses"], c["rank"], c["name"]))

    kategorien: dict[str, int] = {}
    for eintrag in befehle:
        kategorien[eintrag["category"]] = kategorien.get(eintrag["category"], 0) + 1

    return {
        "commands": befehle,
        "total": len(befehle),
        "top_count": min(TOP_COUNT, len(befehle)),
        "categories": [
            {"name": name, "count": anzahl}
            for name, anzahl in sorted(kategorien.items(),
                                       key=lambda x: (-x[1], x[0]))
        ],
        # Ob die Reihenfolge auf echten Zahlen beruht. Die Seite sagt
        # das dazu, statt eine Rangliste zu behaupten, die keine ist.
        "ranked_by_usage": bool(nutzung),
        "prefix": ">",
    }
