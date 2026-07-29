# ╔══════════════════════════════════════════════════════════════════╗
# ║   The live status message                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The Components V2 message the status bot keeps in the status channel.

One message, edited in place. Written to be readable at a glance from a
phone notification shade.

Layout, top to bottom:

  1. the headline -- one line saying whether things work
  2. the main bot: avatar, state, its figures, then its own buttons
  3. the template bot: the same shape, so both read alike
  4. a one-line footer: the name and a live timestamp

Every bot gets a ``Section`` with its avatar as the accessory, so the
two blocks are told apart by picture before a word is read. Underneath,
the figures are a quoted list -- Discord draws a vertical bar down the
side of ``>`` lines, which groups them without needing a box.

The markup is deliberately Discord's own rather than plain text:
``#``/``##``/``###`` headings, ``>`` quotes, ``-#`` small print,
``**bold**`` for what a row is, backticks for measured values, and
``<t:...:R>`` for anything time-based so the client counts it up
itself. Written-out approximations of those things ("Stand: 12:04 UTC")
go stale between edits; the real markup does not.

On the figures: everything under the main bot is measured by this
service. The template bot's are not, and cannot be -- see
``status_bot.check_partner`` for what that means and why.
"""

from __future__ import annotations

import time

from discord import SeparatorSpacing
from discord.ui import (
    ActionRow,
    Button,
    Container,
    LayoutView,
    Section,
    Separator,
    TextDisplay,
    Thumbnail,
)

GREEN = 0x3BA55D
AMBER = 0xFAA61A
RED = 0xED4245
GREY = 0x4F545C

# The footer line. Not the bot's brand name: this is the watcher's own
# name, and it is the only thing down there besides the timestamp.
FOOTER_NAME = "University Status System"

# Marks for the checklist. `None` means "not measured" and gets a
# hollow one, never a red one: red says we looked and it was broken,
# hollow says we did not look.
MARKS = {True: "🟢", False: "🔴", None: "⚪"}


def _rule(large: bool = False) -> Separator:
    """A divider. The large one separates bots, the small one rows."""
    return Separator(
        visible=True,
        spacing=SeparatorSpacing.large if large else SeparatorSpacing.small,
    )


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


def _row(ok: bool | None, label: str, value: str = "", note: str = "") -> str:
    """
    One row of the checklist, as a quoted line.

    Discord draws a continuous bar down the left of consecutive `>`
    lines, so a list of these reads as one grouped block. The label is
    bold, the measured value is in backticks -- a number in code type
    is visibly a reading rather than prose -- and any wording after it
    is left plain.
    """
    line = f"> {MARKS[ok]} **{label}**"
    if value:
        line += f" · `{value}`"
    if note:
        line += f" · {note}"
    return line


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


def _heading(
    name: str,
    mark: str,
    state_word: str,
    subtitle: str,
    avatar: str = "",
) -> Section | TextDisplay:
    """
    A bot's name plate: name, state, one line of context.

    Returns a Section with the avatar beside it when there is one, and
    falls back to plain text when there is not -- a Section without an
    accessory is not a thing, and a broken avatar must not cost the
    whole panel.
    """
    lines = [
        f"## {name}",
        f"### {mark} {state_word}",
        f"-# {subtitle}",
    ]
    if avatar:
        return Section(
            *lines,
            accessory=Thumbnail(avatar, description=f"Profilbild von {name}"),
        )
    return TextDisplay("\n".join(lines))


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
        avatar: str = "",
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
        #
        # The change of state gets a real Discord timestamp rather than
        # only the written-out "seit 2 Stunden": the client keeps that
        # one current by itself, so it does not drift between edits.
        changed = int(since)
        parts = [
            TextDisplay(
                f"# {headline}\n"
                f"-# Unverändert seit {_ago(since)} · seit <t:{changed}:t>"
            ),
            _rule(),
            # The explanation as a quote: it is the panel talking about
            # itself, and the bar sets it apart from the readings.
            TextDisplay(f"> {note}"),
            _rule(large=True),
        ]

        # ── 2 · the main bot ─────────────────────────────────────
        state_word, state_mark = {
            "online": ("Betriebsbereit", "🟢"),
            "starting": ("Startet", "🟡"),
            "down": ("Nicht erreichbar", "🔴"),
        }.get(state, ("Wird geprüft", "⚪"))

        parts.append(_heading(
            brand,
            state_mark,
            state_word,
            "Hauptbot · Dashboard, Befehle und Automatiken",
            avatar,
        ))

        rows: list[str] = []
        if health.reachable:
            rows.append(_row(True, "Erreichbar", f"HTTP {health.status_code}"))

            if health.latency_ms is not None:
                rows.append(_row(
                    health.latency_ms < 2000,
                    "Antwortzeit",
                    f"{int(health.latency_ms)} ms",
                    f"{_bar(health.latency_ms)} {_speed_word(health.latency_ms)}",
                ))

            rows.append(_row(
                health.bot_ready,
                "Discord-Verbindung",
                note="verbunden" if health.bot_ready else "noch nicht bereit",
            ))
            rows.append(_row(
                health.dashboard == "online",
                "Dashboard",
                note={"online": "erreichbar",
                      "starting": "startet noch"}.get(health.dashboard,
                                                      health.dashboard),
            ))
        else:
            rows.append(_row(False, "Erreichbar",
                             note=health.error or "keine Antwort"))
            # Not red: we never got far enough to check these.
            rows.append(_row(None, "Discord-Verbindung", note="nicht geprüft"))
            rows.append(_row(None, "Dashboard", note="nicht geprüft"))

        parts.append(TextDisplay("\n".join(rows)))

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
        #
        # Same shape as the block above on purpose: same heading, same
        # quoted rows, same button row. Two differently built blocks
        # would read as two different kinds of thing.
        if partner is not None:
            parts.append(_rule(large=True))

            name = partner.get("label", "Template-Bot")
            ok = partner.get("ok")
            parts.append(_heading(
                name,
                MARKS[ok],
                "Online" if ok else "Nicht auf dem Server",
                "Template-Bot · fertige Server-Vorlagen",
                partner.get("avatar") or "",
            ))

            partner_rows = [_row(
                ok,
                "Status",
                note=partner.get("detail", "online" if ok else "offline"),
            )]

            ping = partner.get("ping")
            if ping is not None:
                partner_rows.append(_row(
                    True,
                    "Antwortzeit",
                    f"{int(ping)} ms",
                    f"{_bar(ping)} {_speed_word(ping)}",
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
        parts.append(_rule(large=True))
        parts.append(TextDisplay(f"-# {FOOTER_NAME} · <t:{stamp}:R>"))

        self.add_item(Container(*parts, accent_colour=colour))
