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
    Section,
    Separator,
    TextDisplay,
    Thumbnail,
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
        thumbnail_url: str | None = None,
        buttons=None,
        heading: str = "##",
        timeout: float | None = None,
    ):
        super().__init__(timeout=timeout)

        items = []
        if title:
            items.append(TextDisplay(f"{heading} {title}"))

        first = True
        blocks: list[TextDisplay] = []
        for section in sections:
            text = str(section or "").strip()
            if not text:
                continue
            if title or not first:
                items.append(Separator(visible=True))
            display = TextDisplay(text)
            items.append(display)
            blocks.append(display)
            first = False

        # A thumbnail sat top-right of an embed. The V2 equivalent is a
        # Section with the image as its accessory, so the first block of
        # text is moved inside one. Without this the thumbnail is simply
        # dropped -- 81 embeds set one.
        if thumbnail_url and blocks:
            anchor = blocks[0]
            position = items.index(anchor)
            try:
                items[position] = Section(
                    anchor, accessory=Thumbnail(thumbnail_url)
                )
            except Exception:
                # Any rejection (a bad URL, a future API change) must not
                # cost the text: leave the plain block in place.
                pass
        elif thumbnail_url:
            # Nothing to attach it to, so show it rather than lose it.
            items.append(MediaGallery(discord.MediaGalleryItem(thumbnail_url)))

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


# ── embed → V2, without dropping anything ───────────────────────────
#
# The first version of from_embed() kept the title, description, fields
# and footer, and silently lost the author (102 uses), the thumbnail
# (81), the embed url and the timestamp. Across 342 embeds that is a lot
# of text quietly disappearing, so every part is now accounted for.


def _field_block(field) -> str:
    """One embed field as a text block."""
    name = str(getattr(field, "name", "") or "").strip()
    value = str(getattr(field, "value", "") or "").strip()
    if name and value:
        return f"**{name}**\n{value}"
    return name or value


def _fields_to_text(embed: discord.Embed) -> list[str]:
    """
    An embed's fields as V2 text blocks.

    Inline fields sat side by side in an embed; V2 has no columns, so
    consecutive inline fields are joined into one block instead of
    becoming a stack of tiny separated sections.
    """
    out: list[str] = []
    run: list[str] = []

    for field in embed.fields:
        block = _field_block(field)
        if not block:
            continue
        if getattr(field, "inline", False):
            run.append(block)
            continue
        if run:
            out.append("\n\n".join(run))
            run = []
        out.append(block)

    if run:
        out.append("\n\n".join(run))
    return out


def embed_sections(embed: discord.Embed) -> tuple[str, list[str], str | None, str | None]:
    """
    Everything readable in an embed: (title, body blocks, image, thumb).

    Split out from from_embed so callers that build their own panel can
    reuse it, and so the "nothing is lost" test has one place to check.
    """
    title = str(embed.title or "").strip()

    # The author line sits above the title in an embed, so it goes first
    # here too. Linked when the embed linked it.
    head: list[str] = []
    author = getattr(embed, "author", None)
    author_name = str(getattr(author, "name", "") or "").strip() if author else ""
    if author_name:
        author_url = getattr(author, "url", None)
        head.append(f"-# {f'[{author_name}]({author_url})' if author_url else author_name}")

    # An embed title can be a link. A V2 heading cannot, so the link
    # moves into the heading text as markdown.
    if title and embed.url:
        title = f"[{title}]({embed.url})"

    sections: list[str] = []
    description = str(embed.description or "").strip()
    if description:
        sections.append(description)
    sections.extend(_fields_to_text(embed))

    # Footer and timestamp share the last line in an embed, so they are
    # kept on one line here as well.
    tail: list[str] = []
    footer = getattr(embed, "footer", None)
    footer_text = str(getattr(footer, "text", "") or "").strip() if footer else ""
    stamp = getattr(embed, "timestamp", None)
    if footer_text and stamp:
        tail.append(f"-# {footer_text} • <t:{int(stamp.timestamp())}:f>")
    elif footer_text:
        tail.append(f"-# {footer_text}")
    elif stamp:
        tail.append(f"-# <t:{int(stamp.timestamp())}:f>")

    image_url = embed.image.url if embed.image else None
    thumb_url = embed.thumbnail.url if embed.thumbnail else None

    return title, head + sections + tail, image_url, thumb_url


def from_embed(embed: discord.Embed | None, view: discord.ui.View | None = None,
               *, tone: str | None = None) -> "Panel | None":
    """
    Rebuild a classic embed as a V2 panel, keeping an existing view's
    buttons.

    Components V2 and embeds cannot appear on the same message, so a cog
    that already builds an embed and a View has no cheap way across --
    it has to take the view apart and hand the components to a Panel.
    Doing that by hand at hundreds of call sites is hundreds of chances
    to drop a button or a line of text.

    The view's items are *moved*, not copied: a component may belong to
    one view at a time, and leaving it attached to the old view means
    discord.py still routes its callback through a view that is never
    sent. The callbacks keep working because they live on the items.

    Returns a Panel; the caller sends it as `view=` with no embed.

    `embed=None` gives back None rather than raising. Several callers
    build an optional embed -- a greeting can be plain text -- and used
    to pass `embed=None` straight through to send(), which discord.py
    accepts. Wrapping that in from_embed() turned a working "text only"
    path into AttributeError: 'NoneType' object has no attribute
    'title'. Returning None keeps `view=None` meaning exactly what it
    meant before.
    """
    if embed is None:
        return None

    title, sections, image_url, thumb_url = embed_sections(embed)

    buttons = list(view.children) if view is not None else []
    if view is not None:
        # Detach so the components have exactly one owner.
        for item in buttons:
            view.remove_item(item)

    return Panel(
        title,
        *sections,
        tone=tone or "info",
        accent=embed.colour.value if embed.colour is not None else None,
        image_url=image_url,
        thumbnail_url=thumb_url,
        buttons=buttons,
        timeout=getattr(view, "timeout", None),
    )


def from_embeds(embeds, view: discord.ui.View | None = None,
                *, tone: str | None = None) -> "Panel | None":
    """
    Several embeds as one V2 panel.

    A message could carry up to ten embeds stacked on top of each other;
    Components V2 has no equivalent, so they are merged into a single
    container with a divider between them. Battleship sends three at
    once -- two boards and a status card -- and the order is what makes
    them readable, so it is preserved exactly.

    The first embed's title becomes the panel heading; the others keep
    theirs as a bold line inside the body, because a container has one
    heading.
    """
    embeds = [e for e in (embeds or []) if e is not None]
    if not embeds:
        return None
    if len(embeds) == 1:
        return from_embed(embeds[0], view, tone=tone)

    title, sections, image_url, thumb_url = embed_sections(embeds[0])

    for extra in embeds[1:]:
        extra_title, extra_sections, extra_image, extra_thumb = embed_sections(extra)
        if extra_title:
            sections.append(f"**{extra_title}**")
        sections.extend(extra_sections)
        # Only one image and one thumbnail can be shown per container,
        # so a later one is only taken when the first had none.
        image_url = image_url or extra_image
        thumb_url = thumb_url or extra_thumb

    buttons = list(view.children) if view is not None else []
    if view is not None:
        for item in buttons:
            view.remove_item(item)

    accent = None
    for candidate in embeds:
        if candidate.colour is not None:
            accent = candidate.colour.value
            break

    return Panel(
        title,
        *sections,
        tone=tone or "info",
        accent=accent,
        image_url=image_url,
        thumbnail_url=thumb_url,
        buttons=buttons,
        timeout=getattr(view, "timeout", None),
    )
