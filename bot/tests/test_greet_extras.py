#!/usr/bin/env python3
"""
Bild bei Begruessung und Abschied -- und der Abschied selbst.

Drei Anforderungen, danach ist der Test sortiert:

  1. Das Willkommensbild muss sich abschalten lassen. Vorher ging es
     immer mit, sobald eine Begruessung eingestellt war.
  2. Ein eigenes Hintergrundbild statt des gezeichneten Verlaufs.
  3. Dasselbe fuer den Abschied -- den gab es gar nicht,
     ``on_member_remove`` wurde im Begruessungs-Cog nirgends behandelt.

Run:  python3 tests/test_greet_extras.py
"""

import ast
import asyncio
import io
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from utils import greet_extras as ge  # noqa: E402

failures: list[str] = []

GUILD = 1530378233579704370


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(rel: str) -> str:
    return open(os.path.join(BOT, rel), encoding="utf-8").read()


def strip_py(src: str) -> str:
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.split("\n")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                first = node.body[0]
                for i in range(first.lineno - 1, first.end_lineno):
                    lines[i] = ""
    return "\n".join(lines)


# ── 1. Speichern und Vorgaben ────────────────────────────────────────

async def test_speichern():
    print("\n1. Einstellungen")
    vorgabe = await ge.get(GUILD)
    # Das bisherige Verhalten bleibt die Vorgabe: wer nichts einstellt,
    # bekommt weiterhin sein Willkommensbild.
    check("Willkommensbild ist vorgegeben an", vorgabe["welcome_image_enabled"])
    check("Abschied ist vorgegeben aus", not vorgabe["leave_enabled"])

    await ge.save(GUILD, {"welcome_image_enabled": False})
    check("Bild laesst sich abschalten",
          not (await ge.get(GUILD))["welcome_image_enabled"])

    # Teilweises Speichern darf nichts anderes zuruecksetzen.
    await ge.save(GUILD, {"leave_enabled": True})
    stand = await ge.get(GUILD)
    check("anderes Feld bleibt erhalten",
          not stand["welcome_image_enabled"] and stand["leave_enabled"],
          f"({stand})")

    await ge.save(GUILD, {"leave_message": "x" * 3000})
    check("Nachricht wird gekuerzt",
          len((await ge.get(GUILD))["leave_message"]) == 2000)

    await ge.save(GUILD, {"leave_channel_id": "123456789012345678"})
    check("Kanal wird gespeichert",
          (await ge.get(GUILD))["leave_channel_id"] == 123456789012345678)
    await ge.save(GUILD, {"leave_channel_id": "keine Zahl"})
    check("unsinniger Kanal wird zu 0",
          (await ge.get(GUILD))["leave_channel_id"] == 0)


# ── 2. Bildadressen ──────────────────────────────────────────────────

async def test_bildadressen():
    print("\n2. Nur echte Bildadressen")
    gut = [
        "https://example.com/bild.png",
        "https://example.com/a.JPG",
        "https://cdn.discordapp.com/x/y.webp?ex=1&is=2&hm=abc",
        "https://example.com/pfad/zum/bild.gif",
    ]
    schlecht = [
        "http://example.com/bild.png",      # kein https
        "https://example.com/seite.html",   # kein Bild
        "https://example.com/",             # keine Endung
        "javascript:alert(1)",
        "example.com/bild.png",             # kein Schema
        "",
    ]
    for url in gut:
        check(f"erlaubt: {url[:44]}", ge.valid_image_url(url))
    for url in schlecht:
        check(f"abgelehnt: {url[:44] or '(leer)'}", not ge.valid_image_url(url))

    # Die Signatur hinter dem ? darf die Endungspruefung nicht stoeren --
    # sonst waere jede Discord-CDN-Adresse ungueltig.
    check("Discord-CDN mit Signatur geht",
          ge.valid_image_url("https://cdn.discordapp.com/a.png?ex=68&is=67&hm=ff"))

    await ge.save(GUILD, {"welcome_image_url": "https://example.com/ok.png"})
    check("gueltige Adresse wird gespeichert",
          (await ge.get(GUILD))["welcome_image_url"] == "https://example.com/ok.png")

    try:
        await ge.save(GUILD, {"welcome_image_url": "http://example.com/x.png"})
    except ValueError:
        check("ungueltige Adresse wird abgelehnt", True)
    else:
        check("ungueltige Adresse wird abgelehnt", False, "-> ging durch")

    check("die alte Adresse steht noch",
          (await ge.get(GUILD))["welcome_image_url"] == "https://example.com/ok.png")

    await ge.save(GUILD, {"welcome_image_url": ""})
    check("leeren geht (= gezeichneter Hintergrund)",
          (await ge.get(GUILD))["welcome_image_url"] == "")


# ── 3. Platzhalter ───────────────────────────────────────────────────

def test_platzhalter():
    print("\n3. Platzhalter im Abschiedstext")

    class M:
        id = 42
        mention = "<@42>"
        name = "fufi"
        display_name = "Fufi"

    class G:
        name = "LSPD I Dunya"
        member_count = 1234
        members: list = []

    text = ge.render_text(
        "{user} alias {user.name} ({user.display}, {user.id}) verlaesst "
        "{server} -- noch {count}.",
        M(), G(),
    )
    for teil in ("<@42>", "fufi", "Fufi", "42", "LSPD I Dunya", "1234"):
        check(f"'{teil}' eingesetzt", teil in text, f"({text})")
    check("keine Platzhalter uebrig", "{" not in text, f"({text})")
    check("leere Vorlage bleibt leer", ge.render_text("", M(), G()) == "")


# ── 4. Die Karte ─────────────────────────────────────────────────────

def test_karte():
    print("\n4. Die gezeichnete Karte")
    from utils import welcome_card

    if not getattr(welcome_card, "PIL_AVAILABLE", False):
        check("Pillow ist da", False, "-> ohne Pillow kann nichts gezeichnet werden")
        return

    from PIL import Image

    def als_bild(puffer):
        return Image.open(io.BytesIO(puffer.getvalue())).convert("RGB")

    standard = welcome_card.render(
        name="Fufi", avatar_bytes=None, guild_name="Server", member_count=1234
    )
    check("Willkommenskarte entsteht", standard is not None)

    # Jede der drei Beschriftungen einzeln pruefen.
    #
    # "die Karten unterscheiden sich" reicht nicht: aendert man nur die
    # Ueberschrift, sind sie auch verschieden -- und eine Unterzeile,
    # die still bei "auf Server" bleibt, faellt nicht auf. Also wird
    # jeder Bereich fuer sich verglichen, indem genau ein Wert
    # abweicht.
    grund = dict(name="Fufi", avatar_bytes=None, guild_name="Server",
                 member_count=1234)

    nur_label = welcome_card.render(**grund, label="TSCHUESS")
    check("die Ueberschrift wirkt sich aus",
          als_bild(nur_label).crop((300, 70, 900, 110)).tobytes()
          != als_bild(standard).crop((300, 70, 900, 110)).tobytes(),
          "-> label wird ignoriert, auf dem Abschied stuende WILLKOMMEN")

    nur_subtitle = welcome_card.render(**grund, subtitle="hat den Server verlassen")
    check("die Unterzeile wirkt sich aus",
          als_bild(nur_subtitle).crop((300, 180, 900, 220)).tobytes()
          != als_bild(standard).crop((300, 180, 900, 220)).tobytes(),
          "-> subtitle wird ignoriert")

    nur_counter = welcome_card.render(**grund, counter_text="Noch 1.233 Mitglieder")
    check("die Zaehlzeile wirkt sich aus",
          als_bild(nur_counter).crop((300, 216, 900, 256)).tobytes()
          != als_bild(standard).crop((300, 216, 900, 256)).tobytes(),
          "-> counter_text wird ignoriert")

    abschied = welcome_card.render(
        **grund, label="TSCHUESS", subtitle="hat Server verlassen",
        counter_text="Noch 1.233 Mitglieder",
    )
    check("Abschiedskarte entsteht", abschied is not None)

    # Eigener Hintergrund.
    puffer = io.BytesIO()
    Image.new("RGB", (1920, 1080), (200, 60, 60)).save(puffer, "PNG")
    mit_bild = welcome_card.render(
        name="Fufi", avatar_bytes=None, guild_name="Server", member_count=5,
        background_bytes=puffer.getvalue(),
    )
    check("Karte mit eigenem Hintergrund entsteht", mit_bild is not None)

    ohne_bild = welcome_card.render(
        name="Fufi", avatar_bytes=None, guild_name="Server", member_count=5
    )

    # Ein rotes Bild muss die Karte roeter machen als dieselbe Karte
    # ohne Bild. Absolute Farbwerte taugen dafuer nicht: der Schleier
    # ueber dem Bild ist mit Absicht dunkel, damit weisse Schrift
    # darauf lesbar bleibt. Der Vergleich der beiden Karten ist die
    # ehrliche Probe.
    a, b = als_bild(mit_bild), als_bild(ohne_bild)
    rot_mit = sum(a.getpixel(p)[0] for p in ((6, 6), (500, 20), (950, 330)))
    rot_ohne = sum(b.getpixel(p)[0] for p in ((6, 6), (500, 20), (950, 330)))
    check("der eigene Hintergrund ist wirklich zu sehen",
          rot_mit > rot_ohne + 10, f"(rot {rot_mit} gegen {rot_ohne})")

    # Und in der Mitte darf keine Panel-Flaeche liegen, die das Bild
    # verdeckt -- sonst sieht man vom eingestellten Foto nur den Rand.
    # Ohne Bild ist dort das blaue Panel, mit Bild muss Rot ueberwiegen.
    mitte_mit = a.getpixel((600, 170))
    mitte_ohne = b.getpixel((600, 170))
    check("das Panel verdeckt das eigene Bild nicht",
          mitte_mit[0] > mitte_mit[2] and mitte_ohne[2] > mitte_ohne[0],
          f"(mit {mitte_mit}, ohne {mitte_ohne})")

    # Ein kaputtes Bild darf die Karte nicht verhindern -- eine
    # Begruessung ohne Hintergrund ist besser als gar keine.
    kaputt = welcome_card.render(
        name="Fufi", avatar_bytes=None, guild_name="Server", member_count=5,
        background_bytes=b"das ist kein bild",
    )
    check("kaputtes Bild faellt auf die Grundfarbe zurueck", kaputt is not None)

    # Ein schmales Bild muss beschnitten, nicht verzerrt werden.
    hoch = io.BytesIO()
    Image.new("RGB", (400, 1600), (20, 120, 200)).save(hoch, "PNG")
    check("hochkantes Bild geht auch",
          welcome_card.render(
              name="X", avatar_bytes=None, guild_name="S", member_count=1,
              background_bytes=hoch.getvalue()) is not None)


# ── 5. Der Cog ───────────────────────────────────────────────────────

async def test_cog():
    print("\n5. Begruessungs-Cog")
    quelle = read("cogs/events/greet2.py")
    baum = ast.parse(quelle)

    # Der Abschied braucht einen registrierten Listener -- eine Methode
    # ohne Dekorator wird nie aufgerufen.
    hat_listener = False
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.AsyncFunctionDef) and knoten.name == "on_member_remove":
            for dek in knoten.decorator_list:
                if isinstance(dek, ast.Call) and getattr(dek.func, "attr", "") == "listener":
                    hat_listener = True
    check("on_member_remove ist als Listener registriert", hat_listener,
          "-> ohne Dekorator feuert er nie")

    code = strip_py(quelle)
    check("der Abschied prueft, ob er an ist", "leave_enabled" in code)
    check("Bots loesen keinen Abschied aus", 'getattr(member, "bot", False)' in code)
    check("das eigene Bild wird geladen", "_fetch_image" in code)
    check("mit Zeitgrenze", "ClientTimeout" in code)

    # Bei Components V2 muss das Bild IN die View. Eine Datei
    # danebenzulegen laedt sie hoch, zeigt sie aber nicht an.
    entfernt = code[code.find("async def on_member_remove"):]
    check("das Abschiedsbild geht in die View",
          "attachment://" in entfernt and "Panel(" in entfernt,
          "-> sonst kommt der Abschied ohne Bild an")

    # Der Bild-Schalter wird AUSGEFUEHRT, nicht gesucht.
    #
    # Eine Textsuche traefe auch den Kommentar daneben und bliebe
    # gruen, wenn nur die Abfrage wegfaellt. Deshalb wird build_banner
    # wirklich aufgerufen -- mit ausgeschaltetem Schalter muss None
    # herauskommen, und zwar bevor irgendetwas geladen wird.
    print("     -- der Schalter, wirklich ausgefuehrt --")
    import types

    modul = types.ModuleType("greet_probe")
    modul.__dict__["__name__"] = "greet_probe"

    class FakeAsset:
        async def read(self):
            raise RuntimeError("darf nicht aufgerufen werden")

        def replace(self, **kw):
            return self

    class FakeGuild:
        name = "S"
        member_count = 3
        members: list = []
        me = None
        id = GUILD

    class FakeMember:
        display_name = "Fufi"
        display_avatar = FakeAsset()
        guild = FakeGuild()
        bot = False

    # Nur die Methode selbst laden, ohne den ganzen Cog aufzubauen.
    import inspect

    from cogs.events import greet2 as greet_modul

    build = greet_modul.greet.build_banner

    class Huelle:
        _fetch_image = greet_modul.greet._fetch_image

    async def lauf(kind, extras):
        return await build(Huelle(), FakeMember(), kind=kind, extras=extras)

    check("build_banner ist eine Koroutine",
          inspect.iscoroutinefunction(build))

    ergebnis = await lauf("welcome", {"welcome_image_enabled": False})
    check("Willkommensbild aus -> kein Bild", ergebnis is None,
          f"(bekam {ergebnis})")

    ergebnis = await lauf("leave", {"leave_image_enabled": False})
    check("Abschiedsbild aus -> kein Bild", ergebnis is None,
          f"(bekam {ergebnis})")

    # Und die Groessengrenze muss wirken, nicht nur dastehen.
    check("es gibt eine Groessengrenze",
          isinstance(getattr(greet_modul, "MAX_BACKGROUND_BYTES", None), int)
          and greet_modul.MAX_BACKGROUND_BYTES > 0,
          "-> sonst kann eine Adresse den Speicher fuellen")


# ── 6. Verdrahtung ───────────────────────────────────────────────────

def test_verdrahtung():
    print("\n6. Route, Schema und Oberflaeche")
    route = read("api/routes/guilds.py")
    check("GET greet-extras", '"/{guild_id}/greet-extras"' in route)
    check("PATCH greet-extras", route.count('"/{guild_id}/greet-extras"') >= 2)
    check("ungueltige Adresse ergibt 400, nicht 500",
          "status_code=400" in route and "ValueError" in route)

    guard = read("api/schema_guard.py")
    check("schema_guard kennt db/greet_extras.db", '"db/greet_extras.db"' in guard)

    def definiert_und_benutzt(quelle: str, name: str) -> bool:
        """
        Steht die Funktion da UND wird sie aufgerufen?

        Beides einzeln zu pruefen reicht nicht: verschwindet nur die
        Definition, bleiben die Aufrufe stehen und eine Textsuche
        findet den Namen weiter. Umgekehrt genauso.
        """
        hat_definition = bool(
            re.search(rf"function\s+{re.escape(name)}\s*\(", quelle)
        )
        aufrufe = len(re.findall(rf"(?<!function\s){re.escape(name)}\s*\(", quelle))
        return hat_definition and aufrufe >= 1

    panel = read("../dashboard/components/dashboard/greet-extras-panel.tsx")
    check("Schalter fuers Willkommensbild", "welcome_image_enabled" in panel)
    check("Schalter fuer den Abschied", "leave_enabled" in panel)
    check("Schalter fuers Abschiedsbild", "leave_image_enabled" in panel)
    check("Kanalauswahl", "ChannelPicker" in panel)
    check("dieselbe Adresspruefung wie im Bot",
          definiert_und_benutzt(panel, "isImageUrl"),
          "-> Definition und Aufruf muessen beide da sein")

    seite = read("../dashboard/app/dashboard/guild/[guildId]/welcome/page.tsx")
    # Geladen UND angezeigt. Nur der Import allein zeigt nichts an.
    check("Panel wird geladen", "greet-extras-panel" in seite)
    check("Panel wird auch angezeigt",
          bool(re.search(r"<GreetExtrasPanel[^>]*/>", seite)),
          "-> importiert, aber nirgends eingebunden")

    api_ts = read("../dashboard/lib/api.ts")
    check("API-Methoden vorhanden",
          "getGreetExtras" in api_ts and "saveGreetExtras" in api_ts)

    # Und das Ticket-Bild. Das Feld muss wirklich gespeichert werden --
    # `embed_image_url` steht auch in der Typdefinition, die es schon
    # vorher gab.
    ticket = read("../dashboard/components/dashboard/ticket-panels.tsx")
    check("Ticket-Bild wird gespeichert",
          bool(re.search(r"patchPanel\([^)]*\{\s*embed_image_url:", ticket)),
          "-> ein Feld ohne patchPanel aendert nichts")
    check("Ticket-Thumbnail wird gespeichert",
          bool(re.search(r"patchPanel\([^)]*\{\s*embed_thumbnail_url:", ticket)))
    check("Ticket-Bild wird geprueft",
          definiert_und_benutzt(ticket, "isImageUrl"))


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        alt = os.getcwd()
        os.chdir(tmp)
        try:
            await test_speichern()
            await test_bildadressen()
        finally:
            os.chdir(alt)

    test_platzhalter()
    test_karte()
    await test_cog()
    test_verdrahtung()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Begruessung und Abschied: alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
