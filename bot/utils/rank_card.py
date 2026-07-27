# ╔══════════════════════════════════════════════════════════════════╗
# ║   Rank cards                                                     ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The rank card, as an image and as a Components V2 panel.

The old version had seven designs spread over roughly 1500 lines of
Pillow code, each one repeating the same avatar/progress-bar logic with
slightly different colours, and several of them referenced helper methods
with mismatched argument orders. There is one design here, drawn once.

Falling back matters more than the design does: if Pillow is missing, the
font cannot be loaded or the avatar download fails, the caller gets the
text panel instead of an exception.
"""

from __future__ import annotations

import io
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the deployment
    PIL_AVAILABLE = False

WIDTH, HEIGHT = 900, 300
BACKGROUND = (16, 35, 63)
PANEL = (13, 27, 49)
TEXT = (255, 255, 255)
MUTED = (148, 163, 184)
TRACK = (30, 41, 59)

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "assets/fonts/minecraft.ttf",
]


def _font(size: int, bold: bool = True):
    """A font at `size`, or the bitmap default if none can be loaded."""
    if not PIL_AVAILABLE:
        return None
    for path in FONT_PATHS:
        if bold and "Bold" not in path and path.endswith(".ttf"):
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    for path in FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def compact(number: int) -> str:
    """12345 → 12.3K, so long numbers cannot run into the next column."""
    number = int(number or 0)
    if number < 1000:
        return str(number)
    if number < 1_000_000:
        return f"{number / 1000:.1f}K".replace(".0K", "K")
    return f"{number / 1_000_000:.1f}M".replace(".0M", "M")


def progress_bar(current: int, total: int, length: int = 16) -> str:
    """A text progress bar for the V2 card."""
    if total <= 0:
        return "▰" * length
    filled = max(0, min(length, round(length * current / total)))
    return "▰" * filled + "▱" * (length - filled)


def _rounded(draw, box, radius, fill):
    try:
        draw.rounded_rectangle(box, radius=radius, fill=fill)
    except AttributeError:  # very old Pillow
        draw.rectangle(box, fill=fill)


async def render_image(
    *,
    name: str,
    avatar_bytes: bytes | None,
    level: int,
    rank: int,
    xp: int,
    into_level: int,
    level_needs: int,
    messages: int,
    accent: int = 0x5865F2,
) -> io.BytesIO | None:
    """
    Draw the rank card. Returns None when it cannot be drawn, so the
    caller can fall back to the text panel instead of failing.
    """
    if not PIL_AVAILABLE:
        return None

    try:
        accent_rgb = (
            (accent >> 16) & 0xFF, (accent >> 8) & 0xFF, accent & 0xFF
        )

        card = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        draw = ImageDraw.Draw(card)

        _rounded(draw, (20, 20, WIDTH - 20, HEIGHT - 20), 28, PANEL)
        # A stripe in the guild's accent colour, so the card matches the
        # embeds the rest of the bot sends.
        _rounded(draw, (20, 20, 32, HEIGHT - 20), 6, accent_rgb)

        avatar_size = 160
        avatar_x, avatar_y = 60, (HEIGHT - avatar_size) // 2

        if avatar_bytes:
            try:
                avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                avatar = avatar.resize((avatar_size, avatar_size), Image.LANCZOS)

                mask = Image.new("L", (avatar_size, avatar_size), 0)
                ImageDraw.Draw(mask).ellipse(
                    (0, 0, avatar_size, avatar_size), fill=255
                )
                card.paste(avatar, (avatar_x, avatar_y), mask)
            except Exception:
                avatar_bytes = None

        if not avatar_bytes:
            draw.ellipse(
                (avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size),
                fill=TRACK,
            )

        draw.ellipse(
            (avatar_x - 4, avatar_y - 4,
             avatar_x + avatar_size + 4, avatar_y + avatar_size + 4),
            outline=accent_rgb, width=4,
        )

        font_name = _font(38)
        font_stat = _font(24)
        font_small = _font(18, bold=False)

        left = avatar_x + avatar_size + 40

        display = name if len(name) <= 18 else name[:17] + "…"
        draw.text((left, 62), display, font=font_name, fill=TEXT)

        draw.text(
            (left, 112),
            f"Level {level}   ·   Platz #{rank}   ·   {compact(messages)} Nachrichten",
            font=font_small, fill=MUTED,
        )

        bar_x0, bar_x1 = left, WIDTH - 60
        bar_y0, bar_y1 = 168, 196
        _rounded(draw, (bar_x0, bar_y0, bar_x1, bar_y1), 14, TRACK)

        if level_needs > 0:
            ratio = max(0.0, min(1.0, into_level / level_needs))
            filled = int((bar_x1 - bar_x0) * ratio)
            # Below ~28px a rounded rectangle renders as a smear.
            if filled >= 28:
                _rounded(draw, (bar_x0, bar_y0, bar_x0 + filled, bar_y1), 14, accent_rgb)

        draw.text(
            (bar_x0, 210),
            f"{compact(into_level)} / {compact(level_needs)} XP",
            font=font_stat, fill=TEXT,
        )

        total = f"{compact(xp)} XP gesamt"
        try:
            box = draw.textbbox((0, 0), total, font=font_small)
            draw.text((bar_x1 - (box[2] - box[0]), 216), total,
                      font=font_small, fill=MUTED)
        except Exception:
            draw.text((bar_x1 - 140, 216), total, font=font_small, fill=MUTED)

        buffer = io.BytesIO()
        card.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception:
        return None


def render_panel(
    *,
    name: str,
    level: int,
    rank: int,
    xp: int,
    into_level: int,
    level_needs: int,
    messages: int,
    accent: int = 0x5865F2,
    avatar_url: str | None = None,
) -> Any:
    """The same information as a Components V2 panel."""
    from utils.panels import Panel

    bar = progress_bar(into_level, level_needs)
    percent = round(100 * into_level / level_needs) if level_needs else 100

    body = (
        f"**Level {level}**  ·  Platz **#{rank}**\n"
        f"{bar}  {percent}%\n"
        f"`{into_level:,}` / `{level_needs:,}` XP bis Level {level + 1}"
    ).replace(",", ".")

    footer = (
        f"**{xp:,}** XP gesamt  ·  **{messages:,}** Nachrichten"
    ).replace(",", ".")

    return Panel(name, body, footer, accent=accent, image_url=None)


def render_leaderboard_panel(
    *, guild_name: str, entries: list[dict], names: dict, accent: int = 0x5865F2
) -> Any:
    """The leaderboard as a V2 panel."""
    from utils.panels import Panel

    if not entries:
        return Panel(
            f"Bestenliste — {guild_name}",
            "Hier hat noch niemand XP gesammelt.",
            accent=accent,
        )

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    lines = []
    for entry in entries:
        place = entry["rank"]
        marker = medals.get(place, f"`#{place}`")
        name = names.get(entry["user_id"], f"Unbekannt ({entry['user_id']})")
        lines.append(
            f"{marker} **{name}** — Level {entry['level']} · "
            f"{compact(entry['xp'])} XP"
        )

    return Panel(f"Bestenliste — {guild_name}", "\n".join(lines), accent=accent)
