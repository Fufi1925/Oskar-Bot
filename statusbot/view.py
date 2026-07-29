# ╔══════════════════════════════════════════════════════════════════╗
# ║   The live status message                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The Components V2 message the status bot keeps in the status channel.

One message, edited in place. Written to be readable at a glance from a
phone notification shade.

Layout, top to bottom:

  1. the headline -- one line saying whether things work
  2. the main bot: its measured figures, then its own link buttons
  3. the template bot: its figures, then its own invite button
  4. a one-line footer: the name and a live timestamp

The footer deliberately carries no "refreshes every 30 seconds" text.
The timestamp is a Discord relative stamp (``<t:...:R>``), which every
client counts up on its own -- so it stays truthful between edits
without the message claiming a schedule.

On the figures: everything under the main bot is measured by this
service. The template bot's latency is **not** measurable from here --
see ``status_bot.check_partner`` for what that means and why the number
is what it is.
"""

from __future__ import annotations

import time

from discord.ui import (
    ActionRow,
    Button,
    Container,
    LayoutView,
    Separator,
    TextDisplay,
)

GREEN = 0x3BA55D
AMBER = 0xFAA61A
RED = 0xED4245
GREY = 0x4F545C

# The footer line. Not the bot's brand name: this is the watcher's own
# name, and it is the only thing down there besides the timestamp.
FOOTER_NAME = "University Status System"


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
    """A rough speed bar."""
    if latency is None:
        return ""
    filled = 5 if latency < 200 else 4 if latency < 400 else 3 if latency < 800 else 2 if latency < 2000 else 1
    return "▰" * filled + "▱" * (5 - filled)


def _speed_word(latency: float) -> str:
    return (
        "schnell" if latency < 400
        else "träge" if latency < 2000
        else "sehr langsam"
    )


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

        # ── 1 · the headline ─────────────────────────────────────
        parts = [
            TextDisplay(f"# {headline}\n-# unverändert seit {_ago(since)}"),
            Separator(visible=True),
            TextDisplay(note),
            Separator(visible=True),
        ]

        # ── 2 · the main bot ─────────────────────────────────────
        main_rows: list[str] = [f"## {brand}"]

        if health.reachable:
            main_rows.append(_line(True, "Erreichbar", f"HTTP {health.status_code}"))

            if health.latency_ms is not None:
                main_rows.append(_line(
                    health.latency_ms < 2000,
                    "Antwortzeit",
                    f"{_bar(health.latency_ms)}  {int(health.latency_ms)} ms · "
                    f"{_speed_word(health.latency_ms)}",
                ))

            main_rows.append(_line(
                health.bot_ready,
                "Discord-Verbindung",
                "verbunden" if health.bot_ready else "noch nicht bereit",
            ))
            main_rows.append(_line(
                health.dashboard == "online",
                "Dashboard",
                {"online": "erreichbar",
                 "starting": "startet noch"}.get(health.dashboard, health.dashboard),
            ))
        else:
            main_rows.append(_line(False, "Erreichbar", health.error or "keine Antwort"))
            # Not red: we never got far enough to check these.
            main_rows.append(_line(None, "Discord-Verbindung", "nicht geprüft"))
            main_rows.append(_line(None, "Dashboard", "nicht geprüft"))

        parts.append(TextDisplay("\n".join(main_rows)))

        # Its own buttons, directly under its own figures, so it is
        # obvious which bot they belong to. Each appears only when
        # configured -- a button that goes nowhere is worse than none.
        main_buttons: list[Button] = []
        if website:
            main_buttons.append(Button(label="Dashboard", url=website, emoji="🖥️"))
        if invite:
            main_buttons.append(Button(label="Einladen", url=invite, emoji="➕"))
        if main_buttons:
            row = ActionRow()
            for button in main_buttons:
                row.add_item(button)
            parts.append(row)

        # ── 3 · the template bot ─────────────────────────────────
        if partner is not None:
            parts.append(Separator(visible=True))

            partner_rows: list[str] = [f"## {partner.get('label', 'Template-Bot')}"]
            ok = partner.get("ok")
            partner_rows.append(_line(
                ok,
                "Status",
                partner.get("detail", "online" if ok else "offline"),
            ))

            ping = partner.get("ping")
            if ping is not None:
                partner_rows.append(_line(
                    True,
                    "Antwortzeit",
                    f"{_bar(ping)}  {int(ping)} ms · {_speed_word(ping)}",
                ))

            parts.append(TextDisplay("\n".join(partner_rows)))

            # No dashboard button here: the template bot has no website
            # of its own. Only the invite.
            partner_invite = partner.get("invite") or ""
            if partner_invite:
                row = ActionRow()
                row.add_item(Button(label="Einladen", url=partner_invite, emoji="➕"))
                parts.append(row)

        # ── 4 · the footer ───────────────────────────────────────
        #
        # Name and time, nothing else. A relative Discord stamp instead
        # of a fixed clock reading: the client counts it up by itself,
        # so the line stays correct between edits and the message never
        # has to promise an interval it might not keep.
        stamp = int(health.checked_at or time.time())
        parts.append(Separator(visible=True))
        parts.append(TextDisplay(f"-# {FOOTER_NAME} · <t:{stamp}:R>"))

        self.add_item(Container(*parts, accent_colour=colour))
