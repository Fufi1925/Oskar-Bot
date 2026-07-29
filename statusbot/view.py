# ╔══════════════════════════════════════════════════════════════════╗
# ║   The live status message                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The Components V2 message the status bot keeps in the status channel.

One message, edited in place. Written to be readable at a glance from a
phone notification shade: state first, details after, links at the
bottom.

The rule the whole file follows: **never show a number we did not
measure.** A latency of "34 ms" next to a bot we cannot actually reach,
or a green dot for something we never checked, is worse than saying
nothing -- it is a status page that lies, which is the one thing a
status page must not do. Anything unknown is marked unknown.
"""

from __future__ import annotations

import time

import discord
from discord.ui import (
    ActionRow,
    Button,
    Container,
    LayoutView,
    Section,
    Separator,
    TextDisplay,
)

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
    """
    One row of the checklist.

    `None` means "not measured" and gets a hollow mark, not a red one.
    Red says we looked and it was broken; hollow says we did not look.
    """
    mark = {True: "🟢", False: "🔴", None: "⚪"}[ok]
    return f"{mark} **{label}**" + (f"\n-# {detail}" if detail else "")


def _bar(latency: float | None) -> str:
    """A rough speed bar. Only drawn when there is a real measurement."""
    if latency is None:
        return ""
    filled = 5 if latency < 200 else 4 if latency < 400 else 3 if latency < 800 else 2 if latency < 2000 else 1
    return "▰" * filled + "▱" * (5 - filled)


class StatusView(LayoutView):
    def __init__(
        self,
        *,
        brand: str,
        state: str,
        health,
        since: float,
        website: str = "",
        invite: str = "",
        support: str = "",
        partner=None,
    ):
        super().__init__(timeout=None)

        headline, colour, note = {
            "online": (
                "🟢  Alle Systeme laufen",
                GREEN,
                "Der Bot ist erreichbar und bereit.",
            ),
            "starting": (
                "🟡  Startet gerade",
                AMBER,
                "Der Bot antwortet, ist aber noch nicht vollständig bereit. "
                "Nach einem Update dauert das ein bis zwei Minuten.",
            ),
            "down": (
                "🔴  Störung",
                RED,
                # Careful wording: we know the check failed, not that the
                # bot is gone. Saying the second would be a guess, and
                # the checker itself could be the problem.
                "Der Bot ist von außen nicht erreichbar. Das kann ein "
                "Neustart, ein fehlgeschlagenes Update oder eine Störung "
                "bei Discord sein.",
            ),
        }.get(state, ("⚪  Wird geprüft", GREY, "Noch keine Messung."))

        # ── header ───────────────────────────────────────────────
        header = (
            f"# {headline}\n"
            f"-# {brand} · unverändert seit {_ago(since)}"
        )

        # ── the checklist ────────────────────────────────────────
        details: list[str] = []

        if health.reachable:
            details.append(_line(True, "Erreichbar", f"HTTP {health.status_code}"))

            if health.latency_ms is not None:
                speed = (
                    "schnell" if health.latency_ms < 400
                    else "träge" if health.latency_ms < 2000
                    else "sehr langsam"
                )
                details.append(_line(
                    health.latency_ms < 2000,
                    "Antwortzeit",
                    f"{_bar(health.latency_ms)}  {int(health.latency_ms)} ms · {speed}",
                ))

            details.append(_line(
                health.bot_ready,
                "Discord-Verbindung",
                "verbunden" if health.bot_ready else "noch nicht bereit",
            ))
            details.append(_line(
                health.dashboard == "online",
                "Dashboard",
                {"online": "erreichbar",
                 "starting": "startet noch"}.get(health.dashboard, health.dashboard),
            ))
        else:
            details.append(_line(False, "Erreichbar", health.error or "keine Antwort"))
            # Not red: we never got far enough to check these.
            details.append(_line(None, "Discord-Verbindung", "nicht geprüft"))
            details.append(_line(None, "Dashboard", "nicht geprüft"))

        # ── the template bot ─────────────────────────────────────
        #
        # Only what was actually established. `partner` is None when the
        # check was not possible at all, and then the row says so rather
        # than inventing a green dot.
        if partner is not None:
            details.append(_line(
                partner.get("ok"),
                partner.get("label", "Template-Bot"),
                partner.get("detail", ""),
            ))

        checked = (
            time.strftime("%H:%M:%S", time.gmtime(health.checked_at))
            if health.checked_at
            else "—"
        )

        parts = [
            TextDisplay(header),
            Separator(visible=True),
            TextDisplay(note),
            Separator(visible=True),
            TextDisplay("\n".join(details)),
        ]

        # ── links ────────────────────────────────────────────────
        #
        # Only the ones that were configured. A button that goes nowhere
        # is worse than no button.
        buttons: list[Button] = []
        if website:
            buttons.append(Button(label="Dashboard", url=website, emoji="🖥️"))
        if invite:
            buttons.append(Button(label="Einladen", url=invite, emoji="➕"))
        if support:
            buttons.append(Button(label="Support", url=support, emoji="💬"))

        if buttons:
            parts.append(Separator(visible=True))
            row = ActionRow()
            for button in buttons:
                row.add_item(button)
            parts.append(row)

        parts.append(Separator(visible=True))
        parts.append(TextDisplay(
            f"-# Zuletzt geprüft: {checked} UTC · alle 30 Sekunden · "
            "aktualisiert sich von selbst"
        ))

        self.add_item(Container(*parts, accent_colour=colour))
