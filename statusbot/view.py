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

import emojis
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
#
# Read through the emoji module rather than hard-coded, so the custom
# set is used when this application owns it and the plain characters
# when it does not. Called per draw, not captured once: the check that
# decides which to use finishes after this module is imported.


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
    line = f"> {emojis.state_mark(ok)} **{label}**"
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


def _uptime_line(uptime: dict) -> str:
    """
    The history line: how much of the window was up, and the last
    outage.

    "Up" counts starting as well as online -- a bot that is booting is
    not broken, and counting deploys as downtime would make every
    update look like an incident.
    """
    percent = uptime["percent"]
    days = uptime["days"]

    # A partial record is still worth showing, but must not be
    # presented as covering the whole window.
    span = (
        f"{days} Tagen"
        if uptime.get("complete")
        else f"{_ago(time.time() - uptime['measured_seconds'])}"
    )

    line = f"-# {emojis.markup('uptime')} {percent:.2f} % erreichbar in {span}"

    if uptime.get("outage_count"):
        ended = uptime.get("last_outage_end")
        if ended:
            line += (
                f" · letzte Störung <t:{int(ended)}:R>"
                f" ({_ago(time.time() - uptime['last_outage_seconds'])} lang)"
            )
    else:
        line += " · keine Störung"

    return line


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
        uptime=None,
        maintenance: bool = False,
        maintenance_note: str = "",
    ):
        super().__init__(timeout=None)

        headline, colour, note = {
            "online": (
                f"{emojis.markup('online')}  Alle Systeme laufen",
                GREEN,
                "Der Bot ist erreichbar und bereit.",
            ),
            "starting": (
                f"{emojis.markup('starting')}  Startet gerade",
                AMBER,
                "Der Bot antwortet, ist aber noch nicht vollständig bereit. "
                "Nach einem Update dauert das ein bis zwei Minuten.",
            ),
            "down": (
                f"{emojis.markup('down')}  Störung",
                RED,
                # Careful wording: we know the check failed, not that the
                # bot is gone. Saying the second would be a guess, and
                # the checker itself could be the problem.
                "Der Bot ist von außen nicht erreichbar. Das kann ein "
                "Neustart, ein fehlgeschlagenes Update oder eine Störung "
                "bei Discord sein.",
            ),
        }.get(state, (f"{emojis.markup('unknown')}  Wird geprüft", GREY,
                      "Noch keine Messung."))

        # Maintenance overrides the headline, but not the readings
        # below -- those stay real. The point is to stop the panel
        # shouting "outage" at something that was planned, not to hide
        # what is actually happening.
        if maintenance:
            headline = f"{emojis.markup('starting')}  Geplante Wartung"
            colour = AMBER
            note = (
                "An diesem Bot wird gerade gearbeitet. Kurze Ausfälle sind "
                "in dieser Zeit normal und kein Grund zur Sorge."
            )
            if maintenance_note:
                note += f"\n**Grund:** {maintenance_note}"

        # ── 1 · the headline ─────────────────────────────────────
        #
        # The change of state gets a real Discord timestamp rather than
        # only the written-out "seit 2 Stunden": the client keeps that
        # one current by itself, so it does not drift between edits.
        changed = int(since)
        parts = [
            TextDisplay(
                f"# {headline}\n"
                f"-# {emojis.markup('uptime')} Unverändert seit {_ago(since)}"
                f" · seit <t:{changed}:t>"
            ),
            _rule(),
            # The explanation as a quote: it is the panel talking about
            # itself, and the bar sets it apart from the readings.
            TextDisplay(f"> {note}"),
            _rule(large=True),
        ]

        # ── 2 · the main bot ─────────────────────────────────────
        state_word, state_role = {
            "online": ("Betriebsbereit", "online"),
            "starting": ("Startet", "starting"),
            "down": ("Nicht erreichbar", "down"),
        }.get(state, ("Wird geprüft", "unknown"))
        state_mark = emojis.markup(state_role)

        parts.append(_heading(
            brand,
            state_mark,
            state_word,
            f"{emojis.markup('bot')} Hauptbot · Dashboard, Befehle und "
            "Automatiken",
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
            main_buttons.append(Button(
                label="Dashboard", url=website,
                emoji=emojis.button("website"),
            ))
        if invite:
            main_buttons.append(Button(
                label="Einladen", url=invite, emoji=emojis.button("invite"),
            ))
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
                emojis.state_mark(ok),
                "Online" if ok else "Nicht auf dem Server",
                f"{emojis.markup('bot')} Template-Bot · fertige "
                "Server-Vorlagen",
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
                row.add_item(Button(
                    label="Einladen", url=partner_invite,
                    emoji=emojis.button("invite"),
                ))
                parts.append(row)

        # ── 4 · the footer ───────────────────────────────────────
        #
        # Name and time, nothing else. A relative Discord stamp instead
        # of a fixed clock reading: the client counts it up by itself,
        # so the line stays correct between edits and the message never
        # has to promise an interval it might not keep.
        stamp = int(health.checked_at or time.time())
        parts.append(_rule(large=True))

        # The uptime line, when there is enough recorded to mean
        # anything. Left out otherwise rather than printing a
        # percentage derived from twenty minutes of data.
        if uptime and uptime.get("known"):
            parts.append(TextDisplay(_uptime_line(uptime)))

        parts.append(TextDisplay(f"-# {FOOTER_NAME} · <t:{stamp}:R>"))

        self.add_item(Container(*parts, accent_colour=colour))


# ══════════════════════════════════════════════════════════════════════
#  The /verlauf panel
# ══════════════════════════════════════════════════════════════════════


class HistoryView(LayoutView):
    """
    The charts, as their own message.

    Kept separate from the live panel deliberately. That one is edited
    every 30 seconds and has to stay glanceable from a notification
    shade; this one is asked for, read once, and can afford to be long.

    Everything here is measured. There is no simulated figure on this
    panel at all -- the template bot's invented ping has no business in
    a chart somebody might screenshot as evidence.
    """

    def __init__(
        self,
        *,
        brand: str,
        slots: list[dict],
        uptime: dict,
        errors: dict,
        hours: int,
        persistent: bool,
    ):
        super().__init__(timeout=None)

        import charts

        parts: list = [
            TextDisplay(
                f"# {emojis.markup('uptime')}  Verlauf\n"
                f"-# {brand} · letzte {hours} Stunden"
            ),
            _rule(large=True),
        ]

        # ── availability ─────────────────────────────────────────
        avail, avail_caption = charts.availability_chart(slots)
        if avail:
            parts.append(TextDisplay(
                f"### Erreichbarkeit\n{avail}\n-# {avail_caption}"
            ))
        else:
            parts.append(TextDisplay(
                "### Erreichbarkeit\n-# Noch keine Messwerte."
            ))

        # ── latency ──────────────────────────────────────────────
        bars, caption = charts.latency_chart(slots)
        if bars:
            parts.append(_rule())
            parts.append(TextDisplay(
                f"### Antwortzeit\n`{bars}`\n-# {caption}"
            ))

        # ── uptime over the longer window ────────────────────────
        if uptime.get("known"):
            parts.append(_rule())
            rows = [
                f"> {emojis.state_mark(True)} **Erreichbar** · "
                f"`{uptime['percent']:.2f} %`"
                + ("" if uptime.get("complete") else " · Aufzeichnung noch kurz"),
            ]
            if uptime.get("outage_count"):
                total = int(uptime["outage_seconds"])
                rows.append(
                    f"> {emojis.state_mark(False)} **Störungen** · "
                    f"`{uptime['outage_count']}` · zusammen {_ago_span(total)}"
                )
                ended = uptime.get("last_outage_end")
                if ended:
                    rows.append(f"> {emojis.markup('uptime')} **Zuletzt** · <t:{int(ended)}:R>")
            else:
                rows.append(
                    f"> {emojis.state_mark(True)} **Störungen** · keine"
                )
            parts.append(TextDisplay(
                f"### Die letzten {uptime['days']} Tage\n" + "\n".join(rows)
            ))

        # ── command errors from the main bot ─────────────────────
        if errors.get("known"):
            parts.append(_rule())
            total = errors["total"]
            mark = emojis.state_mark(True if total == 0 else None)
            rows = [
                f"> {mark} **Fehlgeschlagene Befehle** · `{total}`"
                f" in {errors['hours']} Stunden"
            ]
            if errors.get("restarts"):
                # Worth its own line: the counter resetting is how a
                # restart shows up here, and a restart nobody ordered
                # is a thing to look into.
                rows.append(
                    f"> {emojis.markup('starting')} **Neustarts** · "
                    f"`{errors['restarts']}`"
                )
            parts.append(TextDisplay(
                "### Befehle\n" + "\n".join(rows) + "\n"
                "-# Vom Hauptbot selbst gezählt: Befehle, die mit einem "
                "Fehler endeten — nicht Ausfälle."
            ))

        # ── the honest footnote ──────────────────────────────────
        parts.append(_rule(large=True))
        if persistent:
            note = f"-# {FOOTER_NAME} · alle Werte gemessen"
        else:
            # Without a volume the record restarts on every deploy, and
            # a chart covering "the last 24 hours" that actually covers
            # forty minutes would be misleading.
            note = (
                f"-# {FOOTER_NAME} · ⚠️ ohne Volume — die Aufzeichnung "
                "beginnt nach jedem Deploy von vorn"
            )
        parts.append(TextDisplay(note))

        self.add_item(Container(*parts, accent_colour=GREEN))


def _ago_span(seconds: int) -> str:
    """A duration in words, for totals rather than points in time."""
    if seconds < 60:
        return f"{seconds} Sekunden"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} Minuten"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min" if minutes else f"{hours} Stunden"
    days, hours = divmod(hours, 24)
    return f"{days} Tage {hours} h" if hours else f"{days} Tage"
