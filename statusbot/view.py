# ╔══════════════════════════════════════════════════════════════════╗
# ║   The live status message                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The Components V2 message the status bot keeps in the status channel.

One message, edited in place. It is written to be readable at a glance
from a phone notification shade: state first, details after, and no
wording that claims more than was actually measured.

Specifically, it never says "the bot is offline" when all we know is
that we could not reach it -- those are different statements, and the
second one is the honest one when the checker itself might be the
problem.
"""

from __future__ import annotations

import time

import discord
from discord.ui import Container, LayoutView, Separator, TextDisplay

GREEN = 0x3BA55D
AMBER = 0xFAA61A
RED = 0xED4245
GREY = 0x4F545C


def _ago(since: float) -> str:
    """How long the current state has held, in words."""
    seconds = max(0, int(time.time() - since))
    if seconds < 60:
        return f"{seconds} Sekunden"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} Minute{'n' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} Stunde{'n' if hours != 1 else ''}"
    days = hours // 24
    return f"{days} Tag{'e' if days != 1 else ''}"


def _line(ok: bool | None, label: str, detail: str = "") -> str:
    mark = {True: "🟢", False: "🔴", None: "⚪"}[ok]
    return f"{mark} **{label}**" + (f" — {detail}" if detail else "")


class StatusView(LayoutView):
    def __init__(self, *, brand: str, state: str, health, since: float):
        super().__init__(timeout=None)

        headline, colour, note = {
            "online": (
                "Alle Systeme laufen",
                GREEN,
                "Der Bot ist erreichbar und bereit.",
            ),
            "starting": (
                "Startet gerade",
                AMBER,
                "Der Bot antwortet, ist aber noch nicht vollständig bereit. "
                "Nach einem Update dauert das ein bis zwei Minuten.",
            ),
            "down": (
                "Störung",
                RED,
                # Careful wording: we know the check failed, not
                # necessarily that the bot is gone. Saying the second
                # would be a guess.
                "Der Bot ist von außen nicht erreichbar. Das kann ein "
                "Neustart, ein fehlgeschlagenes Update oder eine Störung "
                "bei Discord sein.",
            ),
        }.get(state, ("Wird geprüft", GREY, "Noch keine Messung."))

        lines = [
            f"# {headline}",
            f"-# {brand} · seit {_ago(since)}",
        ]

        details = []
        if health.reachable:
            details.append(_line(True, "Erreichbar", f"HTTP {health.status_code}"))
            if health.latency_ms is not None:
                speed = (
                    "schnell" if health.latency_ms < 400
                    else "träge" if health.latency_ms < 2000
                    else "sehr langsam"
                )
                details.append(
                    _line(
                        health.latency_ms < 2000,
                        "Antwortzeit",
                        f"{int(health.latency_ms)} ms ({speed})",
                    )
                )
            details.append(
                _line(
                    health.bot_ready,
                    "Discord-Verbindung",
                    "verbunden" if health.bot_ready else "noch nicht bereit",
                )
            )
            details.append(
                _line(
                    health.dashboard == "online",
                    "Dashboard",
                    health.dashboard,
                )
            )
        else:
            details.append(
                _line(False, "Erreichbar", health.error or "keine Antwort")
            )
            details.append(_line(None, "Discord-Verbindung", "unbekannt"))
            details.append(_line(None, "Dashboard", "unbekannt"))

        checked = (
            time.strftime("%H:%M:%S", time.gmtime(health.checked_at))
            if health.checked_at
            else "—"
        )

        container = Container(
            TextDisplay("\n".join(lines)),
            Separator(visible=True),
            TextDisplay(note),
            Separator(visible=True),
            TextDisplay("\n".join(details)),
            Separator(visible=True),
            TextDisplay(
                f"-# Zuletzt geprüft: {checked} UTC · "
                "Diese Nachricht aktualisiert sich von selbst."
            ),
            accent_colour=colour,
        )
        self.add_item(container)
