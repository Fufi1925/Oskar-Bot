#!/usr/bin/env python3
"""
Jede Seite muss auch in der linken Seitenleiste stehen.

Warum es diese Datei gibt
-------------------------
Der Musik-Reiter wurde angelegt, die Seite gebaut, die Route
verdrahtet -- und in `components/guild-tabs.tsx` eingetragen. Nur:
das ist die Leiste *ueber* dem Inhalt. Die linke Seitenleiste ist eine
zweite, unabhaengige Liste in `app/dashboard/layout.tsx`, und dort
fehlte der Eintrag. Die Seite war nur ueber die Adresszeile oder die
Suche erreichbar.

Zwei Listen, die dasselbe beschreiben und getrennt gepflegt werden --
das laeuft irgendwann auseinander. Zusammenlegen waere die saubere
Loesung, geht hier aber nicht ohne Weiteres: die Seitenleiste gruppiert
anders, kennt Eintraege ausserhalb eines Servers (Premium, Serverliste)
und markiert manche als Beta. Also wird stattdessen geprueft, dass
beide vollstaendig sind.

Run:  python3 tests/test_sidebar_complete.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(os.path.dirname(BOT), "dashboard")

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


def strip_ts(src: str) -> str:
    """Kommentare raus.

    Sonst zaehlt eine Erklaerung als Eintrag: in `layout.tsx` steht in
    den Kommentaren woertlich `/speedrun` und `/supportqueue`. Ohne
    Strippen gaelte eine geloeschte Seite als weiterhin verlinkt --
    dieselbe Falle wie schon mehrfach in diesem Repo.
    """
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke.
    # Steht ein Pfad mit Sternchen in einem //-Kommentar, eroeffnet
    # das darin enthaltene /* sonst einen Schein-Block, der den
    # halben Quelltext verschluckt -- in test_dashboard_rollen.py
    # genau so passiert: fuenf Pruefungen meldeten »fehlt«,
    # obwohl alles da war.
    without_lines = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", without_lines, flags=re.S)


def guild_pages() -> list[str]:
    """Alle Unterseiten eines Servers, aus dem Dateisystem gelesen."""
    root = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]")
    if not os.path.isdir(root):
        return []
    return sorted(
        entry
        for entry in os.listdir(root)
        if os.path.isdir(os.path.join(root, entry))
    )


# Seiten, die bewusst nicht in der Seitenleiste stehen.
#
# Die Liste muss ehrlich bleiben: ein Eintrag fuer eine Seite, die es
# nicht mehr gibt, heisst, dass niemand mehr hinschaut.
NOT_IN_SIDEBAR = {
    # Unterseite des Levelings, ueber dessen eigene Seite erreichbar.
    "leveling/leaderboard",
}


def test_every_page_is_in_the_sidebar():
    """Sonst ist die Seite nur ueber die Adresszeile erreichbar.

    Genau das war beim Musik-Reiter der Fall: gebaut, verdrahtet,
    getestet -- und trotzdem unsichtbar, weil der Eintrag in der
    falschen der beiden Listen stand.
    """
    print("\nJede Seite steht in der linken Seitenleiste")

    layout = strip_ts(read("app", "dashboard", "layout.tsx"))
    check("die Seitenleiste ist lesbar", bool(layout))

    linked = set(
        re.findall(
            r"/dashboard/guild/\$\{currentGuildId\}/([a-z0-9\-/]+)", layout
        )
    )
    check("es gibt ueberhaupt Eintraege", len(linked) > 10, str(len(linked)))

    for page in guild_pages():
        if page in NOT_IN_SIDEBAR:
            continue
        check(f"»{page}« ist verlinkt", page in linked)


def test_the_top_tabs_are_complete_too():
    """Die zweite Liste -- die Reiter ueber dem Inhalt."""
    print("\nUnd in den Reitern darueber")

    tabs = strip_ts(read("components", "guild-tabs.tsx"))
    check("die Reiterleiste ist lesbar", bool(tabs))

    slugs = set(re.findall(r'slug:\s*"([a-z0-9\-/]+)"', tabs))
    check("es gibt ueberhaupt Reiter", len(slugs) > 10, str(len(slugs)))

    for page in guild_pages():
        if page in NOT_IN_SIDEBAR:
            continue
        check(f"»{page}« hat einen Reiter", page in slugs)


def test_no_link_points_at_a_missing_page():
    """Ein Eintrag ohne Seite fuehrt auf einen 404.

    Die Gegenrichtung ist genauso wichtig: wird eine Seite geloescht
    und der Eintrag bleibt stehen, klickt sich jemand in einen Fehler.
    """
    print("\nKein Eintrag zeigt ins Leere")

    pages = set(guild_pages())
    layout = strip_ts(read("app", "dashboard", "layout.tsx"))

    linked = set(
        re.findall(
            r"/dashboard/guild/\$\{currentGuildId\}/([a-z0-9\-/]+)", layout
        )
    )
    for target in sorted(linked):
        # Unterseiten wie leveling/leaderboard: der erste Teil muss
        # existieren.
        top = target.split("/")[0]
        check(f"»{target}« gibt es", top in pages)


def test_the_two_lists_agree():
    """Beide Listen beschreiben dasselbe -- sie muessen sich decken.

    Laufen sie auseinander, ist eine Seite an einer Stelle sichtbar
    und an der anderen nicht. Das faellt niemandem auf, der nur eine
    von beiden benutzt.
    """
    print("\nBeide Listen sind sich einig")

    layout = strip_ts(read("app", "dashboard", "layout.tsx"))
    tabs = strip_ts(read("components", "guild-tabs.tsx"))

    linked = set(
        re.findall(
            r"/dashboard/guild/\$\{currentGuildId\}/([a-z0-9\-/]+)", layout
        )
    )
    slugs = set(re.findall(r'slug:\s*"([a-z0-9\-/]+)"', tabs))

    only_sidebar = sorted(linked - slugs - NOT_IN_SIDEBAR)
    only_tabs = sorted(slugs - linked - NOT_IN_SIDEBAR)

    check("nichts nur in der Seitenleiste", not only_sidebar, str(only_sidebar))
    check("nichts nur in den Reitern", not only_tabs, str(only_tabs))


def test_the_exception_list_stays_honest():
    """Ein Eintrag fuer eine Seite, die es nicht mehr gibt, ist tot."""
    print("\nDie Ausnahmeliste ist aktuell")

    root = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]")
    for entry in sorted(NOT_IN_SIDEBAR):
        path = os.path.join(root, *entry.split("/"))
        check(f"»{entry}« gibt es noch", os.path.isdir(path))


def test_music_is_reachable():
    """Der Anlass fuer diese Datei -- ausdruecklich festgehalten."""
    print("\nDer Musik-Reiter ist erreichbar")

    layout = strip_ts(read("app", "dashboard", "layout.tsx"))
    tabs = strip_ts(read("components", "guild-tabs.tsx"))
    search = strip_ts(read("components", "global-search.tsx"))

    check("in der linken Seitenleiste", "/music`" in layout)
    check("in den Reitern darueber", 'slug: "music"' in tabs)
    # Auf das Ende der Adresse pruefen: ein blosses "/music" traefe
    # auch "/music-weg" und bliebe gruen, obwohl der Eintrag kaputt
    # ist. Genau so ist diese Pruefung beim Mutationstest entwischt.
    check(
        "und in der Suche",
        re.search(r'href:\s*"/dashboard/guild/\{g\}/music"', search) is not None,
    )

    # Und die Seite selbst muss es geben, sonst zeigt alles ins Leere.
    check(
        "die Seite existiert",
        os.path.isfile(
            os.path.join(
                DASH, "app", "dashboard", "guild", "[guildId]", "music", "page.tsx"
            )
        ),
    )


def main() -> int:
    test_every_page_is_in_the_sidebar()
    test_the_top_tabs_are_complete_too()
    test_no_link_points_at_a_missing_page()
    test_the_two_lists_agree()
    test_the_exception_list_stays_honest()
    test_music_is_reachable()

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
