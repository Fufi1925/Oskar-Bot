# ╔══════════════════════════════════════════════════════════════════╗
# ║   Shared Components V2 panels                                    ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Components V2 building blocks shared by the cogs and the dashboard API.

Everything the bot posts should look the same no matter where the action was
triggered. Before this, the verification cog sent V2 cards while the same
panel sent from the dashboard was still a plain embed, so one server could
end up with two different-looking verification messages.

Panels here take a `buttons` list rather than a View, because the caller
already owns the view (and its persistence); we only need the components.
"""

from __future__ import annotations

import discord
from discord.ui import (
    ActionRow,
    Container,
    LayoutView,
    MediaGallery,
    Separator,
    TextDisplay,
)

# Shared accent colours. Keep in sync with the verification cog's tones.
ACCENT = {
    "info": 0x3D7CFF,
    "success": 0x2ECC71,
    "warning": 0xF1C40F,
    "error": 0xE74C3C,
    "brand": 0x5865F2,
    "giveaway": 0xF59E0B,
}

# The app has its own emoji for each of these, so a status card carries
# the bot's own look instead of a bullet, a check mark and a bare "!".
# Imported lazily inside the module to keep panels.py free of a hard
# dependency on the emoji table -- if a name is ever dropped there, the
# card still renders with the old text marker rather than raising.
try:  # pragma: no cover - trivial import guard
    from utils.emoji import TICK, CROSS, WARNING, INFO

    MARKERS = {
        "info": INFO,
        "success": TICK,
        "warning": WARNING,
        "error": CROSS,
    }
except ImportError:  # pragma: no cover
    MARKERS = {
        "info": "\u2022",
        "success": "\u2713",
        "warning": "!",
        "error": "\u00d7",
    }


def container(*items, accent_color=None) -> Container:
    """Container() takes no positional children, so add them one by one."""
    box = Container(accent_color=accent_color)
    for item in items:
        if item is not None:
            box.add_item(item)
    return box


def _is_select(item) -> bool:
    """A select of any flavour: string, user, role, mentionable, channel."""
    return "Select" in type(item).__name__


def _rows(buttons, limit: int = 5):
    """
    Split components into ActionRows.

    Five buttons fit in a row, but a select takes the whole row -- so a
    select mixed in with buttons has to break the run. Chunking purely
    by count raised "maximum number of children exceeded" as soon as a
    select shared a row, which is a 400 from Discord at send time.
    """
    out = []
    current: list = []
    for item in [b for b in (buttons or []) if b is not None]:
        if _is_select(item):
            if current:
                out.append(ActionRow(*current))
                current = []
            out.append(ActionRow(item))
            continue
        current.append(item)
        if len(current) == limit:
            out.append(ActionRow(*current))
            current = []
    if current:
        out.append(ActionRow(*current))
    return out


class Panel(LayoutView):
    """
    A generic V2 panel: heading, body sections, optional image, buttons.

    Used for everything the dashboard posts into a channel so the result is
    indistinguishable from what the bot posts by itself.
    """

    def __init__(
        self,
        title: str,
        *sections: str,
        tone: str = "info",
        accent: int | None = None,
        image_url: str | None = None,
        buttons=None,
        heading: str = "##",
        timeout: float | None = None,
    ):
        super().__init__(timeout=timeout)

        items = []
        if title:
            items.append(TextDisplay(f"{heading} {title}"))

        first = True
        for section in sections:
            text = str(section or "").strip()
            if not text:
                continue
            if title or not first:
                items.append(Separator(visible=True))
            items.append(TextDisplay(text))
            first = False

        if image_url:
            items.append(MediaGallery(discord.MediaGalleryItem(image_url)))

        rows = _rows(buttons)
        if rows:
            items.append(Separator(visible=True))
            items.extend(rows)

        colour = accent if accent is not None else ACCENT.get(tone, ACCENT["info"])
        self.add_item(container(*items, accent_color=colour))


class StatusCard(LayoutView):
    """Small result card: a marker, a title and one block of text."""

    def __init__(self, title: str, body: str = "", *, tone: str = "info"):
        super().__init__(timeout=None)
        marker = MARKERS.get(tone, "\u2022")
        items = [TextDisplay(f"### {marker}  {title}")]
        if body:
            items.append(Separator(visible=True))
            items.append(TextDisplay(str(body)))
        self.add_item(container(*items, accent_color=ACCENT.get(tone, ACCENT["info"])))


def _fields_to_text(embed: discord.Embed) -> list[str]:
    """An embed's fields as V2 text blocks."""
    out = []
    for field in embed.fields:
        name = str(field.name or "").strip()
        value = str(field.value or "").strip()
        if not name and not value:
            continue
        out.append(f"**{name}**\n{value}" if name and value else (name or value))
    return out


def from_embed(embed: discord.Embed, view: discord.ui.View | None = None,
               *, tone: str | None = None) -> "Panel":
    """
    Rebuild a classic embed as a V2 panel, keeping an existing view's
    buttons.

    Components V2 and embeds cannot appear on the same message, so a cog
    that already builds an embed and a View has no cheap way across --
    it has to take the view apart and hand the components to a Panel.
    Doing that at 83 call sites by hand is 83 chances to drop a button.

    The view's items are *moved*, not copied: a component may belong to
    one view at a time, and leaving it attached to the old view means
    discord.py still routes its callback through a view that is never
    sent. The callbacks keep working because they live on the items.

    Returns a Panel; the caller sends it as `view=` with no embed.
    """
    title = str(embed.title or "").strip()

    sections: list[str] = []
    description = str(embed.description or "").strip()
    if description:
        sections.append(description)
    sections.extend(_fields_to_text(embed))
    if embed.footer and embed.footer.text:
        sections.append(f"-# {embed.footer.text}")

    buttons = list(view.children) if view is not None else []
    if view is not None:
        # Detach so the components have exactly one owner.
        for item in buttons:
            view.remove_item(item)

    image_url = embed.image.url if embed.image else None

    return Panel(
        title,
        *sections,
        tone=tone or "info",
        accent=embed.colour.value if embed.colour is not None else None,
        image_url=image_url,
        buttons=buttons,
        timeout=getattr(view, "timeout", None),
    )
