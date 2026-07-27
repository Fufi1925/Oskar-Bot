# ╔══════════════════════════════════════════════════════════════════╗
# ║   Building a message from a dashboard description                ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Turns a JSON description from the dashboard into something the bot can
post: plain text, a classic embed, or a Components V2 panel.

The existing `/actions/{guild}/message/send` route could do a title, a
body and a colour, and always produced the same shaped panel. Anything
past that — several blocks of text, a divider, an image in the middle,
buttons with links, a footer — meant editing Python.

One rule runs through all of this: **validate before sending.** Discord
rejects a whole message for a single malformed URL or an over-long
field, and the error it returns says very little. Everything here is
checked first and reported as a plain sentence.
"""

from __future__ import annotations

from typing import Any

import discord

# Discord's own limits. Exceeding any of these is a 400 with a terse body.
LIMITS = {
    "content": 2000,
    "embed_title": 256,
    "embed_description": 4096,
    "embed_field_name": 256,
    "embed_field_value": 1024,
    "embed_footer": 2048,
    "embed_author": 256,
    "embed_total": 6000,
    "fields": 25,
    "buttons": 25,
    "button_label": 80,
    "v2_text": 4000,
}

BLOCK_TYPES = {"text", "divider", "image", "buttons"}

BUTTON_STYLES = {
    "primary": discord.ButtonStyle.primary,
    "secondary": discord.ButtonStyle.secondary,
    "success": discord.ButtonStyle.success,
    "danger": discord.ButtonStyle.danger,
    "link": discord.ButtonStyle.link,
}


def is_url(value: str) -> bool:
    return str(value or "").strip().startswith(("http://", "https://"))


def parse_colour(value: Any, fallback: int = 0x5865F2) -> int:
    """Accept `#5865f2`, `5865f2` or an integer."""
    if value is None or value == "":
        return fallback
    if isinstance(value, int):
        return max(0, min(value, 0xFFFFFF))
    try:
        return max(0, min(int(str(value).strip().lstrip("#"), 16), 0xFFFFFF))
    except ValueError:
        return fallback


# ── validation ──────────────────────────────────────────────────────


def validate(data: dict) -> list[str]:
    """
    Everything wrong with this message, in plain German.

    An empty list means it can be sent. Returning all the problems at
    once beats making somebody press Send five times to find them.
    """
    problems: list[str] = []
    kind = str(data.get("kind") or "text")

    if kind == "text":
        content = str(data.get("content") or "").strip()
        if not content:
            problems.append("Die Nachricht ist leer.")
        elif len(content) > LIMITS["content"]:
            problems.append(
                f"Der Text ist {len(content)} Zeichen lang, erlaubt sind "
                f"{LIMITS['content']}."
            )

    elif kind == "embed":
        embed = data.get("embed") or {}
        title = str(embed.get("title") or "")
        description = str(embed.get("description") or "")
        fields = embed.get("fields") or []

        if not any([title, description, fields, embed.get("image"),
                    embed.get("thumbnail")]):
            problems.append("Der Embed ist komplett leer.")

        if len(title) > LIMITS["embed_title"]:
            problems.append(f"Der Titel ist zu lang (max {LIMITS['embed_title']}).")
        if len(description) > LIMITS["embed_description"]:
            problems.append(
                f"Die Beschreibung ist zu lang (max {LIMITS['embed_description']})."
            )
        if len(fields) > LIMITS["fields"]:
            problems.append(f"Mehr als {LIMITS['fields']} Felder gehen nicht.")

        for index, field in enumerate(fields, start=1):
            name = str(field.get("name") or "")
            value = str(field.get("value") or "")
            if not name or not value:
                problems.append(f"Feld {index}: Name und Inhalt dürfen nicht leer sein.")
            if len(name) > LIMITS["embed_field_name"]:
                problems.append(f"Feld {index}: Der Name ist zu lang.")
            if len(value) > LIMITS["embed_field_value"]:
                problems.append(f"Feld {index}: Der Inhalt ist zu lang.")

        # Discord counts every text part of an embed together.
        total = (
            len(title) + len(description)
            + len(str(embed.get("footer_text") or ""))
            + len(str(embed.get("author_name") or ""))
            + sum(len(str(f.get("name") or "")) + len(str(f.get("value") or ""))
                  for f in fields)
        )
        if total > LIMITS["embed_total"]:
            problems.append(
                f"Der Embed hat insgesamt {total} Zeichen, Discord erlaubt "
                f"{LIMITS['embed_total']}."
            )

        for key, label in (("image", "Großes Bild"), ("thumbnail", "Kleines Bild"),
                           ("author_icon", "Autor-Bild"), ("footer_icon", "Fußzeilen-Bild")):
            value = embed.get(key)
            if value and not is_url(value):
                problems.append(f"{label}: Das muss ein Link mit https:// sein.")

    elif kind == "v2":
        blocks = data.get("blocks") or []
        if not blocks:
            problems.append("Es wurde noch kein Baustein hinzugefügt.")

        has_content = False
        button_count = 0

        for index, block in enumerate(blocks, start=1):
            block_type = str(block.get("type") or "")
            if block_type not in BLOCK_TYPES:
                problems.append(f"Baustein {index}: Unbekannter Typ „{block_type}“.")
                continue

            if block_type == "text":
                text = str(block.get("text") or "").strip()
                if not text:
                    problems.append(f"Baustein {index}: Der Text ist leer.")
                elif len(text) > LIMITS["v2_text"]:
                    problems.append(f"Baustein {index}: Der Text ist zu lang.")
                else:
                    has_content = True

            elif block_type == "image":
                if not is_url(block.get("url")):
                    problems.append(
                        f"Baustein {index}: Das Bild braucht einen Link mit https://."
                    )
                else:
                    has_content = True

            elif block_type == "buttons":
                buttons = block.get("buttons") or []
                if not buttons:
                    problems.append(f"Baustein {index}: Keine Knöpfe eingetragen.")
                for button in buttons:
                    button_count += 1
                    label = str(button.get("label") or "").strip()
                    if not label:
                        problems.append(f"Baustein {index}: Ein Knopf hat keine Beschriftung.")
                    elif len(label) > LIMITS["button_label"]:
                        problems.append(f"Baustein {index}: Eine Beschriftung ist zu lang.")
                    # Only link buttons make sense from here: a custom_id
                    # button needs code behind it to do anything.
                    if not is_url(button.get("url")):
                        problems.append(
                            f"Baustein {index}: „{label or 'Knopf'}“ braucht einen "
                            "Link mit https:// — ein Knopf ohne Ziel täte nichts."
                        )
                has_content = True

        if button_count > LIMITS["buttons"]:
            problems.append(f"Mehr als {LIMITS['buttons']} Knöpfe gehen nicht.")
        if blocks and not has_content:
            problems.append("Die Nachricht besteht nur aus Trennlinien.")

    else:
        problems.append(f"Unbekannte Nachrichtenart „{kind}“.")

    return problems


# ── building ────────────────────────────────────────────────────────


def build_embed(embed_data: dict) -> discord.Embed:
    embed = discord.Embed(
        title=str(embed_data.get("title") or "") or None,
        description=str(embed_data.get("description") or "") or None,
        color=parse_colour(embed_data.get("color")),
    )

    if embed_data.get("timestamp"):
        embed.timestamp = discord.utils.utcnow()

    for field in (embed_data.get("fields") or [])[: LIMITS["fields"]]:
        name = str(field.get("name") or "")
        value = str(field.get("value") or "")
        if name and value:
            embed.add_field(name=name, value=value, inline=bool(field.get("inline")))

    if embed_data.get("author_name"):
        embed.set_author(
            name=str(embed_data["author_name"]),
            icon_url=(
                str(embed_data["author_icon"])
                if is_url(embed_data.get("author_icon")) else None
            ),
        )
    if embed_data.get("footer_text"):
        embed.set_footer(
            text=str(embed_data["footer_text"]),
            icon_url=(
                str(embed_data["footer_icon"])
                if is_url(embed_data.get("footer_icon")) else None
            ),
        )
    if is_url(embed_data.get("thumbnail")):
        embed.set_thumbnail(url=str(embed_data["thumbnail"]))
    if is_url(embed_data.get("image")):
        embed.set_image(url=str(embed_data["image"]))

    return embed


def build_v2(data: dict):
    """
    A Components V2 layout assembled from the dashboard's blocks.

    Built directly rather than through utils.panels.Panel, because that
    one fixes the order (heading, text, image, buttons) and the whole
    point here is that the author decides.
    """
    from discord.ui import (
        ActionRow,
        Container,
        LayoutView,
        MediaGallery,
        Separator,
        TextDisplay,
    )

    view = LayoutView(timeout=None)
    container = Container(accent_color=parse_colour(data.get("color")))

    for block in data.get("blocks") or []:
        block_type = str(block.get("type") or "")

        if block_type == "text":
            text = str(block.get("text") or "").strip()
            if text:
                container.add_item(TextDisplay(text))

        elif block_type == "divider":
            container.add_item(Separator(visible=not block.get("invisible")))

        elif block_type == "image":
            url = str(block.get("url") or "")
            if is_url(url):
                container.add_item(MediaGallery(discord.MediaGalleryItem(url)))

        elif block_type == "buttons":
            row: list = []
            for button in (block.get("buttons") or [])[:5]:
                url = str(button.get("url") or "")
                if not is_url(url):
                    continue
                row.append(discord.ui.Button(
                    label=str(button.get("label") or "Link")[: LIMITS["button_label"]],
                    url=url,
                    emoji=str(button.get("emoji") or "") or None,
                    # A URL button is always link-styled; Discord rejects
                    # any other style together with a url.
                    style=discord.ButtonStyle.link,
                ))
            if row:
                container.add_item(ActionRow(*row))

    view.add_item(container)
    return view


def build(data: dict) -> dict:
    """
    Turn the description into kwargs for `channel.send(...)`.

    Returns a dict so the caller does not have to know which of content,
    embed or view was produced.
    """
    kind = str(data.get("kind") or "text")

    if kind == "embed":
        out: dict = {"embed": build_embed(data.get("embed") or {})}
        # An embed may carry plain text above it, which is the only way to
        # ping somebody: a mention inside an embed does not notify.
        content = str(data.get("content") or "").strip()
        if content:
            out["content"] = content[: LIMITS["content"]]
        return out

    if kind == "v2":
        # A V2 layout cannot be combined with content or embeds; Discord
        # rejects the message outright.
        return {"view": build_v2(data)}

    return {"content": str(data.get("content") or "")[: LIMITS["content"]]}


def describe(data: dict) -> dict:
    """A short summary for the dashboard's confirmation step."""
    kind = str(data.get("kind") or "text")
    if kind == "v2":
        blocks = data.get("blocks") or []
        counts: dict[str, int] = {}
        for block in blocks:
            key = str(block.get("type") or "?")
            counts[key] = counts.get(key, 0) + 1
        return {"kind": kind, "blocks": len(blocks), "by_type": counts}

    if kind == "embed":
        embed = data.get("embed") or {}
        return {"kind": kind, "fields": len(embed.get("fields") or [])}

    return {"kind": kind, "length": len(str(data.get("content") or ""))}
