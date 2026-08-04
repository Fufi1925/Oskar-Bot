#!/usr/bin/env python3
"""
Das Willkommens-Banner mit Profilbild.

Der Fehler, um den es hier geht: das Bild wurde als Datei *neben* der
Nachricht mitgeschickt. Eine Components-V2-Nachricht rendert aber
ausschließlich ihre Komponenten -- die Datei wurde hochgeladen und nie
angezeigt. Es kam weiterhin die alte Begrüßung ohne Bild an, obwohl der
Renderer einwandfrei arbeitete.

Deshalb wird hier nicht "wurde eine Datei mitgegeben" geprüft, sondern
ob im gerenderten View wirklich eine Bildkomponente steckt.

Run:  python3 tests/test_welcome_banner.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

failures: list[str] = []

# Discord-Komponententyp einer MediaGallery.
MEDIA_GALLERY = 12
CONTAINER = 17


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def component_types(view) -> list[int]:
    found: list[int] = []

    def walk(items):
        for item in items:
            found.append(item.get("type"))
            walk(item.get("components", []) or [])

    walk(view.to_components())
    return found


def test_the_image_ends_up_inside_the_view():
    """Der eigentliche Bug: ein Anhang allein reicht bei V2 nicht."""

    print("\nDas Bild steckt in der View, nicht daneben")
    import discord

    from utils.panels import from_embed

    embed = discord.Embed(title="Willkommen!", description="Schön, dass du da bist.")
    view = from_embed(embed)

    check("ohne Bild ist keins drin",
          MEDIA_GALLERY not in component_types(view))

    added = view.add_image("attachment://willkommen.png")
    check("add_image meldet Erfolg", added is True)
    check("danach ist eine Bildkomponente da",
          MEDIA_GALLERY in component_types(view),
          str(component_types(view)))

    # Und zwar *im* Container: ein Element neben der Karte säße optisch
    # außerhalb, genau wie damals die J2C-Knöpfe.
    raw = view.to_components()
    check("die View hat einen Container", raw and raw[0].get("type") == CONTAINER)
    inner = [c.get("type") for c in (raw[0].get("components") or [])]
    check("das Bild sitzt im Container", MEDIA_GALLERY in inner, str(inner))


def test_the_greeting_wires_the_attachment_to_the_view():
    """Die Datei und der Verweis darauf müssen zusammenpassen."""

    print("\nDateiname und Verweis stimmen überein")

    path = os.path.join(BOT, "cogs", "events", "greet2.py")
    source = open(path, encoding="utf-8").read()
    code = "\n".join(
        line for line in source.splitlines() if not line.strip().startswith("#")
    )

    check("das Banner wird in die View gehängt",
          "add_image(f\"attachment://{banner.filename}\")" in code,
          "sonst lädt Discord die Datei hoch und zeigt sie nicht")
    check("die Datei wird auch mitgeschickt",
          '"file": banner' in code)

    # Ohne Embed gibt from_embed None zurück -- dann braucht es ein
    # eigenes Panel, sonst hat das Bild wieder keinen Platz.
    check("auch der Nur-Text-Fall trägt das Bild",
          "image_url=f\"attachment://{banner.filename}\"" in code,
          "bei einer Text-Begrüßung fiele das Banner sonst weg")


def test_the_banner_renders():
    print("\nDas Bild entsteht wirklich")
    from utils import welcome_card

    if not welcome_card.PIL_AVAILABLE:
        check("Pillow ist da", False, "ohne Pillow gibt es kein Banner")
        return

    buffer = welcome_card.render(
        name="Fufi", avatar_bytes=None,
        guild_name="University Support", member_count=1247,
    )
    check("ohne Avatar kommt ein Bild", buffer is not None)
    if buffer:
        data = buffer.getvalue()
        check("es ist ein PNG", data[:8] == b"\x89PNG\r\n\x1a\n", str(data[:8]))
        check("und nicht leer", len(data) > 5000, f"{len(data)} Bytes")


def test_a_broken_avatar_does_not_lose_the_banner():
    """Ein kaputtes Profilbild darf die Begrüßung nicht kosten."""

    print("\nEin kaputter Avatar wird verkraftet")
    from utils import welcome_card

    if not welcome_card.PIL_AVAILABLE:
        return

    buffer = welcome_card.render(
        name="Fufi", avatar_bytes=b"kein bild, nur muell",
        guild_name="S", member_count=5,
    )
    check("es kommt trotzdem ein Banner", buffer is not None)


def test_the_member_number_is_readable():
    """»1.2K« hilft niemandem, der seine Nummer sehen will."""

    print("\nDie Mitgliedsnummer steht ausgeschrieben")

    path = os.path.join(BOT, "utils", "welcome_card.py")
    source = open(path, encoding="utf-8").read()
    code = re.sub(r"#.*$", "", source, flags=re.M)

    check("compact() wird nicht mehr benutzt",
          "compact(member_count)" not in code,
          "eine Mitgliedsnummer will man genau sehen")
    check("es gibt einen Tausenderpunkt",
          'f"Mitglied Nr. {member_count:,}"' in code)


def test_long_names_shrink_instead_of_being_cut():
    """Gemessen, nicht im Quelltext nachgelesen.

    Ein erster Versuch prüfte nur, ob »_fit(« vorkommt. Damit blieb der
    Test grün, als ich die Schriftgröße wieder fest verdrahtete -- der
    Name lief aus dem Bild und niemand merkte es. Also wird jetzt
    gerechnet, wie breit der Text tatsächlich wird.
    """

    print("\nEin langer Name wird kleiner, nicht abgeschnitten")
    from PIL import Image, ImageDraw

    from utils import welcome_card

    if not welcome_card.PIL_AVAILABLE:
        return

    long_name = "EinSehrLangerBenutzernameHierDrin"
    buffer = welcome_card.render(
        name=long_name, avatar_bytes=None, guild_name="S", member_count=5,
    )
    check("auch damit kommt ein Bild", buffer is not None)

    # Am *fertigen Bild* messen, nicht mit _fit nachrechnen.
    #
    # Mein zweiter Versuch rief _fit selbst auf und prüfte dessen
    # Ergebnis. Das ist dieselbe Falle in neu: die Mutation hat nicht
    # _fit kaputt gemacht, sondern render() dazu gebracht, _fit gar
    # nicht mehr zu benutzen. Der Test rechnete brav weiter und blieb
    # grün, während der Name aus dem Bild lief.
    import io

    left = 72 + welcome_card.AVATAR + 56
    room = welcome_card.WIDTH - left - 64
    edge = left + room + 4

    def bright_pixels_right_of(name: str, x_from: int) -> int:
        rendered = welcome_card.render(
            name=name, avatar_bytes=None, guild_name="S", member_count=5
        )
        image = Image.open(io.BytesIO(rendered.getvalue())).convert("RGB")
        count = 0
        # Nur das Band, in dem der Name steht.
        for x in range(x_from, image.width):
            for y in range(100, 190):
                red, green, blue = image.getpixel((x, y))
                if red > 200 and green > 200 and blue > 200:
                    count += 1
        return count

    check("der lange Name bleibt im Textbereich",
          bright_pixels_right_of(long_name, edge) == 0,
          f"{bright_pixels_right_of(long_name, edge)} helle Pixel jenseits x={edge}")

    # Und ein kurzer Name bleibt groß -- sonst wäre »passt immer« auch
    # mit Schriftgröße 8 erfüllt.
    draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    small_font, _ = welcome_card._fit(
        draw, "Fufi", welcome_card._font, 54, room, 26
    )
    check("ein kurzer Name bleibt in voller Größe",
          getattr(small_font, "size", 54) == 54,
          str(getattr(small_font, "size", "?")))

    check("nichts wird mit … gekürzt",
          "…" not in open(
              os.path.join(BOT, "utils", "welcome_card.py"), encoding="utf-8"
          ).read().replace("# ", ""),
          "ein langer Name ist genau der Fall, wo man ihn sehen will")


def main():
    test_the_image_ends_up_inside_the_view()
    test_the_greeting_wires_the_attachment_to_the_view()
    test_the_banner_renders()
    test_a_broken_avatar_does_not_lose_the_banner()
    test_the_member_number_is_readable()
    test_long_names_shrink_instead_of_being_cut()

    print()
    if failures:
        print(f"FAILED {len(failures)}")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("Alle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
