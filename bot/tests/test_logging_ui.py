#!/usr/bin/env python3
"""
Der Logs-Reiter: die Oberfläche.

Die Gegenstücke dazu stehen in test_logging_tab.py -- dort geht es um
das Modul selbst (welche Ereignisse in welche Kategorie gehören). Hier
um den Reiter, der es bedienbar macht.

Neu gebaut, weil neun gleich aussehende Karten die falsche Antwort auf
die Frage waren, die Leute hier stellen. Sie lautet nicht „welche der
neun Ereignisarten will ich?", sondern „ich will mitbekommen, was auf
meinem Server los ist".

Was diese Datei festhält:

  * Beim Umbau darf keine Funktion verlorengehen. Genau das ist mir
    passiert -- `setAllLogging` fiel weg, der Endpunkt blieb ungenutzt,
    und niemand hätte es bemerkt, bis jemand den Knopf sucht.
  * Jede Kategorie des Cogs muss erreichbar bleiben. Vor dem letzten
    Umbau fehlten drei von neun ganz.
  * Angeschaltet ohne Kanal ist der gefährlichste Zustand: man glaubt zu
    protokollieren und tut es nicht. Das muss sichtbar sein.

Run:  python3 tests/test_logging_ui.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")
sys.path.insert(0, BOT)

failures: list[str] = []

PANEL = os.path.join(DASH, "components", "dashboard", "logging-panel.tsx")


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(path):
    if not os.path.isfile(path):
        return ""
    return open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """Kommentare raus, damit eine Erklärung nicht als Code zählt."""
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


def test_every_endpoint_is_still_used():
    """Ein Umbau darf keinen Endpunkt zurücklassen.

    Beim Neubau ist mir `setAllLogging` durchgerutscht: die Route
    existierte weiter, das Dashboard rief sie nicht mehr auf, und der
    Knopf „alles in einen Kanal" war einfach weg.
    """

    print("\nAlle Endpunkte werden benutzt")

    panel = strip_comments(read(PANEL))

    for name in ("getLogging", "updateLogging", "setAllLogging", "testLogging"):
        check(f"{name} wird aufgerufen", f"api.{name}(" in panel,
              "die Route gibt es, der Reiter benutzt sie nicht")

    # Und die Routen gibt es wirklich -- ein Aufruf ins Leere wäre
    # genauso kaputt, nur andersherum.
    from api.routes import logging_cfg

    paths = {r.path for r in logging_cfg.router.routes}
    for path in ("/{guild_id}", "/{guild_id}/all", "/{guild_id}/test/{category}"):
        check(f"die Route {path} gibt es", path in paths, str(sorted(paths)))


def test_every_category_of_the_cog_is_reachable():
    """Vor dem letzten Umbau fehlten drei von neun Arten ganz.

    Sie waren dann nur noch per Chat-Befehl erreichbar, und `/log status`
    meldete sie für immer als „nicht eingerichtet".
    """

    print("\nJede Art des Cogs ist erreichbar")

    from api.routes.logging_cfg import CATEGORIES

    panel = strip_comments(read(PANEL))

    # Die Gruppen des Reiters decken alle Kategorien ab.
    grouped = set(re.findall(r'"([a-z_]+_events|member_moderation)"', panel))
    missing = [key for key in CATEGORIES if key not in grouped]
    check("keine Art fehlt in den Gruppen", not missing, str(missing))

    # Und keine erfundene, die es im Cog nicht gibt.
    unknown = [key for key in grouped if key not in CATEGORIES]
    check("keine erfundene Art", not unknown, str(unknown))

    # Jede Art hat ein Symbol -- sonst sehen drei Zeilen gleich aus.
    icons = panel.split("const ICONS")[1].split("};")[0]
    without_icon = [key for key in CATEGORIES if f"{key}:" not in icons]
    check("jede Art hat ein Symbol", not without_icon, str(without_icon))


def test_the_groups_cover_everything_exactly_once():
    """Eine Art in zwei Gruppen wäre zweimal schaltbar -- mit
    widersprüchlichem Ergebnis, je nachdem, wo man zuletzt geklickt hat.
    """

    print("\nDie Gruppen überschneiden sich nicht")

    from api.routes.logging_cfg import CATEGORIES

    panel = read(PANEL)
    block = panel.split("const GROUPS")[1].split("];")[0]

    keys: list[str] = []
    for group in re.findall(r"keys: \[([^\]]+)\]", block):
        keys.extend(re.findall(r'"([a-z_]+)"', group))

    check("alle Arten sind einsortiert",
          set(keys) == set(CATEGORIES),
          f"fehlt: {set(CATEGORIES) - set(keys)}, zu viel: {set(keys) - set(CATEGORIES)}")
    check("keine Art doppelt", len(keys) == len(set(keys)),
          str([k for k in keys if keys.count(k) > 1]))


def test_presets_do_not_quietly_include_the_noisy_one():
    """Reaktionen fluten den Kanal -- das muss man wählen, nicht erben.

    Eine Reaktion entsteht bei jedem Klick auf ein Emoji. In „Das
    Nötigste" hätte sie nichts verloren.
    """

    print("\nDie laute Art steckt nicht in den kleinen Voreinstellungen")

    panel = read(PANEL)
    block = panel.split("const PRESETS")[1].split("];")[0]

    # Die Voreinstellungen der Reihe nach.
    presets = re.findall(r'key: "(\w+)",.*?keys: (null|\[[^\]]*\])', block, re.S)
    check("es gibt drei Voreinstellungen", len(presets) == 3, str(len(presets)))

    for name, keys in presets:
        has_reactions = "reaction_events" in keys
        if name == "everything":
            check("„Alles“ nimmt Reaktionen mit", keys == "null" or has_reactions)
        else:
            check(f"„{name}“ lässt Reaktionen weg", not has_reactions,
                  "eine Reaktion pro Emoji-Klick flutet den Kanal")


def test_a_switched_on_category_without_a_channel_is_flagged():
    """Der gefährlichste Zustand: man glaubt zu protokollieren.

    Angeschaltet, aber kein Kanal -- da landet nichts, und ohne Hinweis
    fällt es erst auf, wenn man einen Eintrag sucht, den es nie gab.
    """

    print("\nAn ohne Kanal wird angezeigt")

    panel = strip_comments(read(PANEL))

    check("es gibt eine Zählung dafür", "broken" in panel)
    check("sie prüft auf fehlenden Kanal",
          "if (!s.channel) return true;" in panel,
          "sonst zählt sie nur, was der Server schon meldet")
    check("gelöschte Kanäle zählen auch",
          "channel_info?.missing" in panel)
    check("und fehlendes Schreibrecht",
          "channel_info?.cannot_post" in panel,
          "ein Kanal ohne Schreibrecht sieht sonst gültig aus")
    check("es wird oben zusammengefasst",
          "aber dort landet" in panel,
          "eine Zahl allein sagt nicht, welche Art betroffen ist")


def test_the_server_reports_a_missing_write_permission():
    """Das Panel liest `cannot_post` -- der Server muss es auch senden.

    Zuerst habe ich nur geprüft, dass das Panel das Feld liest. Das war
    wertlos: der Server sendete es gar nicht, die Anzeige war tot, und
    der Test blieb grün. Also hier gegen die echte Funktion.
    """

    print("\nDer Server meldet fehlendes Schreibrecht")

    from api.routes.logging_cfg import _channel_info

    class Perms:
        def __init__(self, ok):
            self.view_channel = ok
            self.send_messages = ok

    class Channel:
        name = "logs"

        def __init__(self, ok):
            self._ok = ok

        def permissions_for(self, _member):
            return Perms(self._ok)

    class Guild:
        me = object()

        def __init__(self, channel):
            self._channel = channel

        def get_channel(self, _id):
            return self._channel

    allowed = _channel_info(Guild(Channel(True)), 5)
    denied = _channel_info(Guild(Channel(False)), 5)
    gone = _channel_info(Guild(None), 5)

    check("das Feld wird geliefert", "cannot_post" in allowed, str(allowed))
    check("mit Schreibrecht ist es False",
          allowed.get("cannot_post") is False, str(allowed))
    check("ohne Schreibrecht ist es True",
          denied.get("cannot_post") is True, str(denied))
    check("ein gelöschter Kanal bleibt missing",
          gone.get("missing") is True and gone.get("cannot_post") is False,
          str(gone))

    # Ein Kanaltyp ohne permissions_for darf die Antwort nicht kosten.
    class Odd:
        name = "forum"

    weird = _channel_info(Guild(Odd()), 5)
    check("ein ungewöhnlicher Kanal wirft nicht",
          weird.get("cannot_post") is False, str(weird))


def test_the_save_bar_matches_the_shared_component():
    """Die Schnittstelle ist `count`/`onDiscard`, nicht `dirty`/`onReset`.

    Hier habe ich beim Neubau die Namen geraten und TypeScript hat es
    gefangen. Der Test hält es fest, damit es nicht beim nächsten Mal
    wieder passiert.
    """

    print("\nDie Speicherleiste passt zur gemeinsamen Komponente")

    panel = strip_comments(read(PANEL))
    bar = panel.split("<StickySaveBar")[1].split("/>")[0]

    for prop in ("count=", "onDiscard=", "onSave=", "busy=", "shake="):
        check(f"{prop} wird gesetzt", prop in bar, bar.strip()[:150])

    check("keine erfundenen Namen",
          "dirty=" not in bar and "onReset=" not in bar and "guard=" not in bar,
          bar.strip()[:150])


def main():
    test_every_endpoint_is_still_used()
    test_every_category_of_the_cog_is_reachable()
    test_the_groups_cover_everything_exactly_once()
    test_presets_do_not_quietly_include_the_noisy_one()
    test_a_switched_on_category_without_a_channel_is_flagged()
    test_the_server_reports_a_missing_write_permission()
    test_the_save_bar_matches_the_shared_component()

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
