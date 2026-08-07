#!/usr/bin/env python3
"""
Die vorgefertigten Texte benutzen die eigenen Emojis des Bots.

Gemeldet: bei Verifizierung, Begruessung und Speedrun sollen die
vorgefertigten Texte Custom-Emojis nutzen, keine Unicode-Zeichen.

Warum das ueberhaupt besser ist
-------------------------------
Ein Unicode-Zeichen wie ``🎉`` sieht auf jedem Geraet anders aus:
Windows, iOS und Android bringen eigene Saetze mit. Was ein Geraet
nicht kennt, zeigt es als leeres Rechteck. Ein App-Emoji ist ueberall
dasselbe Bild.

Wo es *nicht* geht -- und das ist der Kern
------------------------------------------
Discord rendert Custom-Emojis nur dort, wo es Nachrichtentext gibt:
in Nachrichten, Embeds und als Reaktion. In **Kanalnamen,
Kategorienamen, Rollennamen und Webhook-Namen** rendert es sie nicht;
dort erschiene ``<a:TADAA:1530375414575529984>`` als roher Text.

Deshalb bleiben die Vorlagen des Template-Bots unangetastet: ihre
Emojis sitzen zu 519 von 673 Stellen in einem Feld, das gleichzeitig
den Kanalnamen bildet. Ausserdem gehoeren App-Emojis genau einer
Anwendung -- der Template-Bot ist eine eigene App und synchronisiert
sich seine eigenen Kopien.

Und noch etwas
--------------
Die Codes duerfen nur an **einer** Stelle stehen. Eine zweite Liste im
Dashboard liefe beim ersten neuen Emoji auseinander. Genau dieser
Fehler stand hier schon einmal im Changelog: vier Emojis zeigten auf
geloeschte IDs und erschienen als roher Text.

Run:  python3 tests/test_template_emojis.py
"""

import ast
import asyncio
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")
TEMPLATE_BOT = os.path.join(os.path.dirname(os.path.dirname(BOT)), "University-Template")
sys.path.insert(0, BOT)

failures: list[str] = []

# Die Unicode-Bereiche, die als Bild dargestellt werden.
UNICODE_EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF\U00002B00-\U00002BFF\U0000FE0F]"
)

# Die Schreibweise eines Custom-Emojis.
CUSTOM = re.compile(r"<(a?):([A-Za-z0-9_]+):(\d+)>")


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def strip_py_text(src: str) -> str:
    """Kommentare und Docstrings raus.

    Sonst treffen die Suchen die eigenen Erklaerungen: in den
    Kommentaren steht woertlich, was frueher falsch war (``🎉``).
    Genau dieser Fehler ist hier schon mehrfach passiert.
    """
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src

    spans = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", [])
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            doc = body[0]
            spans.append((doc.lineno, doc.end_lineno))

    lines = src.split("\n")
    for start, end in spans:
        for i in range(start - 1, min(end, len(lines))):
            lines[i] = ""
    return "\n".join(lines)


def strip_ts(src: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


def known_emojis() -> set[str]:
    """Was in utils/emoji.py wirklich steht."""
    source = open(os.path.join(BOT, "utils", "emoji.py"), encoding="utf-8").read()
    return set(re.findall(r'"(<a?:[A-Za-z0-9_]+:\d+>)"', source))


# ------------------------------------------------------------------ #
# 1. Die Standardtexte des Bots
# ------------------------------------------------------------------ #
def test_the_verify_defaults_use_custom_emojis():
    """Die Verify-Texte landen in einer Nachricht -- dort geht es."""
    print("\nVerifizierung: die vorgefertigten Texte")

    from utils import verify_store

    for key in ("panel_text", "success_text"):
        text = verify_store.DEFAULTS[key]
        leftover = UNICODE_EMOJI.findall(text)
        check(f"{key} ohne Unicode-Emoji", not leftover, f"-> {leftover}")
        check(f"{key} nutzt ein eigenes Emoji", bool(CUSTOM.search(text)))


def test_the_level_default_uses_a_custom_emoji():
    print("\nLevel-Aufstieg: der vorgefertigte Text")

    from utils import leveling_store

    text = leveling_store.DEFAULTS["level_message"]
    leftover = UNICODE_EMOJI.findall(text)
    check("ohne Unicode-Emoji", not leftover, f"-> {leftover}")
    check("nutzt ein eigenes Emoji", bool(CUSTOM.search(text)))


def test_every_code_in_a_default_really_exists():
    """Ein erfundener Code erscheint in Discord als roher Text.

    Das ist kein hypothetischer Fall -- genau dieser Fehler steht im
    Changelog vom 30.07. als behobene Stoerung.
    """
    print("\nJeder Code steht wirklich in utils/emoji.py")

    from utils import leveling_store, verify_store

    known = known_emojis()
    texts = {
        "verify/panel_text": verify_store.DEFAULTS["panel_text"],
        "verify/success_text": verify_store.DEFAULTS["success_text"],
        "leveling/level_message": leveling_store.DEFAULTS["level_message"],
    }
    for where, text in texts.items():
        for match in CUSTOM.finditer(text):
            check(f"{where}: {match.group(0)} ist echt", match.group(0) in known)


def test_the_placeholders_survived():
    """Ein f-String frisst schnell eine Klammer.

    ``{server}`` muss ``{server}`` bleiben. Wird daraus versehentlich
    der *Wert* einer Variablen eingesetzt, steht im Text plötzlich
    nichts mehr -- und der Bot kann den Namen nicht mehr einsetzen.
    """
    print("\nDie Platzhalter sind unversehrt")

    from utils import leveling_store, verify_store

    check(
        "verify/panel_text hat {server}",
        "{server}" in verify_store.DEFAULTS["panel_text"],
    )
    check(
        "verify/success_text hat {user} und {server}",
        "{user}" in verify_store.DEFAULTS["success_text"]
        and "{server}" in verify_store.DEFAULTS["success_text"],
    )
    check(
        "leveling hat {user} und {level}",
        "{user}" in leveling_store.DEFAULTS["level_message"]
        and "{level}" in leveling_store.DEFAULTS["level_message"],
    )


# ------------------------------------------------------------------ #
# 2. Die Begruessungs-Vorlagen kommen vom Bot
# ------------------------------------------------------------------ #
def test_the_welcome_templates_come_from_the_bot():
    """Eine zweite Liste im Dashboard liefe auseinander."""
    print("\nDie Begruessungs-Vorlagen kommen vom Bot")

    from api.routes import compose

    answer = asyncio.run(compose.welcome_templates())
    items = answer["templates"]

    check("es kommen Vorlagen zurueck", len(items) >= 3, str(len(items)))

    known = known_emojis()
    with_emoji = 0
    for entry in items:
        blob = entry.get("message", "") + " " + " ".join(
            str(v) for v in (entry.get("embed") or {}).values()
        )
        leftover = UNICODE_EMOJI.findall(blob)
        check(f"{entry['name']}: ohne Unicode-Emoji", not leftover, f"-> {leftover}")
        for match in CUSTOM.finditer(blob):
            check(f"{entry['name']}: {match.group(0)} ist echt",
                  match.group(0) in known)
            with_emoji += 1

    check("mindestens eine Vorlage nutzt ein Emoji", with_emoji > 0)


def test_the_templates_read_the_shared_source():
    """Nicht die Codes abschreiben, sondern nachschlagen.

    Ein hier eingefrorenes ``<a:TADAA:1530...>`` waere die zweite
    Quelle, die vermieden werden soll. Geprueft wird deshalb, dass die
    Route das Modul *liest*, statt Codes im Klartext zu enthalten.
    """
    print("\nDie Route schlaegt nach, statt abzuschreiben")

    src = strip_py_text(
        open(os.path.join(BOT, "api", "routes", "compose.py"), encoding="utf-8").read()
    )
    block = src.split("async def welcome_templates")[1]

    check("sie liest utils/emoji.py", "from utils import emoji as bot_emoji" in src)
    check("und schlaegt die Namen nach", "getattr(bot_emoji" in block)

    # Kein Code im Klartext -- der waere die zweite Quelle.
    hardcoded = CUSTOM.findall(block)
    check("keine Emoji-ID abgeschrieben", not hardcoded, f"-> {hardcoded}")


def test_a_missing_emoji_does_not_break_the_template():
    """Faellt ein Emoji weg, bleibt der Text brauchbar.

    Ein ``<:weg:123>`` mitten im Satz waere schlimmer als gar kein
    Emoji: Discord zeigt den rohen Code an.
    """
    print("\nEin fehlendes Emoji laesst den Text heil")

    src = strip_py_text(
        open(os.path.join(BOT, "api", "routes", "compose.py"), encoding="utf-8").read()
    )
    block = src.split("async def welcome_templates")[1]

    # `getattr(..., "")` faellt auf einen leeren String zurueck.
    check(
        "es gibt einen Rueckfall auf leer",
        re.search(r'getattr\(bot_emoji, name, ""\)', block) is not None,
        "sonst stuende dort ein kaputter Code oder es kraeche",
    )


def test_the_dashboard_asks_the_bot():
    print("\nDas Dashboard fragt den Bot")

    api_src = strip_ts(open(os.path.join(DASH, "lib", "api.ts"), encoding="utf-8").read())
    check("es gibt den Aufruf", "getWelcomeTemplates" in api_src)
    check("und er zeigt auf die richtige Route",
          "/compose/templates/welcome" in api_src)

    form = strip_ts(
        open(
            os.path.join(DASH, "components", "dashboard", "welcome-form.tsx"),
            encoding="utf-8",
        ).read()
    )
    # Prettier bricht die Kette um:
    #     api
    #       .getWelcomeTemplates()
    # Ein Muster auf "api.getWelcomeTemplates()" findet das nicht.
    check(
        "das Formular ruft ihn auf",
        re.search(r"api\s*\.\s*getWelcomeTemplates\s*\(", form) is not None,
    )
    # Die Liste muss auch benutzt werden -- nicht nur geladen.
    check("und zeigt die geladenen Vorlagen an",
          "templates.map(" in form,
          "geladen, aber nie angezeigt")


def test_the_dashboard_has_no_second_emoji_list():
    """Der Rueckfall darf keine Codes enthalten.

    Sonst gaebe es zwei Quellen, und beim ersten neuen Emoji liefen sie
    auseinander -- ohne dass es jemand merkt, bis in einer Begruessung
    roher Text steht.
    """
    print("\nKeine zweite Emoji-Liste im Dashboard")

    form = strip_ts(
        open(
            os.path.join(DASH, "components", "dashboard", "welcome-form.tsx"),
            encoding="utf-8",
        ).read()
    )
    hardcoded = CUSTOM.findall(form)
    check("keine Emoji-ID im Dashboard", not hardcoded, f"-> {hardcoded}")

    # Auch keine Unicode-Emojis mehr in den Vorlagen.
    if "FALLBACK_TEMPLATES" in form:
        block = form.split("FALLBACK_TEMPLATES")[1].split("function Field")[0]
        leftover = UNICODE_EMOJI.findall(block)
        check("der Rueckfall traegt keine Unicode-Emojis", not leftover,
              f"-> {leftover}")


def test_the_proxy_lets_the_templates_through():
    """Ohne Regel im Proxy kaeme ein 400 statt der Vorlagen.

    "templates" ist keine achtzehnstellige Zahl und liefe sonst in die
    guild_id-Pruefung.
    """
    print("\nDer Proxy kennt die Route")

    proxy = strip_ts(
        open(
            os.path.join(DASH, "app", "api", "bot", "[...path]", "route.ts"),
            encoding="utf-8",
        ).read()
    )
    block = proxy.split('scope === "compose"')[1].split('scope === "anonchat"')[0]

    check("es gibt eine Regel", 'rest[0] === "templates"' in block)
    branch = block.split('rest[0] === "templates"')[1].split("\n    }")[0]
    check("Nichtangemeldete kommen nicht durch", "Not signed in" in branch)

    if "guild_id missing" in block:
        check(
            "die Regel steht vor der ID-Pruefung",
            block.index('rest[0] === "templates"') < block.index("guild_id missing"),
            "die Route antwortete sonst mit 400",
        )


# ------------------------------------------------------------------ #
# 3. Wo bewusst NICHT umgestellt wurde
# ------------------------------------------------------------------ #
def test_the_template_bot_keeps_unicode():
    """Die Speedrun-Vorlagen bleiben, wie sie sind -- mit Grund.

    Zwei unabhaengige Gruende, jeder fuer sich ausreichend:

      1. Ihre Emojis sitzen ueberwiegend im Feld ``emoji``, und das
         bildet den **Kanalnamen**. Discord rendert Custom-Emojis dort
         nicht -- es stuende der rohe Code im Namen.
      2. Der Template-Bot ist eine **eigene Anwendung**. App-Emojis
         gehoeren genau einer App; die IDs des Hauptbots erschienen
         dort als Text. Er synchronisiert sich deshalb eigene Kopien.
    """
    print("\nDer Template-Bot bleibt unangetastet")

    if not os.path.isdir(TEMPLATE_BOT):
        print("  --   Template-Bot nicht ausgecheckt, uebersprungen")
        return

    import json

    path = os.path.join(TEMPLATE_BOT, "templates", "gaming.json")
    if not os.path.isfile(path):
        print("  --   gaming.json fehlt, uebersprungen")
        return

    data = json.load(open(path, encoding="utf-8"))

    # Die Kanal-Emojis muessen Unicode bleiben.
    codes = 0
    unicode_count = 0
    for cat in data.get("categories", []):
        for channel in cat.get("channels", []):
            value = channel.get("emoji") or ""
            if CUSTOM.search(value):
                codes += 1
            if UNICODE_EMOJI.search(value):
                unicode_count += 1

    check("Kanal-Emojis sind noch Unicode", unicode_count > 0, str(unicode_count))
    check(
        "und keines wurde auf einen Custom-Code umgestellt",
        codes == 0,
        f"{codes} Kanaele haetten rohen Text im Namen",
    )


def test_the_reason_is_written_down():
    """Der naechste soll nicht dieselbe Frage neu stellen muessen."""
    print("\nDer Grund steht im Code")

    src = open(
        os.path.join(BOT, "api", "routes", "compose.py"), encoding="utf-8"
    ).read()
    block = src.split("# ── Vorgefertigte Texte")[1]

    check("die zweite Quelle ist als Gefahr benannt",
          "auseinanderlaeuft" in block or "auseinanderlaufen" in block)
    check("und wo Emojis nicht gerendert werden",
          "Kanal-" in block and "roher Code" in block.replace("rohe Code", "roher Code"))


def main() -> int:
    test_the_verify_defaults_use_custom_emojis()
    test_the_level_default_uses_a_custom_emoji()
    test_every_code_in_a_default_really_exists()
    test_the_placeholders_survived()
    test_the_welcome_templates_come_from_the_bot()
    test_the_templates_read_the_shared_source()
    test_a_missing_emoji_does_not_break_the_template()
    test_the_dashboard_asks_the_bot()
    test_the_dashboard_has_no_second_emoji_list()
    test_the_proxy_lets_the_templates_through()
    test_the_template_bot_keeps_unicode()
    test_the_reason_is_written_down()

    print()
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for entry in failures:
            print(f"  - {entry}")
        return 1
    print("Alles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
