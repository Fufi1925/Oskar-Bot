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


def _rows(buttons, limit: int = 5):
    """Split components into ActionRows of at most five."""
    out = []
    buttons = [b for b in (buttons or []) if b is not None]
    for i in range(0, len(buttons), limit):
        out.append(ActionRow(*buttons[i:i + limit]))
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
