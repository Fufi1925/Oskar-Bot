# ╔══════════════════════════════════════════════════════════════════╗
# ║   Welcome banner                                                 ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
The image posted when somebody joins: avatar, name, member count.

Same approach as the rank card next door -- one design, drawn once, and
every failure falls back to None so the caller posts the text version
instead of raising. A greeting that crashes is worse than a plain one:
the member is already in the server either way.

The look follows the dashboard: dark navy, a round avatar with a glowing
ring in the accent colour, the name large, the rest quiet underneath.
"""

from __future__ import annotations

import io

try:
    from PIL import Image, ImageDraw, ImageFilter
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the deployment
    PIL_AVAILABLE = False

from utils.rank_card import _font, _rounded

WIDTH, HEIGHT = 1000, 340

BACKGROUND = (7, 21, 39)      # --background of the dashboard
PANEL = (16, 35, 63)          # the card surface
TEXT = (255, 255, 255)
MUTED = (148, 163, 184)
FAINT = (71, 85, 105)

AVATAR = 168
RING = 6


def _glow(size: tuple[int, int], box, radius: int, colour, blur: int):
    """A soft halo behind something, drawn on its own layer.

    Blurring is the whole point: drawing the ring straight onto the card
    gives a hard edge, and the design lives from the light bleeding out.
    """

    layer = Image.new("RGB", size, (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(box, fill=colour) if radius < 0 else _rounded(
        draw, box, radius, colour
    )
    return layer.filter(ImageFilter.GaussianBlur(blur))


def _fit(draw, text: str, font_for, start: int, limit: int, minimum: int):
    """Largest font size at which `text` still fits into `limit` pixels.

    Cutting the name off with an ellipsis was the first idea and it is
    worse: a long username is exactly the case where somebody wants to
    see their own name in the greeting.
    """

    size = start
    while size > minimum:
        font = font_for(size)
        if font is None:
            return None, 0
        try:
            width = draw.textlength(text, font=font)
        except Exception:
            return font, 0
        if width <= limit:
            return font, width
        size -= 4
    font = font_for(minimum)
    return font, 0


def _background(background_bytes: bytes | None):
    """
    Der Hintergrund: eigenes Bild, sonst die Grundfarbe.

    Das eigene Bild wird beschnitten statt verzerrt -- ein gestrecktes
    Foto sieht immer nach Fehler aus. Darueber liegt ein dunkler
    Schleier, ohne den heller Text auf einem hellen Bild unlesbar ist.
    """
    if not background_bytes:
        return Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)

    try:
        bild = Image.open(io.BytesIO(background_bytes)).convert("RGB")
        # Seitenverhaeltnis wahren, Ueberstand abschneiden.
        ziel = WIDTH / HEIGHT
        quelle = bild.width / bild.height
        if quelle > ziel:
            neue_breite = int(bild.height * ziel)
            links = (bild.width - neue_breite) // 2
            bild = bild.crop((links, 0, links + neue_breite, bild.height))
        elif quelle < ziel:
            neue_hoehe = int(bild.width / ziel)
            oben = (bild.height - neue_hoehe) // 2
            bild = bild.crop((0, oben, bild.width, oben + neue_hoehe))
        bild = bild.resize((WIDTH, HEIGHT), Image.LANCZOS)

        # Der Schleier. 55 % Deckung ist der Punkt, an dem das Bild noch
        # zu erkennen ist und weisse Schrift darauf sicher liest.
        schleier = Image.new("RGB", (WIDTH, HEIGHT), (5, 12, 24))
        return Image.blend(bild, schleier, 0.55)
    except Exception:
        # Kaputtes oder fremdes Format: lieber die Grundfarbe als gar
        # keine Karte.
        return Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)


def render(
    *,
    name: str,
    avatar_bytes: bytes | None,
    guild_name: str,
    member_count: int,
    accent: int = 0x3B82F6,
    background_bytes: bytes | None = None,
    label: str = "WILLKOMMEN",
    subtitle: str | None = None,
    counter_text: str | None = None,
) -> io.BytesIO | None:
    """
    The banner as PNG bytes, or None when it cannot be drawn.

    ``background_bytes`` legt ein eigenes Bild darunter, ``label``,
    ``subtitle`` und ``counter_text`` machen dieselbe Karte fuer den
    Abschied brauchbar -- sonst stuende dort "WILLKOMMEN", wenn jemand
    geht.
    """

    if not PIL_AVAILABLE:
        return None

    try:
        accent_rgb = ((accent >> 16) & 0xFF, (accent >> 8) & 0xFF, accent & 0xFF)

        eigenes_bild = background_bytes is not None
        card = _background(background_bytes)

        avatar_x = 72
        avatar_y = (HEIGHT - AVATAR) // 2
        ring_box = (
            avatar_x - RING, avatar_y - RING,
            avatar_x + AVATAR + RING, avatar_y + AVATAR + RING,
        )

        # Two halos: a wide dim one for the atmosphere, a tight bright
        # one for the edge. One alone looks either muddy or flat.
        for blur, shrink, strength in ((34, -26, 0.55), (12, -8, 1.0)):
            box = (
                ring_box[0] + shrink, ring_box[1] + shrink,
                ring_box[2] - shrink, ring_box[3] - shrink,
            )
            tinted = tuple(int(value * strength) for value in accent_rgb)
            halo = _glow((WIDTH, HEIGHT), box, -1, tinted, blur)
            card = Image.blend(card, halo, 0.5)

        draw = ImageDraw.Draw(card)

        # The panel goes on top of the glow, so the halo only shows
        # around the avatar and not across the whole card.
        #
        # Bei einem eigenen Hintergrund entfaellt es: die Flaeche wuerde
        # genau das Bild verdecken, das jemand eingestellt hat.
        if not eigenes_bild:
            _rounded(draw, (28, 28, WIDTH - 28, HEIGHT - 28), 32, PANEL)

        # Re-draw the tight halo above the panel, otherwise the panel
        # covers exactly the part that should be lit.
        halo = _glow((WIDTH, HEIGHT), ring_box, -1, accent_rgb, 16)
        card = Image.blend(card, halo, 0.42)
        draw = ImageDraw.Draw(card)

        drawn = False
        if avatar_bytes:
            try:
                avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                avatar = avatar.resize((AVATAR, AVATAR), Image.LANCZOS)
                mask = Image.new("L", (AVATAR, AVATAR), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, AVATAR, AVATAR), fill=255)
                card.paste(avatar, (avatar_x, avatar_y), mask)
                drawn = True
            except Exception:
                # A broken or unreadable avatar must not lose the banner.
                drawn = False

        if not drawn:
            draw.ellipse(
                (avatar_x, avatar_y, avatar_x + AVATAR, avatar_y + AVATAR),
                fill=(30, 41, 59),
            )
            initial = (name or "?").strip()[:1].upper() or "?"
            font = _font(76)
            if font is not None:
                try:
                    width = draw.textlength(initial, font=font)
                except Exception:
                    width = 40
                draw.text(
                    (avatar_x + AVATAR / 2 - width / 2, avatar_y + AVATAR / 2 - 52),
                    initial, font=font, fill=MUTED,
                )

        draw.ellipse(ring_box, outline=accent_rgb, width=RING)

        left = avatar_x + AVATAR + 56
        room = WIDTH - left - 64

        label_font = _font(22, bold=False)
        if label_font is not None:
            draw.text((left, 84), label, font=label_font, fill=accent_rgb)

        name_font, _width = _fit(draw, name, _font, 54, room, 26)
        if name_font is not None:
            draw.text((left, 120), name, font=name_font, fill=TEXT)

        sub_font = _font(24, bold=False)
        if sub_font is not None:
            zeile = subtitle if subtitle is not None else f"auf {guild_name}"
            server, _ = _fit(draw, zeile, lambda s: _font(s, bold=False),
                             24, room, 16)
            draw.text((left, 190), zeile,
                      font=server or sub_font, fill=MUTED)
            # Ausgeschrieben mit Tausenderpunkt, nicht "1.2K": bei einer
            # Mitgliedsnummer will man die genaue Zahl sehen -- sie ist
            # der ganze Reiz an der Zeile. compact() ist fuer
            # Nachrichtenzaehler da, wo die Groessenordnung reicht.
            zaehler = (
                counter_text
                if counter_text is not None
                else f"Mitglied Nr. {member_count:,}".replace(",", ".")
            )
            draw.text((left, 226), zaehler, font=sub_font, fill=FAINT)

        buffer = io.BytesIO()
        card.save(buffer, format="PNG")
        buffer.seek(0)
        return buffer
    except Exception:
        # Same rule as the rank card: no greeting is better than a
        # traceback, and the caller has a text version ready.
        return None
