#!/usr/bin/env python3
"""
Die Emoji-Auswahl an jedem Feld, dessen Text in Discord landet.

Gemeldet: die Auswahl fuer die eigenen Emojis des Bots gab es nur im
Reiter "Eigene Nachricht". Ueberall sonst -- Willkommen, Verifizierung,
Autoresponder, Gewinnspiele, Tickets -- musste man die Schreibweise
kennen: ``<:name:1530375445785084005>``, achtzehnstellige ID inklusive.

Drei Dinge sind hier zu pruefen, und sie sind verschieden:

  1. **Steht die Auswahl an jedem Textfeld?** Das ist die eigentliche
     Bitte.

  2. **Steht sie NICHT dort, wo sie schadet?** Ein Emoji in einer
     Sicherheitsabfrage ("Servernamen tippen zum Bestaetigen") oder in
     einem Kanalnamen ist kein Fortschritt. Discord rendert
     Custom-Emojis in Kanal-, Rollen- und Webhook-Namen ueberhaupt
     nicht -- dort erschiene der rohe Code als Text.

  3. **Stimmt das Verhalten je nach Feld?** In einen Fliesstext wird
     an der Cursorposition *eingefuegt*. In ein Feld fuer genau ein
     Emoji -- Knopf, Reaktionsrolle, Ticket-Kategorie -- wird
     *ersetzt*: Discord erlaubt dort genau eines.

Run:  python3 tests/test_emoji_everywhere.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")
PANELS = os.path.join(DASH, "components", "dashboard")

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*parts) -> str:
    path = os.path.join(DASH, *parts)
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """Kommentare raus, damit eine Erklaerung nicht als Code zaehlt.

    In den Kommentaren steht woertlich, was wo passiert ("Ersetzen
    statt anhaengen", "EmojiPicker"). Ohne Strippen meldet eine Suche
    Treffer, die es im Code nicht gibt -- genau dieser Fehler ist beim
    Emoji-Picker mehrfach hintereinander passiert.
    """
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


def has_picker(src: str) -> bool:
    """Wird die Auswahl wirklich gerendert?

    Der Import allein zaehlt nicht -- er bleibt stehen, auch wenn
    niemand das Element mehr benutzt. Gesucht wird das Element im
    Baum, direkt oder ueber einen der Bausteine.
    """
    return bool(
        re.search(r"<EmojiPicker[\s/>]", src)
        or re.search(r"<EmojiText[\s/>]", src)
        or re.search(r"<EmojiDraftField[\s/>]", src)
        or re.search(r"<EmojiOnly[\s/>]", src)
    )


# ------------------------------------------------------------------ #
# 1. Wo die Auswahl stehen MUSS
# ------------------------------------------------------------------ #

# Datei -> was der Nutzer dort schreibt. Alles davon postet der Bot.
MUST_HAVE = {
    "compose-panel.tsx": "Eigene Nachricht",
    "welcome-form.tsx": "Begruessung",
    "verify-panel.tsx": "Verifizierung",
    "autoresponder-panel.tsx": "Autoresponder",
    "joindm-panel.tsx": "Willkommens-DM",
    "giveaways-panel.tsx": "Gewinnspiel anlegen",
    "giveaway-detail.tsx": "Gewinnspiel bearbeiten",
    "ticket-panels.tsx": "Ticket-Panels",
    "leveling-panel.tsx": "Level-Aufstieg",
    "support-queue-panel.tsx": "Support-Warteraum",
    "extras-panels.tsx": "Boost und Sticky",
    "broadcast-panel.tsx": "Rundnachricht",
    "reactionroles-panel.tsx": "Reaktionsrollen",
    "ping-reactions-panel.tsx": "Ping-Reaktionen",
    "tester-panel.tsx": "Tester-Meldungen",
    "warnings-panel.tsx": "Verwarnung (geht als DM raus)",
}


def _field_block(src: str, needle: str, span: int = 700) -> str:
    """Der Ausschnitt rund um ein bestimmtes Feld.

    Warum nicht die ganze Datei durchsuchen: eine Datei hat mehrere
    Felder. Faellt bei einem die Auswahl weg, findet eine Suche ueber
    die ganze Datei sie immer noch bei einem anderen und bleibt gruen.
    Genau das hat der Mutationstest aufgedeckt -- vier Mutationen sind
    so entwischt.
    """
    i = src.find(needle)
    if i == -1:
        return ""
    return src[max(0, i - 200) : i + span]


def test_every_message_field_offers_the_picker():
    print("\nUeberall, wo Text fuer Discord entsteht")
    for name, what in sorted(MUST_HAVE.items()):
        src = strip_comments(read("components", "dashboard", name))
        check(f"{what} ({name})", has_picker(src))


# Feld -> (Datei, Textstelle, was es ist). Hier wird jedes Feld
# EINZELN geprueft, nicht die Datei als Ganzes.
SINGLE_FIELDS = [
    ("verify-panel.tsx", "value={value ?? \"\"}", "Verifizierung: gemeinsames Textfeld"),
    ("joindm-panel.tsx", 'value={value("message") ?? ""}', "Willkommens-DM: Text"),
    ("joindm-panel.tsx", 'value={value("title") ?? ""}', "Willkommens-DM: Ueberschrift"),
    ("joindm-panel.tsx", 'value={value("footer") ?? ""}', "Willkommens-DM: Fusszeile"),
    ("ticket-panels.tsx", "defaultValue={panel.embed_description}", "Tickets: Beschreibung"),
    ("ticket-panels.tsx", "defaultValue={panel.embed_title}", "Tickets: Ueberschrift"),
    ("giveaways-panel.tsx", "value={description}", "Gewinnspiel: Beschreibung"),
    ("giveaways-panel.tsx", "value={title}", "Gewinnspiel: Ueberschrift"),
    ("giveaways-panel.tsx", "value={prize}", "Gewinnspiel: Preis"),
    ("giveaway-detail.tsx", 'value={value("description")}', "Gewinnspiel bearb.: Beschreibung"),
    ("giveaway-detail.tsx", 'value={value("title")}', "Gewinnspiel bearb.: Ueberschrift"),
    ("autoresponder-panel.tsx", "value={response}", "Autoresponder: Antwort"),
    ("leveling-panel.tsx", 'value={value("level_message") ?? ""}', "Level-Aufstieg"),
    ("support-queue-panel.tsx", "value={greeting}", "Warteraum: Ansage"),
    ("broadcast-panel.tsx", "value={message}", "Rundnachricht: Text"),
    ("extras-panels.tsx", 'value={boost.message ?? ""}', "Boost-Nachricht"),
    ("tester-panel.tsx", "value={body}", "Tester: Meldungstext"),
    ("warnings-panel.tsx", "value={reason}", "Verwarnungsgrund (DM)"),
]


def test_each_single_field_has_its_own_picker():
    """Jedes Feld einzeln, nicht die Datei als Ganzes.

    Eine Datei kann fuenf Textfelder haben. Verliert eines seine
    Auswahl, bliebe eine Suche ueber die ganze Datei gruen -- die
    anderen vier enthalten das Wort ja noch.
    """
    print("\nJedes einzelne Feld hat seine eigene Auswahl")
    for name, needle, what in SINGLE_FIELDS:
        src = strip_comments(read("components", "dashboard", name))
        block = _field_block(src, needle)
        check(f"{what}", bool(block) and has_picker(block),
              "kein Feld gefunden" if not block else "keine Auswahl in der Naehe")


def test_the_welcome_embed_covers_every_part():
    """Jede Ueberschrift und jede Fusszeile einzeln -- so gewuenscht.

    Eine Auswahl irgendwo in der Datei reicht nicht: die Begruessung
    hat sechs getrennte Felder, und jedes braucht seine eigene. Genau
    das war die Bitte ("auch jede Ueberschrift, Fusszeile, ueber alle
    einzeln").
    """
    print("\nDie Begruessung: jedes Feld einzeln")
    src = strip_comments(read("components", "dashboard", "welcome-form.tsx"))

    for field, label in [
        ("welcome_message", "freie Nachricht"),
        ("message", "Text ueber der Karte"),
        ("title", "Ueberschrift"),
        ("description", "Beschreibung"),
        ("author_name", "Kopfzeile"),
        ("footer_text", "Fusszeile"),
    ]:
        # Das Feld muss ein EmojiText sein -- ein nacktes <input>
        # haette keine Auswahl.
        pattern = re.compile(
            r"<EmojiText\b[^>]*?" + re.escape(field) + r"\b", re.S
        )
        check(f"{label} hat eine Auswahl", bool(pattern.search(src)))


def test_each_field_uses_its_own_discord_limit():
    """Discord zaehlt jedes Feld einzeln.

    Titel 256, Beschreibung 4096, Fusszeile 2048, Nachricht 2000,
    Knopfbeschriftung 80. Ein fester Wert waere fuer Titel und
    Beschreibung gleichzeitig falsch.

    Geprueft wird die Zuordnung Feld -> Grenze, nicht nur "es gibt
    verschiedene Zahlen". Vertauscht man zwei, blieb der alte Test
    gruen: die Menge der Zahlen war ja unveraendert.
    """
    print("\nJedes Feld kennt seine eigene Grenze")
    src = strip_comments(read("components", "dashboard", "welcome-form.tsx"))

    for field, expected, what in [
        ("config.welcome_message", "2000", "freie Nachricht"),
        ("embed.message", "2000", "Text ueber der Karte"),
        ("embed.title", "256", "Ueberschrift"),
        ("embed.description", "4096", "Beschreibung"),
        ("embed.author_name", "256", "Kopfzeile"),
        ("embed.footer_text", "2048", "Fusszeile"),
    ]:
        block = _field_block(src, f"value={{{field}", span=500)
        found = re.search(r"limit=\{(\d+)\}", block)
        got = found.group(1) if found else "(keine)"
        check(f"{what} = {expected}", got == expected, f"-> {got}")


def test_the_limit_is_checked_before_inserting():
    """Erst pruefen, dann einfuegen -- nicht umgekehrt.

    Schneidet Discord ab, trifft es mitten in den Emoji-Code. Der
    Nutzer saehe dann eine abgehackte Zahl statt eines Bildes.
    """
    print("\nDie Grenze wird vor dem Einfuegen geprueft")
    src = strip_comments(read("components", "dashboard", "emoji-field.tsx"))

    check("es wird gegen die Grenze geprueft", "text.length > limit" in src)
    # Auf die Wirkung pruefen: ein `return` muss folgen, sonst wird
    # trotzdem geschrieben.
    guard = re.search(
        r"if \(text\.length > limit\)\s*\{[^}]*return;[^}]*\}", src, re.S
    )
    check("und bei Ueberschreitung abgebrochen", bool(guard),
          "ohne `return` wird trotzdem geschrieben")


def test_the_cursor_moves_behind_the_emoji():
    """Sonst tippt man mitten in den gerade eingefuegten Code hinein.

    Es gibt ZWEI Stellen mit dieser Logik: `EmojiText` fuer gesteuerte
    Felder und `EmojiDraftField` fuer die Ticket-Panels. Beide muessen
    einzeln geprueft werden -- sonst deckt die eine die andere zu und
    ein Fehler in nur einer bleibt unbemerkt.
    """
    print("\nDer Cursor springt hinter das Emoji")
    src = strip_comments(read("components", "dashboard", "emoji-field.tsx"))

    parts = [
        ("EmojiText", src.split("export function EmojiText")[1].split("export function")[0]),
        ("EmojiDraftField", src.split("export function EmojiDraftField")[1].split("export function")[0]),
    ]

    for what, block in parts:
        # Der AUFRUF, nicht der Import. `const text = value + raw`
        # liesse den Import stehen und haenge trotzdem stur an.
        call = re.search(r"insertAtCursor\(\s*field", block)
        check(f"{what}: fuegt an der Cursorposition ein", bool(call),
              "ohne insertAtCursor landet jedes Emoji am Ende")

        # Die Positionierung muss INNERHALB von requestAnimationFrame
        # stehen. Davor gesetzt, ueberschreibt Reacts Rendern sie.
        frame = re.search(
            r"requestAnimationFrame\(\(\) => \{[^}]*?setSelectionRange\(caret, caret\)",
            block,
            re.S,
        )
        check(f"{what}: Position erst im naechsten Bild", bool(frame),
              "davor gesetzt, ueberschreibt Reacts Rendern sie wieder")


# ------------------------------------------------------------------ #
# 2. Felder mit genau EINEM Emoji: ersetzen statt einfuegen
# ------------------------------------------------------------------ #
def test_single_emoji_fields_replace_instead_of_insert():
    """Auf einem Knopf ist genau ein Emoji erlaubt.

    Zwei hintereinander lehnt Discord ab -- und der Fehler kaeme erst
    beim Absenden, lange nach dem Klick, der ihn verursacht hat.
    Deshalb wird dort *ersetzt*.

    Geprueft wird die Wirkung, nicht das Wort: die Zuweisung muss den
    rohen Wert setzen und darf ihn nicht an den alten anhaengen.
    """
    print("\nFelder fuer genau ein Emoji ersetzen")

    cases = [
        ("giveaways-panel.tsx", "setButtonEmoji", "Knopf am Gewinnspiel"),
        ("giveaway-detail.tsx", 'set("button_emoji"', "Knopf am Gewinnspiel"),
        ("reactionroles-panel.tsx", "setEmoji", "Reaktionsrolle"),
        ("extras-panels.tsx", 'p.set("success_emoji"', "Bestaetigungs-Reaktion"),
    ]

    for name, setter, what in cases:
        src = strip_comments(read("components", "dashboard", name))

        # Der onPick muss den rohen Wert setzen: `setX(raw)`, nicht
        # `setX(alt + raw)`. Ein Anhaengen waere hier der Fehler.
        # `[^)]*` scheitert an `p.set("success_emoji", raw)`: die
        # schliessende Klammer des Zeichenketten-Arguments steht davor.
        # Also bis zum `raw` suchen, ohne Klammern auszuschliessen.
        replaces = re.search(
            r"onPick=\{\(raw\)\s*=>\s*" + re.escape(setter) + r"[^;{}]*?\braw\b",
            src,
        )
        # Das Anhaengen kann verschachtelt sein:
        #   p.set("success_emoji", (p.value("success_emoji") ?? "") + raw)
        # Ein Muster mit `[^)]*` scheitert an der inneren Klammer und
        # meldete die Mutation nicht -- sie ist so entwischt. Deshalb
        # im ganzen onPick-Ausdruck nach einem `+ raw` suchen.
        pick = re.search(
            r"onPick=\{\(raw\)\s*=>\s*" + re.escape(setter) + r"[\s\S]{0,200}?\}",
            src,
        )
        appends = bool(pick and re.search(r"\+\s*raw|raw\s*\+", pick.group(0)))
        check(f"{what} ({name}) ersetzt", bool(replaces) and not appends,
              "haengt an statt zu ersetzen" if appends else "kein onPick gefunden")


def test_the_ticket_category_replaces_too():
    """Eine Ticket-Kategorie traegt genau ein Symbol."""
    print("\nDie Ticket-Kategorie ersetzt")
    src = strip_comments(read("components", "dashboard", "ticket-panels.tsx"))

    # Das Symbol wird gesetzt, nicht angehaengt.
    replaces = re.search(r"cat:\s*\{\s*\.\.\.editing\.cat,\s*emoji:\s*raw\s*\}", src)
    check("Symbol wird ersetzt", bool(replaces))

    # Der Name dagegen ist Fliesstext -- dort wird angehaengt.
    appends = "editing.cat.name + raw" in src
    check("der Name dagegen waechst", appends)


# ------------------------------------------------------------------ #
# 3. Wo die Auswahl NICHT stehen darf
# ------------------------------------------------------------------ #
def test_confirmation_fields_have_no_picker():
    """Sicherheitsabfragen pruefen auf Zeichengleichheit.

    "Tippe den Servernamen, um zu bestaetigen" vergleicht Buchstabe
    fuer Buchstabe. Ein Emoji darin macht die Abfrage unerfuellbar --
    der Knopf bliebe fuer immer grau.
    """
    print("\nSicherheitsabfragen bekommen keine Auswahl")

    for name, field in [
        ("servers-panel.tsx", "leaveConfirm"),
        ("speedrun-panel.tsx", "wipeConfirm"),
    ]:
        src = strip_comments(read("components", "dashboard", name))
        # Es darf keine Auswahl direkt an diesem Feld haengen.
        near = re.search(
            re.escape(field) + r"[\s\S]{0,400}?<EmojiPicker", src
        )
        check(f"{field} ({name}) ohne Auswahl", not near)


def test_name_fields_have_no_picker():
    """Discord rendert Custom-Emojis in Namen nicht.

    In Kanal-, Rollen- und Webhook-Namen erscheint der rohe Code als
    Text -- ``<:name:1530375445785084005>`` mitten im Kanalnamen.
    Belegt: Discord unterstuetzt dort nur Unicode-Emojis, und selbst
    die nur eingeschraenkt.

    Betroffen hier: der Anzeigename im Anonym-Chat (ein Webhook-Name)
    und die Namensvorlage fuer Sprachkanaele.
    """
    print("\nNamensfelder bekommen keine Auswahl")

    src = strip_comments(read("components", "dashboard", "anonchat-panel.tsx"))
    check("Anonym-Alias ohne Auswahl (ist ein Webhook-Name)",
          not has_picker(src))

    src = strip_comments(read("components", "dashboard", "voice-panels.tsx"))
    check("Sprachkanal-Vorlage ohne Auswahl (ist ein Kanalname)",
          not has_picker(src))


# ------------------------------------------------------------------ #
# 4. Der Baustein selbst
# ------------------------------------------------------------------ #
def test_there_is_one_shared_building_block():
    """Nicht 65 Kopien derselben Rechnung.

    Die Logik drumherum ist jedes Mal dieselbe und jedes Mal leicht
    falsch zu machen. Eine Korrektur soll einmal wirken, nicht
    fuenfundsechzigmal nachgezogen werden muessen.
    """
    print("\nEin gemeinsamer Baustein")
    src = read("components", "dashboard", "emoji-field.tsx")
    check("es gibt ihn", bool(src))

    clean = strip_comments(src)
    check("mit einem Feld fuer Fliesstext", "export function EmojiText" in clean)
    check("einem fuer genau ein Emoji", "export function EmojiOnly" in clean)
    check("und einem fuer ungesteuerte Felder",
          "export function EmojiDraftField" in clean,
          "die Ticket-Panels speichern erst beim Verlassen")


def test_the_uncontrolled_field_reports_its_change():
    """Sonst steht das Emoji im Feld und wird nie gespeichert.

    Die Ticket-Panels arbeiten mit `defaultValue` -- der Wert lebt im
    DOM. Wer dort nur `field.value` setzt, aendert die Anzeige, aber
    niemand erfaehrt davon. Beim Neuladen waere das Emoji weg, und der
    Nutzer wuesste nicht, warum.

    Geprueft wird der ERREICHBARE Aufruf: `if (false) onCommit(text)`
    liesse das Wort stehen und meldete trotzdem nie. Genau diese
    Mutation ist beim ersten Anlauf entwischt.
    """
    print("\nDas ungesteuerte Feld meldet seine Aenderung")
    src = strip_comments(read("components", "dashboard", "emoji-field.tsx"))

    block = src.split("export function EmojiDraftField")[1]
    check("es schreibt in das Element", "field.value = text" in block)

    # Der Aufruf muss unbedingt erfolgen -- nicht hinter einer
    # Bedingung, die nie zutrifft.
    guarded = re.search(r"if\s*\([^)]*\)\s*onCommit\(text\)", block)
    plain = re.search(r"^\s*onCommit\(text\);", block, re.M)
    check("und meldet die Aenderung unbedingt",
          bool(plain) and not guarded,
          "hinter einer Bedingung versteckt" if guarded else "kein Aufruf gefunden")


def test_the_focus_handler_is_passed_through():
    """Die Platzhalter-Knoepfe der Begruessung brauchen ihn.

    Sie merken sich das zuletzt benutzte Feld, um zu wissen, wohin
    {user} geschrieben werden soll. Verschluckt der Baustein `onFocus`,
    schreiben sie ins falsche Feld -- oder in gar keines.
    """
    print("\nonFocus wird durchgereicht")
    src = strip_comments(read("components", "dashboard", "emoji-field.tsx"))
    check("der Baustein nimmt onFocus an", "onFocus?:" in src)
    check("und gibt es an das Feld weiter",
          re.search(r"const shared = \{[\s\S]{0,300}?onFocus,", src) is not None,
          "sonst merkt sich die Begruessung das Feld nicht mehr")

    welcome = strip_comments(read("components", "dashboard", "welcome-form.tsx"))
    check("die Begruessung reicht track weiter",
          welcome.count("{...track}") >= 6,
          f"nur {welcome.count('{...track}')} von 6 Feldern")


def main() -> int:
    test_every_message_field_offers_the_picker()
    test_each_single_field_has_its_own_picker()
    test_the_welcome_embed_covers_every_part()
    test_each_field_uses_its_own_discord_limit()
    test_the_limit_is_checked_before_inserting()
    test_the_cursor_moves_behind_the_emoji()
    test_single_emoji_fields_replace_instead_of_insert()
    test_the_ticket_category_replaces_too()
    test_confirmation_fields_have_no_picker()
    test_name_fields_have_no_picker()
    test_there_is_one_shared_building_block()
    test_the_uncontrolled_field_reports_its_change()
    test_the_focus_handler_is_passed_through()

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
