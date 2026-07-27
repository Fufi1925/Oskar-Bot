# ╔══════════════════════════════════════════════════════════════════╗
# ║   Welcome messages: one renderer for the bot and the dashboard   ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Rendering a welcome message, in exactly one place.

There used to be two implementations. The greeter in
`cogs/events/greet2.py` filled `{server_name}` and `{server_membercount}`
and understood the whole embed (author, footer, thumbnail, image); the
dashboard's "send a preview" route in `api/routes/actions.py` filled
`{server}` and `{count}` and only looked at title, description and
footer. So the preview showed something the members would never see, and
half the placeholders came out as literal `{server_name}` text.

Both now call `render()` here, which means a preview is the real thing.
"""

from __future__ import annotations

import json
import re
from typing import Any

import discord

DEFAULT_COLOUR = 0x2F3136

# Every placeholder, with a short description. The dashboard reads this
# list so the help text next to the input can never drift from the code.
PLACEHOLDERS: dict[str, str] = {
    "user": "Erwähnt das Mitglied (@Name)",
    "user_name": "Der Benutzername",
    "user_nick": "Der Anzeigename auf dem Server",
    "user_id": "Die ID des Mitglieds",
    "user_avatar": "Link zum Profilbild",
    "user_joindate": "Wann das Mitglied beigetreten ist",
    "user_createdate": "Wann der Account erstellt wurde",
    "server_name": "Name des Servers",
    "server_id": "ID des Servers",
    "server_membercount": "Wie viele Mitglieder der Server hat",
    "server_icon": "Link zum Serverbild",
    "timestamp": "Der aktuelle Zeitpunkt",
}


def placeholders(member) -> dict[str, Any]:
    """The values behind every `{...}` for one member."""
    guild = member.guild
    joined = getattr(member, "joined_at", None)
    created = getattr(member, "created_at", None)

    return {
        "user": member.mention,
        # display_avatar covers members without their own picture; plain
        # `.avatar` is None for them and used to raise.
        "user_avatar": member.display_avatar.url,
        "user_name": member.name,
        "user_id": member.id,
        "user_nick": member.display_name,
        "user_joindate": joined.strftime("%a, %b %d, %Y") if joined else "—",
        "user_createdate": created.strftime("%a, %b %d, %Y") if created else "—",
        "server_name": guild.name,
        "server_id": guild.id,
        "server_membercount": guild.member_count,
        "server_icon": (
            guild.icon.url if guild.icon
            else "https://cdn.discordapp.com/embed/avatars/0.png"
        ),
        "timestamp": discord.utils.format_dt(discord.utils.utcnow()),
    }


def fill(text: str, values: dict[str, Any]) -> str:
    """
    Replace `{name}` with its value, case-insensitively.

    An unknown placeholder is left as it was rather than raising — a typo
    in the dashboard should not stop the greeting from being sent.
    """
    lowered = {key.lower(): value for key, value in values.items()}

    def replace(match: re.Match) -> str:
        name = match.group(1).lower()
        return str(lowered.get(name, "{" + name + "}"))

    return re.sub(r"\{(\w+)\}", replace, text or "")


def parse_colour(value) -> int:
    """Accept `#3498db`, `3498db` or a plain integer."""
    if value is None or value == "":
        return DEFAULT_COLOUR
    if isinstance(value, int):
        return value
    text = str(value).strip().lstrip("#")
    try:
        return int(text, 16)
    except ValueError:
        return DEFAULT_COLOUR


def _valid_url(text: str) -> str | None:
    """Discord rejects the whole embed on a malformed URL, so check first."""
    text = (text or "").strip()
    return text if text.startswith(("http://", "https://")) else None


def build_embed(embed_info: dict, values: dict[str, Any]) -> discord.Embed:
    """The embed as the members will see it."""
    embed = discord.Embed(
        title=fill(embed_info.get("title", ""), values) or None,
        description=fill(embed_info.get("description", ""), values) or None,
        color=parse_colour(embed_info.get("color")),
    )
    embed.timestamp = discord.utils.utcnow()

    if embed_info.get("footer_text"):
        embed.set_footer(
            text=fill(embed_info["footer_text"], values),
            icon_url=_valid_url(fill(embed_info.get("footer_icon", ""), values)),
        )
    if embed_info.get("author_name"):
        embed.set_author(
            name=fill(embed_info["author_name"], values),
            icon_url=_valid_url(fill(embed_info.get("author_icon", ""), values)),
        )

    thumbnail = _valid_url(fill(embed_info.get("thumbnail", ""), values))
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    image = _valid_url(fill(embed_info.get("image", ""), values))
    if image:
        embed.set_image(url=image)

    return embed


def render(row: dict, member) -> tuple[str | None, discord.Embed | None]:
    """
    Turn a stored welcome configuration into what gets posted.

    `row` holds welcome_type, welcome_message and embed_data (the JSON
    string as it sits in the database). Returns (content, embed); either
    may be None, and both being None means nothing is configured.
    """
    values = placeholders(member)
    welcome_type = (row.get("welcome_type") or "simple").lower()

    if welcome_type == "embed":
        raw = row.get("embed_data")
        if not raw:
            return None, None
        try:
            embed_info = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except (ValueError, TypeError):
            return None, None

        # An embed may carry plain text above it as well; that field was
        # written by the setup command but never read back.
        content = fill(embed_info.get("message", ""), values) or None
        return content, build_embed(embed_info, values)

    message = row.get("welcome_message")
    if not message:
        return None, None
    return fill(message, values), None
