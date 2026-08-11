#!/usr/bin/env python3
"""
Ticket-Rechte, Schalter-Darstellung und der Abschied-Reiter.

Drei Meldungen auf einmal:

  1. Wer ein Ticket erstellt, sieht seinen Kanal, kann aber nichts
     hineinschreiben.
  2. Manche Schalter im Dashboard sind verrutscht -- der weisse Knopf
     haengt rechts ueber die Bahn hinaus.
  3. Der Abschied soll einen eigenen Reiter bekommen, wie die
     Begruessung.

Run:  python3 tests/test_ticket_perms_and_toggle.py
"""

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(rel: str) -> str:
    return open(os.path.join(BOT, rel), encoding="utf-8").read()


def read_dash(rel: str) -> str:
    return open(os.path.join(DASH, rel), encoding="utf-8").read()


# ── 1. Die Rechte im frischen Ticket ─────────────────────────────────

def rechte_im_ticket() -> dict[str, set[str]]:
    """
    Welche Rechte bekommt wer -- aus dem Syntaxbaum.

    Nicht per Textsuche: die Aufrufe gehen ueber mehrere Zeilen, und
    ein Muster wie ``\\(([^)]*)\\)`` hoert beim ersten Klammerende auf.
    Ausserdem steht der Wert fuer den Ersteller inzwischen in einer
    Zwischenvariablen, der gefolgt werden muss.
    """
    roh = read("cogs/commands/ticket.py")
    baum = ast.parse(roh)

    quelle = None
    for k in ast.walk(baum):
        if isinstance(k, ast.AsyncFunctionDef) and k.name == "create_ticket_flow":
            quelle = ast.get_source_segment(roh, k)
    if quelle is None:
        return {}

    lokal = ast.parse(quelle.lstrip())

    def keywords(knoten):
        if not isinstance(knoten, ast.Call):
            return None
        if ast.unparse(knoten.func).split(".")[-1] != "PermissionOverwrite":
            return None
        return {
            k.arg for k in knoten.keywords
            if k.arg and ast.unparse(k.value) == "True"
        }

    # Zwischenvariablen aufloesen: name -> Rechte
    variablen: dict[str, set[str]] = {}
    for knoten in ast.walk(lokal):
        if isinstance(knoten, ast.Assign) and len(knoten.targets) == 1:
            ziel = knoten.targets[0]
            if isinstance(ziel, ast.Name):
                kw = keywords(knoten.value)
                if kw is not None:
                    variablen[ziel.id] = kw

    ergebnis: dict[str, set[str]] = {}

    def eintragen(schluessel: str, wert):
        kw = keywords(wert)
        if kw is None and isinstance(wert, ast.Name):
            kw = variablen.get(wert.id)
        if kw is not None:
            ergebnis[schluessel] = kw

    for knoten in ast.walk(lokal):
        if isinstance(knoten, ast.Dict):
            for schluessel, wert in zip(knoten.keys, knoten.values):
                if schluessel is None:
                    continue
                eintragen(ast.unparse(schluessel).strip(), wert)
        if isinstance(knoten, ast.Assign):
            for ziel in knoten.targets:
                text = ast.unparse(ziel)
                if "overwrites[" in text:
                    eintragen(text, knoten.value)

    return ergebnis


def test_ticket_rechte():
    print("\n1. Wer darf im frischen Ticket schreiben?")
    rechte = rechte_im_ticket()

    ersteller = rechte.get("user", set())
    print(f"     Ersteller: {sorted(ersteller) or '(nichts)'}")
    check("der Ersteller darf den Kanal sehen", "view_channel" in ersteller)
    check("der Ersteller darf schreiben", "send_messages" in ersteller,
          "-> er sieht sein eigenes Ticket und kann nichts hineinschreiben")
    check("der Ersteller sieht den bisherigen Verlauf",
          "read_message_history" in ersteller,
          "-> sonst ist der Kanal beim Oeffnen leer")
    check("der Ersteller darf Dateien anhaengen", "attach_files" in ersteller,
          "-> ein Screenshot ist bei einem Ticket der Normalfall")

    # Genau der Eintrag `overwrites[role] = ...`; "role" allein traefe
    # auch `guild.default_role` aus dem Dict darueber.
    rolle = rechte.get("overwrites[role]", set())
    print(f"     Team-Rolle: {sorted(rolle) or '(nichts)'}")
    check("das Team darf schreiben", "send_messages" in rolle,
          "-> das Team koennte nur zusehen")
    check("das Team sieht den Verlauf", "read_message_history" in rolle)

    bot_rechte = rechte.get("guild.me", set())
    print(f"     Bot: {sorted(bot_rechte) or '(nichts)'}")
    check("der Bot darf schreiben", "send_messages" in bot_rechte,
          "-> schon die Begruessung im Ticket schluege fehl")

    # @everyone muss ausgesperrt bleiben -- ein Ticket ist privat.
    #
    # Nicht per Textsuche nach dem ganzen Ausdruck: der aendert sich
    # mit, wenn jemand False zu True macht, und dann findet die Suche
    # eben nichts und bleibt still. Stattdessen wird gefragt, welche
    # Rechte @everyone bekommt -- rechte_im_ticket() sammelt nur die
    # auf True gesetzten.
    everyone = rechte.get("guild.default_role", set())
    print(f"     @everyone: {sorted(everyone) or '(nichts erlaubt)'}")
    check("@everyone darf das Ticket nicht sehen",
          "view_channel" not in everyone,
          "-> das Ticket waere fuer den ganzen Server sichtbar")
    check("@everyone bekommt ueberhaupt kein Recht", not everyone,
          f"-> {sorted(everyone)}")


# ── 2. Die Schalter ──────────────────────────────────────────────────

def test_schalter():
    """
    Ein `absolute` positionierter Knopf ohne `left` faellt auf seine
    statische Position zurueck -- und die zentriert ein <button>. Bei
    48px Bahn und 20px Knopf sind das 14px statt 2px; `translate-x-6`
    schiebt ihn dann auf 38px, er endet bei 58px und haengt 10px ueber
    den rechten Rand. Genau so sah es auf dem gemeldeten Bild aus.
    """
    print("\n2. Kein Schalter haengt mehr ueber den Rand")

    verdaechtig = []
    for wurzel, _, dateien in os.walk(DASH):
        if "node_modules" in wurzel or ".next" in wurzel:
            continue
        for name in dateien:
            if not name.endswith(".tsx"):
                continue
            pfad = os.path.join(wurzel, name)
            inhalt = open(pfad, encoding="utf-8").read()
            for treffer in re.finditer(r'"([^"]*\babsolute\b[^"]*)"', inhalt):
                klassen = treffer.group(1)
                if "top-" not in klassen:
                    continue
                if re.search(r"\b(left|right|inset)-", klassen):
                    continue
                umfeld = inhalt[treffer.start():treffer.start() + 320]
                if "translate-x" in umfeld:
                    zeile = inhalt[:treffer.start()].count("\n") + 1
                    verdaechtig.append(f"{os.path.relpath(pfad, DASH)}:{zeile}")

    check("kein Knopf ohne Anker", not verdaechtig,
          f"-> {verdaechtig[:4]} rutschen ueber den Rand")

    # Der gemeinsame Baustein muss die Rechnung richtig machen.
    formen = read_dash("components/dashboard/form-elements.tsx")
    check("es gibt einen gemeinsamen Schalter", "export const SwitchToggle" in formen)

    block = formen.split("export const SwitchToggle")[1][:900]
    check("die Bahn ist 48px breit", "w-12" in block)
    check("der Knopf ist verankert", "left-0.5" in block,
          "-> ohne Anker faellt er auf die zentrierte Position zurueck")
    check("der Weg passt zur Bahn", "translate-x-6" in block,
          "-> 48 - 20 - 2 - 2 = 24px")

    # Und die drei Kopien muessen ihn wirklich benutzen.
    for datei in ("components/dashboard/greet-extras-panel.tsx",
                  "components/dashboard/ticket-notify-panel.tsx"):
        inhalt = read_dash(datei)
        check(f"{os.path.basename(datei)} nutzt den gemeinsamen Schalter",
              "SwitchToggle" in inhalt,
              "-> eine eigene Kopie holt sich denselben Fehler zurueck")
        check(f"{os.path.basename(datei)} hat keine eigene Bahn mehr",
              "rounded-full transition-colors shrink-0 disabled:opacity-40" not in inhalt,
              "-> die alte Kopie steht noch da")


# ── 3. Der Abschied-Reiter ───────────────────────────────────────────

def test_abschied_reiter():
    print("\n3. Der Abschied hat einen eigenen Reiter")

    seite = os.path.join(DASH, "app/dashboard/guild/[guildId]/leave/page.tsx")
    check("die Seite existiert", os.path.isfile(seite))
    if os.path.isfile(seite):
        inhalt = open(seite, encoding="utf-8").read()
        check("sie zeigt nur den Abschied", 'show="leave"' in inhalt,
              "-> sonst steht das Willkommensbild doppelt da")
        check("sie ist als Abschied ueberschrieben", "Abschied" in inhalt)

    welcome = read_dash("app/dashboard/guild/[guildId]/welcome/page.tsx")
    check("die Begruessung zeigt den Abschied nicht mehr",
          'show="welcome"' in welcome,
          "-> sonst gibt es ihn zweimal, an zwei Stellen bearbeitbar")

    panel = read_dash("components/dashboard/greet-extras-panel.tsx")
    check("das Panel kennt den Umschalter", 'show?: "welcome" | "leave" | "both"' in panel)
    check("der Willkommensteil laesst sich ausblenden", 'show !== "leave"' in panel)
    check("der Abschiedsteil laesst sich ausblenden", 'show !== "welcome"' in panel)

    # Fuenf Stellen, sonst findet die Seite niemand.
    tabs = read_dash("components/guild-tabs.tsx")
    check("Reiter eingetragen", 'slug: "leave"' in tabs)
    check("Reiter-Icon importiert",
          bool(re.search(r"^\s*DoorOpen,\s*$", tabs, re.M)),
          "-> sonst bricht der Build")
    suche = read_dash("components/global-search.tsx")
    check("in der Suche eingetragen", "/leave" in suche)
    check("Such-Icon importiert",
          bool(re.search(r"^\s*DoorOpen,\s*$", suche, re.M)))
    layout = read_dash("app/dashboard/layout.tsx")
    check("in der Seitenleiste eingetragen", "/leave`" in layout)

    save_bars = read("tests/test_dashboard_save_bars.py")
    check("in der Ausnahmeliste der Speicherleisten", '"leave",' in save_bars,
          "-> der Reiter speichert sofort, eine Leiste haette nichts zu tun")


def main():
    test_ticket_rechte()
    test_schalter()
    test_abschied_reiter()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Ticket-Rechte, Schalter und Abschied-Reiter: alles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
