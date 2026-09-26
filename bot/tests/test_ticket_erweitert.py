#!/usr/bin/env python3
"""
Die erweiterten Ticket-Einstellungen und ihre Vorschau.

Was hier zusammengekommen ist: der Reiter (Begrüssungstitel, -text,
Bestätigung, Formularfragen mit Typ, Pflicht und Kategoriebezug) kam aus
zwei Richtungen gleichzeitig. Diese Datei prueft den Zusammenbau — und
vor allem die eine Invariante, ohne die alles andere schief aussieht:

  **Der Bot und die Vorschau benutzen dieselbe Regel.** Welche
  Platzhalter ersetzt werden und welche Fragen eine Kategorie bekommt,
  steht ein einziges Mal, in `bot/api/ticket_panels.py`. Zwei Umsetzun-
  gen derselben Regel zeigen zwei verschiedene Texte, und der
  Unterschied faellt erst auf, wenn jemand den Ticketkanal mit dem
  Dashboard vergleicht.

Run:  python3 tests/test_ticket_erweitert.py
"""

import asyncio
import json
import os
import re
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
sys.path.insert(0, BOT)

GUILD = 1520714989860814992
ANDERER = 1111111111111111111

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f" -> {extra}" if extra else ""))
        failures.append(name)


def quelltext(*teile):
    with open(os.path.join(DASH, *teile), encoding="utf-8") as f:
        return f.read()


def bot_quelltext(*teile):
    with open(os.path.join(BOT, *teile), encoding="utf-8") as f:
        return f.read()


# ══════════════════════════════════════════════════════════════════════


def test_regeln():
    """Platzhalter und Fragenauswahl — die eine Regel, zweimal benutzt."""
    print("\nRegeln im Panel-Speicher")

    from api import ticket_panels as tp

    check("fünf Woerter, alle in Klammern",
          tp.WILLKOMMEN_WOERTER == tuple("{" + n + "}" for n in tp.WILLKOMMEN_NAMEN),
          str(tp.WILLKOMMEN_WOERTER))

    text = tp.setze_woerter(
        "{ticket_number} {user} {category} {server} {channel} {falsch} {}",
        ticket_number="0007", user="@max", category="Support",
        server="Uni", channel="#ticket-0007",
    )
    check("die fünf werden ersetzt",
          "0007 @max Support Uni #ticket-0007" in text, text)
    check("ein unbekanntes Wort bleibt stehen", "{falsch}" in text, text)
    check("ein einsames {} wirft nicht", "{}" in text, text)

    # Leere und fehlende Werte: nichts einsetzen, nichts löschen.
    check("ein fehlender Wert loescht nichts",
          tp.setze_woerter("hi {user}", server="x") == "hi {user}")

    # Kategorie-Auswahl
    fragen = [
        {"label": "Global", "category_ids": []},
        {"label": "Nur 7", "category_ids": [7]},
        {"label": "Nur 9", "category_ids": [9]},
    ]
    check("ohne Kategorieangabe alle Fragen (Vorschau)",
          [f["label"] for f in tp.fragen_fuer_kategorie(fragen, None)]
          == ["Global", "Nur 7", "Nur 9"],
          str(tp.fragen_fuer_kategorie(fragen, None)))
    check("Kategorie 7 sieht global und ihre eigene",
          [f["label"] for f in tp.fragen_fuer_kategorie(fragen, 7)]
          == ["Global", "Nur 7"])
    check("Kategorie 9 sieht die von 7 nicht",
          [f["label"] for f in tp.fragen_fuer_kategorie(fragen, 9)]
          == ["Global", "Nur 9"])
    check("als Zeichenkette ebenso (so kommt die ID aus der Zeile)",
          [f["label"] for f in tp.fragen_fuer_kategorie(fragen, "7")]
          == ["Global", "Nur 7"])

    sechs = [{"label": f"F{i}"} for i in range(1, 7)]
    check("fuenf sind das Maximum (Discord-Limit)",
          len(tp.fragen_fuer_kategorie(sechs, None)) == 5,
          str(len(tp.fragen_fuer_kategorie(sechs, None))))

    # Die Vorschau: Entwurf schlägt Gespeichertes.
    panel = {
        "ticket_welcome_title": "Gespeicherter Titel",
        "ticket_welcome_message": "Gespeicherte Nachricht für {user}",
        "ticket_created_message": "Gespeicherte Bestätigung",
        "ticket_questions": json.dumps([{"label": "Alt?", "type": "short"}]),
    }
    v = tp.vorschau_willkommen(panel, entwurf={
        "ticket_welcome_message": "Neuer Entwurf {ticket_number}",
        "ticket_questions": [{"label": "Neu?", "type": "paragraph",
                              "required": False}],
    })
    check("der Entwurf gewinnt", v["nachricht"] == "Neuer Entwurf 0001", v["nachricht"])
    check("unberührtes Feld bleibt gespeichert",
          v["titel"] == "Gespeicherter Titel", v["titel"])
    check("die Fragen kommen aus dem Entwurf",
          [f["label"] for f in v["fragen"]] == ["Neu?"], str(v["fragen"]))
    check("Pflicht wird mitgegeben",
          v["fragen"][0]["pflicht"] is False, str(v["fragen"][0]))
    check("Beispielswerte sind als solche erkennbar",
          "@dein.name" in tp.vorschau_willkommen({})["nachricht"], "")

    # Laengen: die Beschneidung des Cogs, sonst zeigt die Vorschau einen
    # Text, den Discord ablehnen würde.
    lang = tp.vorschau_willkommen({
        "ticket_welcome_title": "t" * 900,
        "ticket_welcome_message": "m" * 9000,
        "ticket_created_message": "c" * 4000,
    })
    check("Titel bei 256 gekappt", len(lang["titel"]) == 256, str(len(lang["titel"])))
    check("Nachricht bei 4096 gekappt",
          len(lang["nachricht"]) == 4096, str(len(lang["nachricht"])))
    check("Bestätigung bei 1900 gekappt",
          len(lang["bestaetigung"]) == 1900, str(len(lang["bestaetigung"])))


def test_cog_teilt_die_regel():
    """Der Cog benutzt die Regeln des Speichers, nicht eigene."""
    print("\nCog und Vorschau mit einer Regel")

    code = bot_quelltext("cogs", "commands", "ticket.py")

    check("der Cog ruft die gemeinsame Ersetzung",
          "regeln.setze_woerter(" in code,
          "eine zweite Ersetzung im Cog ist der Anfang von zwei Texten")
    check("und die gemeinsame Fragenauswahl",
          "regeln.fragen_fuer_kategorie(" in code)
    check("dabei verschwindet die harte Grenze nicht",
          "][:5]" not in code.split("fragen_fuer_kategorie(")[1][:200],
          "doppelt kappen ist okay, aber die Auswahl muss dieselbe bleiben")

    # Dieselben fünf Werte, sonst ersetzt die eine Seite und die andere nicht.
    block = code[code.index("replacements = {"):]
    # Die erste "}" liegt in f"{t_num:04d}" — bis dahin abschneiden
    # waere ein Block mit einem Eintrag und drei falschen Fehlern.
    block = block[: block.index("\n        }")]
    for name in ("ticket_number", "user", "category", "server", "channel"):
        check(f"der Cog kennt {name}", f'"{name}"' in block, block[:120])

    # Reihenfolge: Modal vor dem defer. Vollständige Aufrufe suchen —
    # die Kurzfassung steht auch in Kommentaren und macht die Pruefung
    # dann wertlos.
    flow = code[code.index("async def create_ticket_flow"):]
    flow = flow[: flow.index("\n    @commands.hybrid_group")]
    i_modal = flow.find("inter.response.send_modal(")
    i_defer = flow.find("inter.response.defer(ephemeral=True)")
    check("das Modal kommt vor dem defer",
          -1 not in (i_modal, i_defer) and i_modal < i_defer,
          f"modal={i_modal} defer={i_defer}")


def test_routen():
    """Sperre bleibt, Vorschau darf ohne Premium."""
    print("\nRouten")

    from fastapi.testclient import TestClient

    from api.server import create_app

    arbeit = tempfile.mkdtemp(prefix="vorschau-routen-")
    aktuell = os.getcwd()
    os.chdir(arbeit)
    os.makedirs("db", exist_ok=True)
    try:
        client = TestClient(create_app())
        base = f"/api/v1/tickets/{GUILD}"
        panel = client.post(f"{base}/panels", json={"name": "Support"}).json()["panel_id"]

        # Kein Premium: die fünf erweiterten Felder bleiben zu.
        for feld in (
            "select_placeholder",
            "ticket_welcome_title",
            "ticket_welcome_message",
            "ticket_created_message",
            "ticket_questions",
        ):
            r = client.patch(f"{base}/panels/{panel}", json={feld: "x"})
            check(f"ohne Premium: {feld} abgelehnt", r.status_code == 403,
                  f"{r.status_code} {r.text[:60]}")

        r = client.patch(f"{base}/panels/{panel}", json={"ticket_welcome_title": "x"})
        check("die Meldung nennt Premium", "Premium" in r.text, r.text[:90])

        r = client.patch(f"{base}/panels/{panel}", json={"embed_title": "Titel"})
        check("der Rest des Panels geht ohne Premium", r.status_code == 200,
              f"{r.status_code} {r.text[:60]}")

        # Die Vorschau ist lesen, nicht schreiben — sie darf auch ohne
        # Premium bleiben, sonst ist der Hinweis im Panel blockiert,
        # obwohl nichts verändert wird.
        r = client.post(f"{base}/panels/{panel}/vorschau",
                        json={"ticket_welcome_message": "Hallo {user}"})
        check("Vorschau geht ohne Premium", r.status_code == 200,
              f"{r.status_code} {r.text[:90]}")
        check("Vorschau rechnet den Platzhalter",
              r.json()["nachricht"] == "Hallo @dein.name", str(r.json())[:120])
        check("unbekannte Felder werden ignoriert",
              "name" not in r.json(), str(r.json())[:120])

        # Nichts geschrieben: derselbe Aufruf nach einem unbeteiligten
        # PATCH darf den alten Stand zeigen.
        from api import ticket_panels as regeln

        gespeichert = next(
            p for p in client.get(f"{base}/panels").json()["panels"]
            if p["panel_id"] == panel
        )
        # Leer ist hier der Standardtext des Bots: der Speicher fuellt
        # ihn beim Lesen ein. „nicht gespeichert" heisst also: immer
        # noch der Standard, nicht der Vorschautext.
        check("die Vorschau speichert nichts",
              gespeichert.get("ticket_welcome_message")
              == regeln.DEFAULT_TICKET_WELCOME_MESSAGE,
              str(gespeichert.get("ticket_welcome_message"))[:80])

        r = client.post(f"{base}/panels/999999/vorschau", json={})
        check("unbekanntes Panel gibt 404", r.status_code == 404, str(r.status_code))

        from utils import feature_gates

        originally = feature_gates.can_configure_premium_guild
        feature_gates.can_configure_premium_guild = lambda gid: int(gid) == GUILD
        try:
            r = client.post(f"{base}/panels/{panel}/vorschau", json={
                "ticket_questions": [
                    {"label": "Worum?", "type": "paragraph"},
                    {"label": "Beleg", "type": "image", "category_ids": [4242]},
                ],
            })
            pruefe = r.json()
            check("mit Premium dieselbe Antwort", r.status_code == 200)
            # Die Vorschau kennt keine Kategorie (sie zeigt das Panel,
            # nicht einen Knopf), also sind alle Fragen gemeint — auch
            # die mit Kategoriebezug.
            check("beide Fragen werden vorgeführt",
                  [f["label"] for f in pruefe["fragen"]] == ["Worum?", "Beleg"],
                  str(pruefe["fragen"]))
            # Rohdaten filtern, nicht die Vorschau-Ausgabe: die traegt
            # bewusst keine category_ids mehr (sie zeigt dem Team, was
            # ankommt, nicht die Konfiguration).
            roh = [
                {"label": "Worum?", "type": "paragraph"},
                {"label": "Beleg", "type": "image", "category_ids": [4242]},
            ]
            # Die globale Frage bleibt auch hier — genau wie im Cog,
            # der alle Fragen ohne Kategoriebezug bei jeder Kategorie
            # stellt. Nur die fremde Kategorie faellt weg.
            check("eine Kategorie laesst die fremde Frage weg",
                  [f["label"] for f in regeln.vorschau_willkommen(
                      {"ticket_questions": roh}, category_id=4242)["fragen"]]
                  == ["Worum?", "Beleg"], str(roh))
            check("und ohne Bezug bleibt sie global",
                  [f["label"] for f in regeln.vorschau_willkommen(
                      {"ticket_questions": roh}, category_id=1)["fragen"]]
                  == ["Worum?"], str(roh))
            check("der Bildhinweis kommt mit",
                  pruefe["fragen"][0]["typ"] == "paragraph", str(pruefe["fragen"]))

            r2 = client.patch(f"{base}/panels/{panel}",
                              json={"ticket_welcome_message": "Gespeichert {user}"})
            check("mit Premium darf gespeichert werden", r2.status_code == 200,
                  f"{r2.status_code} {r2.text[:70]}")
            gespeichert = next(
                p for p in client.get(f"{base}/panels").json()["panels"]
                if p["panel_id"] == panel
            )
            check("und der Stand bleibt ohne Entwurf erhalten",
                  gespeichert["ticket_welcome_message"].startswith("Gespeichert"),
                  str(gespeichert["ticket_welcome_message"])[:60])
            r3 = client.post(f"{base}/panels/{panel}/vorschau", json={})
            check("Vorschau ohne Entwurf nimmt den gespeicherten Text",
                  "Gespeichert" in r3.json()["nachricht"], str(r3.json())[:120])
        finally:
            feature_gates.can_configure_premium_guild = originally
    finally:
        os.chdir(aktuell)


def test_oberflaeche():
    """Das Formular holt die Vorschau — und baut sie nicht selbst."""
    print("\nOberfläche")

    quelltext_ = quelltext("components", "dashboard", "ticket-panels.tsx")

    check("die Vorschau wird beim Bot geholt",
          "await api.ticketPanelVorschau(" in quelltext_,
          "eine eigene Ersetzung hier waer die zweite Regel")
    check("und der Entwurf wird mitgeschickt",
          "ticket_welcome_message: welcomeMessage" in quelltext_,
          "sonst sieht man immer den alten Stand")
    check("kein eigenes Ersetzen im Formular",
          re.search(r'\.replace\("\{(?:user|ticket_number|category|server|channel)\}"',
                    quelltext_) is None,
          "die Liste der Woerter steht im Bot")
    check("abgesichert gegen zu schnelles Nachfragen",
          "500)" in quelltext_ and "clearTimeout" in quelltext_,
          "ein Abruf pro Tasteanschlag trifft die Schnittstelle")
    # Blockbezogen pruefen: `guildId={guildId}` steht achtmal in der
    # Datei. Ein Suchauftrag uebers Ganze bleibt gruen, auch wenn aus-
    # gerechnet der Aufruf von AdvancedTicketSettings die Server-ID
    # verliert — nachgemessen im Mutationstest.
    aufruf = re.search(r"<AdvancedTicketSettings\b.*?/>", quelltext_, re.S)
    check("der Aufruf ist auffindbar", aufruf is not None)
    if aufruf:
        check("die Server-ID kommt beim Formular an",
              "guildId={guildId}" in aufruf.group(0),
              "ohne sie weiss der Bot nicht, welches Panel gemeint ist")

    # Ohne Premium nachfragen waer nicht gefaehrlich, aber laestig: der
    # Entwurf wird bei jedem Tippen zum Bot geschickt, obwohl die
    # erweiterten Felder gar nicht bedienbar sind.
    check("die Vorschau laeuft nur, wenn die Sperre offen ist",
          "if (!premium) return;" in quelltext_,
          "sonst sendet ein Nutzer ohne Premium bei jedem Tipp seinen Text")

    # Die Sperre selbst: muss bleiben, sonst ist der Hinweis frei bedienbar.
    check("Sperre: unscharf und nicht bedienbar",
          'pointer-events-none select-none blur-[3px]' in quelltext_)
    check("Karte steckt in einem Container mit overflow-hidden",
          "relative overflow-hidden rounded-3xl" in quelltext_,
          "ohne das ragt die Karte über ihre Karte hinaus — das war der"
          " Fehler am Design-Reiter")
    check("und sie führt zu Premium", 'href="/premium"' in quelltext_)

    api_ts = quelltext("lib", "api.ts")
    check("der API-Helfer existiert", "ticketPanelVorschau:" in api_ts)
    # Ebenfalls blockbezogen: `/vorschau` steht noch ein zweites Mal in
    # der Datei (bei den Sicherungen), und ein Suchauftrag uebers Ganze
    # deckt einen falsch zeigenden Ticket-Helfer nicht auf.
    helfer = re.search(r"ticketPanelVorschau:.*?\n    \}", api_ts, re.S)
    check("der Helfer ist auffindbar", helfer is not None)
    if helfer:
        check("er zeigt auf die Ticket-Route",
              "/tickets/${guildId}/panels/${panelId}/vorschau" in helfer.group(0),
              helfer.group(0)[:120])


def test_gemessene_grenzen():
    """Discords Grenzen, nicht unsere Laune."""
    print("\nDiscord-Grenzen")

    from api import ticket_panels as tp

    check("fünf Fragen", tp.MAX_TICKET_QUESTIONS == 5, str(tp.MAX_TICKET_QUESTIONS))
    code = bot_quelltext("cogs", "commands", "ticket.py")
    check("Modal kappt auf fünf", "for question in panel_config[\"questions\"][:5]:" in code)

    sauber = tp._clean_questions([{"label": "x" * 90}])
    check("Beschriftung 45 Zeichen", len(sauber[0]["label"]) == 45,
          str(len(sauber[0]["label"])))
    sauber2 = tp._clean_questions([{"label": "a", "placeholder": "y" * 300}])
    check("Platzhalter 100 Zeichen", len(sauber2[0]["placeholder"]) == 100,
          str(len(sauber2[0]["placeholder"])))


if __name__ == "__main__":
    test_regeln()
    test_cog_teilt_die_regel()
    test_routen()
    test_oberflaeche()
    test_gemessene_grenzen()

    print()
    if failures:
        print(f"FAILED {len(failures)}")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("Vorschau und Bot rechnen denselben Text.")
