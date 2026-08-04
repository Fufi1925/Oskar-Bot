#!/usr/bin/env python3
"""
Die Emoji-Auswahl im Reiter »Eigene Nachricht«.

Der Bot bringt rund 140 eigene Emojis mit. Um eines in eine Nachricht
zu setzen, musste man bisher seine Schreibweise kennen --
``<:name:1530375445785084005>``, achtzehnstellige ID inklusive. In der
Praxis hiess das: aus dem Quelltext abschreiben.

Worauf es hier ankommt:

  * Die Liste muss **aus der Quelle** kommen. Eine zweite, von Hand
    gepflegte Aufstellung laeuft beim ersten neuen Emoji auseinander,
    und niemand merkt es -- bis in einer Nachricht roher Text steht.
  * Jeder gelieferte Code muss **gueltig** sein. Kennt Discord die ID
    nicht, wird der Platzhalter als Text ausgegeben. Genau dieser
    Fehler stand schon einmal in einem Changelog.
  * Die Route darf nicht als ``guild_id`` gelesen werden.
  * Eingefuegt wird an der **Cursorposition**, nicht am Ende.

Run:  python3 tests/test_emoji_picker.py
"""

import asyncio
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*parts):
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """Kommentare raus, damit eine Erklärung nicht als Code zählt."""
    without_block = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", without_block, flags=re.M)


PICKER = "components/dashboard/emoji-picker.tsx"
PANEL = "components/dashboard/compose-panel.tsx"
PROXY = "app/api/bot/[...path]/route.ts"
API = "lib/api.ts"

EMOJI_PATTERN = re.compile(r"^<(a?):([A-Za-z0-9_]+):(\d+)>$")


def real_emojis() -> set[str]:
    """Was in utils/emoji.py wirklich steht."""

    source = open(os.path.join(BOT, "utils", "emoji.py"), encoding="utf-8").read()
    return set(re.findall(r'"(<a?:[A-Za-z0-9_]+:\d+>)"', source))


# --------------------------------------------------------------------- #


def test_the_list_comes_from_the_source():
    """Keine zweite Liste, die auseinanderlaufen kann."""

    print("\nDie Liste kommt aus utils/emoji.py")

    from api.routes import compose

    answer = asyncio.run(compose.emojis())
    items = answer["emojis"]

    check("es kommen Emojis zurück", len(items) > 100, str(len(items)))

    # Jeder gelieferte Code muss auch wirklich im Modul stehen.
    known = real_emojis()
    delivered = {entry["raw"] for entry in items}
    invented = sorted(delivered - known)
    check("kein erfundenes Emoji", not invented, str(invented[:3]))

    # Und umgekehrt: nichts darf fehlen. Eine Auswahl, in der das
    # gesuchte Emoji nicht auftaucht, schickt den Nutzer wieder in
    # den Quelltext.
    missing = sorted(known - delivered)
    check("nichts fehlt", not missing, f"{len(missing)} fehlen: {missing[:3]}")


def test_every_code_is_well_formed():
    """
    Ein kaputter Code wird in Discord als roher Text ausgegeben.

    Das ist kein hypothetischer Fall -- genau dieser Fehler steht im
    Changelog vom 30.07. als behobene Störung.
    """

    print("\nJeder Code ist gültig")

    from api.routes import compose

    items = asyncio.run(compose.emojis())["emojis"]

    broken = [e["raw"] for e in items if not EMOJI_PATTERN.match(e["raw"])]
    check("jeder Code hat die richtige Form", not broken, str(broken[:3]))

    # Die Einzelteile müssen zum Code passen -- sonst zeigt die
    # Vorschau ein anderes Bild als das, was eingefügt wird.
    mismatched = []
    for entry in items:
        match = EMOJI_PATTERN.match(entry["raw"])
        if match is None:
            continue
        if match.group(2) != entry["name"] or match.group(3) != entry["id"]:
            mismatched.append(entry["raw"])
        if bool(match.group(1)) != entry["animated"]:
            mismatched.append(entry["raw"])
    check("Name, ID und Animation passen zum Code",
          not mismatched, str(mismatched[:3]))

    # Die Bild-URL muss zur Art passen: ein animiertes Emoji als PNG
    # wäre ein Standbild.
    wrong_url = [
        e["raw"] for e in items
        if (".gif" in e["url"]) is not e["animated"]
    ]
    check("animierte Emojis werden als GIF vorgeschaut",
          not wrong_url, str(wrong_url[:3]))


def test_no_duplicates():
    """Dieselbe Kachel zweimal wäre nur verwirrend.

    Mehrere Namen zeigen auf dasselbe Emoji -- DELETE und DELETE_ALT1
    etwa sind Zeile für Zeile identisch.
    """

    print("\nKeine doppelten Kacheln")

    from api.routes import compose

    items = asyncio.run(compose.emojis())["emojis"]
    codes = [e["raw"] for e in items]
    check("jedes Emoji kommt einmal vor",
          len(codes) == len(set(codes)),
          f"{len(codes) - len(set(codes))} doppelt")


def test_the_grouping_loses_nothing():
    """Jedes Emoji landet in genau einer Gruppe."""

    print("\nDie Gruppierung verliert nichts")

    from api.routes import compose

    answer = asyncio.run(compose.emojis())
    items, groups = answer["emojis"], answer["groups"]

    check("es gibt mehrere Gruppen", len(groups) >= 3, str(groups))
    check("jedes Emoji hat eine Gruppe",
          all(e["group"] for e in items))
    check("jede Gruppe ist auch gemeldet",
          {e["group"] for e in items} <= set(groups),
          "eine Gruppe fehlt in der Aufzählung")

    # Die Auffanggruppe muss es geben, sonst verschluckt ein
    # unpassender Name das Emoji.
    check("es gibt eine Auffanggruppe",
          "Sonstige" in groups or all(
              e["group"] != "Sonstige" for e in items
          ),
          "Emojis ohne passende Gruppe hätten keinen Platz")


def test_the_route_is_not_read_as_a_guild():
    """/compose/emojis darf nicht als guild_id durchgehen."""

    print("\nDie Route kollidiert nicht mit guild_id")

    from fastapi.testclient import TestClient

    from api.server import create_app

    client = TestClient(create_app())
    response = client.get("/api/v1/compose/emojis")
    check("sie wird nicht als ID gelesen",
          response.status_code != 422,
          f"HTTP {response.status_code}")
    check("und antwortet mit Daten",
          response.status_code == 200,
          f"HTTP {response.status_code}")


def test_the_proxy_lets_signed_in_users_read_it():
    """Die Liste ist serverunabhängig -- aber nicht öffentlich."""

    print("\nDer Proxy kennt die Route")

    proxy = strip_comments(read(PROXY))
    block = proxy.split('scope === "compose"')[1].split('scope === "anonchat"')[0]

    check("es gibt eine Regel für die Emoji-Liste",
          'rest[0] === "emojis"' in block,
          "die Route läuft in die guild_id-Prüfung und wird abgewiesen")

    branch = block.split('rest[0] === "emojis"')[1].split("\n    }")[0]
    check("Nichtangemeldete kommen nicht durch",
          "Not signed in" in branch,
          "die Liste wäre ohne Anmeldung lesbar")

    # Die Regel muss vor der guild_id-Prüfung stehen: "emojis" ist
    # keine achtzehnstellige Zahl.
    if "guild_id missing" in block:
        check("die Regel steht vor der ID-Prüfung",
              block.index('rest[0] === "emojis"') < block.index("guild_id missing"),
              "die Route antwortet mit 400 statt zu funktionieren")


def test_the_picker_inserts_at_the_cursor():
    """Am Ende anzuhängen wäre die falsche Stelle."""

    print("\nEingefügt wird an der Cursorposition")

    picker = strip_comments(read(PICKER))
    panel = strip_comments(read(PANEL))

    check("es gibt die Auswahl", bool(picker))
    check("sie holt die Liste vom Bot", "api.getBotEmojis" in picker)
    check("es gibt eine Einfüge-Hilfe", "insertAtCursor" in picker)

    # Sie muss die Auswahl wirklich lesen, nicht bloss anhaengen.
    check("die Cursorposition wird gelesen",
          "selectionStart" in picker and "selectionEnd" in picker,
          "ohne sie landet das Emoji immer am Ende")

    # Und das Panel muss sie benutzen -- beide Textfelder.
    check("das freie Textfeld bietet die Auswahl",
          "contentRef" in panel and "EmojiPicker" in panel)
    check("die V2-Blöcke ebenfalls",
          "blockRefs" in panel,
          "in den Blöcken ließe sich kein Emoji einsetzen")

    # Ein Ref je Block, und zwar am *Block* festgemacht.
    #
    # Nur nach "blockRefs.current[block.id]" zu suchen reicht nicht:
    # der Lesezugriff beim Einfügen benutzt dieselbe Zeichenfolge. Wird
    # beim Speichern ein fester Index eingetragen
    # (`blockRefs.current[0] = node`), bleibt die Prüfung grün und alle
    # Blöcke teilen sich ein Feld. Ein Mutationstest hat genau das
    # durchgelassen -- also die Zuweisung gezielt ansehen.
    stores = re.findall(r"blockRefs\.current\[([^\]]+)\]\s*=", panel)
    check("jeder Block speichert unter seiner eigenen Kennung",
          bool(stores) and all(s.strip() == "block.id" for s in stores),
          f"gespeichert unter: {stores} — ein fester Index schreibt "
          "ins falsche Feld")
    check("und wird unter derselben Kennung gelesen",
          "blockRefs.current[block.id] ??" in panel
          or "blockRefs.current[block.id]" in panel)

    # Die Grenzen von Discord. Auch hier zählt die Bedingung, nicht das
    # Vorkommen: `if (false)` ließe die Wörter stehen.
    #
    # Es gibt zwei Stellen, und sie sehen verschieden aus: das freie
    # Textfeld prüft fest gegen 2000, die Embed-Hilfe gegen ein
    # übergebenes `limit`, weil Discord jedes Embed-Feld einzeln zählt
    # (Titel 256, Beschreibung 4096, Fußzeile 2048). Ein einzelnes
    # Suchmuster traf nur die erste und meldete die zweite als Fehler.
    guards = re.findall(r"if \(([^)]*text\.length[^)]*)\)", panel)
    check("beide Grenzen werden geprüft", len(guards) >= 2,
          f"gefunden: {guards}")
    check("das freie Textfeld prüft gegen 2000",
          any("2000" in g for g in guards),
          f"Bedingungen: {guards}")
    check("die Embed-Felder prüfen gegen ihre eigene Grenze",
          any("limit" in g for g in guards),
          f"Bedingungen: {guards} — ein fester Wert wäre für Titel (256) "
          "und Beschreibung (4096) gleichzeitig falsch")
    check("und es kommt eine Meldung statt stillen Abschneidens",
          "passt nicht mehr" in panel)

    # Die Auswahl muss überall stehen, wo Text entsteht -- nicht nur im
    # freien Feld. Ein Embed ohne Auswahl heißt: dort weiterhin die
    # Schreibweise von Hand kennen.
    # Auf den *Render*-Zweig eingrenzen, nicht auf den ersten Treffer:
    # "kind === \"embed\"" steht auch in der Typ-Auswahl oben, und der
    # Ausschnitt dazwischen war dreißig Zeichen lang.
    embed_branch = panel.split('{kind === "embed" && (')[1].split(
        '{kind === "v2" && (')[0]
    check("der Embed-Zweig bietet die Auswahl",
          "EmojiPicker" in embed_branch,
          "im Embed müsste man den Code weiterhin abschreiben")
    for field in ("title", "description", "author_name", "footer_text"):
        check(f"…auch für {field}",
              f'insertIntoEmbed("{field}"' in embed_branch,
              f"{field} hat keine Auswahl")

    # Die Embed-Hilfe muss ihr Feld auch wirklich nachschlagen.
    #
    # `const node = null` ließe alles andere grün: die Auswahl steht
    # da, die Grenze wird geprüft, nur landet jedes Emoji am Ende statt
    # am Cursor. Ein Mutationstest hat genau das durchgelassen.
    helper = panel.split("const insertIntoEmbed")[1].split("};")[0]
    check("die Embed-Hilfe schlägt ihr Feld nach",
          "embedRefs.current[field]" in helper,
          "ohne das Feld landet jedes Emoji am Ende")
    check("und reicht es an die Einfüge-Hilfe weiter",
          "insertAtCursor(node" in helper,
          f"Rumpf: {helper.strip()[:120]}")

    buttons_branch = panel.split('block.type === "buttons"')[1][:3000]
    check("das Button-Emoji lässt sich auswählen",
          "EmojiPicker" in buttons_branch,
          "gerade dort ist ein Emoji am naheliegendsten")


def test_the_api_call_exists():
    print("\nDer Aufruf ist verdrahtet")

    api_src = strip_comments(read(API))
    check("getBotEmojis gibt es", "getBotEmojis:" in api_src)
    check("und zeigt auf die richtige Route",
          "/compose/emojis" in api_src)


def test_the_new_changelogs_are_there():
    """Die Einträge für alles seit dem letzten Changelog."""

    print("\nDie neuen Changelog-Einträge")

    src = read("lib/announcements.ts")

    for entry_id, topic in (
        ("2026-08-speedrun-vorlagen", "die drei neuen Vorlagen"),
        ("2026-08-speedrun-beta-code", "der Beta-Code"),
        ("2026-08-speedrun-tab-zu", "der Tab-Fehler"),
        ("2026-08-tickets-rechte", "die Ticket-Rechte"),
    ):
        check(f"es gibt den Eintrag für {topic}", f'"{entry_id}"' in src)

    # Sie gehören auf den Support-Server, sonst sieht sie jeder.
    entries = re.split(r"\n  \{\n    id: ", src)[1:]
    new_entries = [e for e in entries if e.startswith('"2026-08-')]
    check("die neuen Einträge wurden gefunden",
          len(new_entries) >= 4, str(len(new_entries)))
    for entry in new_entries:
        name = entry.split('"')[1]
        check(f"{name}: nur auf dem Support-Server",
              "BOT_GUILD_ID" in entry.split("blocks:")[0],
              "der Eintrag wäre auf jedem Server sichtbar")


def test_the_changelogs_use_real_emojis():
    """
    Ein erfundener Emoji-Code wird als roher Text ausgegeben.

    In einem Changelog über kaputte Emojis wäre das besonders
    peinlich.
    """

    print("\nDie Changelogs benutzen echte Emojis")

    src = read("lib/announcements.ts")
    known = real_emojis()

    # Codes in Backticks sind Beispiele im Fließtext -- der alte
    # Emoji-Changelog zeigt absichtlich einen ungültigen. Die zählen
    # nicht mit; sie werden nie als Emoji gerendert.
    without_examples = re.sub(r"`[^`]*`", "", src)
    used = set(re.findall(r"<a?:[A-Za-z0-9_]+:\d+>", without_examples))

    check("es werden Emojis benutzt", len(used) >= 5, str(len(used)))

    invented = sorted(used - known)
    check("jedes davon gibt es wirklich",
          not invented,
          f"kennt der Bot nicht: {invented}")


def main():
    test_the_list_comes_from_the_source()
    test_every_code_is_well_formed()
    test_no_duplicates()
    test_the_grouping_loses_nothing()
    test_the_route_is_not_read_as_a_guild()
    test_the_proxy_lets_signed_in_users_read_it()
    test_the_picker_inserts_at_the_cursor()
    test_the_api_call_exists()
    test_the_new_changelogs_are_there()
    test_the_changelogs_use_real_emojis()

    print()
    if failures:
        print(f"FAILED {len(failures)}")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("Alle Prüfungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
