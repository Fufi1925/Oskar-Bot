#!/usr/bin/env python3
"""
Dashboard-Rollen: ergaenzen, nicht ersetzen.

Der gemeldete Fehler
--------------------
Der Nutzer: „sobald man eine Dashboard-Rolle hat, kann man nichts mehr
machen -- egal was ich einstelle, 'missing permission'. Sobald die
Rolle weg ist, geht es wieder.“

Nachgemessen, und zwar genau so: in 24 Server-Bereichen des Proxys
stand

    const team = await fetchTeamAccess(userId);
    if (!team || team.roles.length === 0) return { ok: true };
    if (await hasTeamPermission(...)) return { ok: true };
    return deny(403);

**Ohne** Rolle kam man durch -- die Discord-Pruefung
(`verifyGuildAccess`) lief ja darueber. **Mit** Rolle zaehlte ab da nur
noch die Rolle. Wer sich als Server-Inhaber selbst eine enge Rolle wie
„Ticket Support“ gab, verlor damit auf dem eigenen Server jedes Recht,
das diese Rolle nicht ausdruecklich enthielt.

Eine Rolle ist eine **Zusatzbefugnis** fuer Leute ohne Discord-Rechte.
Sie darf niemandem etwas wegnehmen.

Was hier festgehalten wird
--------------------------
  1. Jeder serverbezogene Bereich laesst Discord-Verwalter durch --
     und zwar VOR der Rollenpruefung. Danach waere die Zeile
     wirkungslos, weil vorher schon 403 zurueckkommt.
  2. `managesGuildOnDiscord` sagt im Zweifel NEIN. Ein Ausfall der
     Discord-API darf kein Freifahrtschein sein.
  3. Jede der 41 Rollen sieht mindestens einen Reiter, und jeder
     Reiter, den der Proxy schuetzt, ist auch in der Oberflaeche
     hinterlegt. Sonst steht er in der Leiste und gibt beim Klick
     eine Fehlermeldung.
  4. Ohne Rolle: kein Link, keine Reiter, kein Zugang zur Seite.
  5. Waehrend die Rechte laden, wird NICHTS gezeigt -- vorher war es
     „alles“.

Run:  python3 tests/test_dashboard_rollen.py
"""

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
sys.path.insert(0, BOT)

from utils import dashboard_roles as dr  # noqa: E402

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read_dash(*teile) -> str:
    with open(os.path.join(DASH, *teile), encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    """Kommentare raus -- aber in der richtigen Reihenfolge.

    Erst die Zeilenkommentare, dann die Bloecke. Andersherum ist eine
    Falle, in die dieser Test beim Schreiben selbst getappt ist: in
    einem `//`-Kommentar stand ein Pfad mit Sternchen, und das darin
    enthaltene `/*` eroeffnete fuer den Block-Regex einen Kommentar,
    der erst 12.000 Zeichen spaeter wieder zuging. Der halbe Quelltext
    war weg, fuenf Pruefungen meldeten „fehlt“ -- obwohl alles da war.

    Ein Test, der zu wenig sieht, meldet Fehler, die es nicht gibt.
    Das ist genauso schaedlich wie einer, der zu viel durchlaesst.
    """
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


PROXY = os.path.join("app", "api", "bot", "[...path]", "route.ts")


def bereiche(src: str) -> list[tuple[str, str]]:
    """Die Datei in ihre `if (scope === "...")`-Bloecke zerlegen."""
    marken = list(re.finditer(r'if \(scope === "(\w+)"\) \{', src))
    out = []
    for i, m in enumerate(marken):
        ende = marken[i + 1].start() if i + 1 < len(marken) else len(src)
        out.append((m.group(1), src[m.start():ende]))
    return out


# ══════════════════════════════════════════════════════════════════════
#  1. Der eigentliche Fehler
# ══════════════════════════════════════════════════════════════════════


def test_rolle_ersetzt_nicht():
    print("\nEine Rolle ergaenzt Discord-Rechte, sie ersetzt sie nicht")

    src = strip_ts(read_dash(PROXY))
    alle = bereiche(src)
    check("die Datei liess sich zerlegen", len(alle) >= 30, f"{len(alle)}")

    mit_rollen = [
        (n, t) for n, t in alle
        if "hasTeamPermission" in t or "team.roles.length === 0" in t
    ]
    check("es gibt Bereiche mit Rollenpruefung", len(mit_rollen) >= 20,
          f"{len(mit_rollen)}")

    # Serverbezogen = holt sich eine guildId. Gemessen, nicht als
    # Namensliste gepflegt: eine Liste waere beim naechsten neuen
    # Bereich still veraltet.
    serverbezogen = [(n, t) for n, t in mit_rollen if "const guildId =" in t]

    # `servers` ist die Flotten-Uebersicht: guildId optional, und der
    # Bereich prueft die Discord-Rechte bereits selbst.
    ohne = [
        n for n, t in serverbezogen
        if n != "servers" and "managesGuildOnDiscord" not in t
    ]
    check("jeder serverbezogene Bereich laesst Discord-Verwalter durch",
          not ohne, ", ".join(ohne))

    flotte = dict(mit_rollen).get("servers", "")
    check("die Flotten-Uebersicht prueft Discord selbst",
          re.search(r"if \(guildId\) \{[\s\S]{0,200}verifyGuildAccess", flotte)
          is not None,
          "sonst waere sie doch eine Luecke")

    # Die Reihenfolge entscheidet: steht die Discord-Pruefung hinter
    # der Rollenpruefung, kommt sie nie zum Zug.
    # Gemessen wird der SERVERBEZOGENE Teil des Blocks.
    #
    # Manche Bereiche haben davor noch einen globalen Zweig, der gar
    # keine Server-ID kennt -- `antinuke` etwa die Liste der
    # vertrauten Bots, die fuer alle Server gilt. Der prueft
    # zwangslaeufig nur eine Rolle, und ein Vergleich ueber den
    # ganzen Block meldete deshalb einen Fehler, den es nicht gibt:
    # nachgemessen steht `managesGuildOnDiscord` im Server-Teil
    # weiterhin vor `hasTeamPermission`.
    #
    # Der Schnitt liegt dort, wo die Server-ID gelesen wird -- ab da
    # geht es um einen bestimmten Server.
    falsch = []
    for name, text in mit_rollen:
        schnitt = text.find("const guildId =")
        teil = text[schnitt:] if schnitt != -1 else text
        d = teil.find("managesGuildOnDiscord")
        r = teil.find("hasTeamPermission")
        if d != -1 and r != -1 and d > r:
            falsch.append(name)
    check("und zwar VOR der Rollenpruefung", not falsch, ", ".join(falsch))

    # Immer mit der guildId des Bereichs -- ohne Argument waere die
    # Frage sinnlos.
    ohne_id = [
        n for n, t in mit_rollen
        if "managesGuildOnDiscord" in t
        and "managesGuildOnDiscord(guildId)" not in t
    ]
    check("immer mit der guildId aufgerufen", not ohne_id, ", ".join(ohne_id))


def test_hilfsfunktion():
    print("\nDie Pruefung selbst")

    lib = strip_ts(read_dash("lib", "guild-auth.ts"))
    check("managesGuildOnDiscord gibt es",
          "export async function managesGuildOnDiscord" in lib)
    check("sie fragt wirklich Discord",
          "fetchUserGuilds" in lib and "hasManagePermission(guild)" in lib,
          "sonst prueft sie etwas anderes als sie behauptet")

    # Und zwar IN ihrem eigenen Rumpf. `hasManagePermission` kommt in
    # der Datei noch an einer zweiten Stelle vor (`verifyGuildAccess`),
    # also faellt es nicht auf, wenn es hier verschwindet: im
    # Mutationstest blieb genau das gruen. Ohne den Aufruf wuerde
    # jedes blosse Mitglied eines Servers als „Verwalter“ gelten.
    rumpf = lib.split("export async function managesGuildOnDiscord", 1)[1]
    rumpf = rumpf.split("\nexport ", 1)[0]
    check("und zwar in ihrem eigenen Rumpf",
          "hasManagePermission(guild)" in rumpf,
          "sonst zaehlt blosse Mitgliedschaft als Verwaltungsrecht")
    check("sie holt die Serverliste selbst",
          "fetchUserGuilds(session.accessToken)" in rumpf)

    # Im Zweifel NEIN. Ein Ausfall der Discord-API darf niemandem
    # Rechte geben, die er nicht hat.
    koerper = lib.split("export async function managesGuildOnDiscord", 1)[1]
    koerper = koerper.split("\nexport ", 1)[0]
    check("ohne Sitzung: nein", "return false" in koerper)
    check("bei einem Fehler: nein",
          re.search(r"catch\s*\{\s*return false;\s*\}", koerper) is not None,
          "ein Discord-Ausfall waere sonst ein Freifahrtschein")
    check("eine ungueltige ID: nein",
          r"/^\d{17,20}$/" in koerper)

    proxy = strip_ts(read_dash(PROXY))
    check("der Proxy importiert sie",
          re.search(r"import \{[^}]*managesGuildOnDiscord", proxy, re.S)
          is not None)


# ══════════════════════════════════════════════════════════════════════
#  2. Jede Rolle sieht etwas Sinnvolles
# ══════════════════════════════════════════════════════════════════════


def tab_rechte() -> tuple[list[str], dict[str, str]]:
    src = read_dash("components", "dashboard", "admin-content.tsx")
    block = re.search(
        r"const TAB_PERMISSION[^=]*=\s*\{(.*?)\n  \};", src, re.S
    )
    zuordnung = dict(re.findall(r'^\s*(\w+):\s*"([^"]+)"', block.group(1), re.M))
    reiter = list(dict.fromkeys(re.findall(r'\{ id: "(\w+)"', src)))
    return reiter, zuordnung


def test_jede_rolle_sieht_etwas():
    print("\nJede der 41 Rollen sieht mindestens einen Reiter")

    reiter, zuordnung = tab_rechte()
    check("die Reiter wurden gefunden", len(reiter) >= 20, f"{len(reiter)}")
    check("es gibt 41 Rollen", len(dr.ROLES) == 41, f"{len(dr.ROLES)}")

    # `access` und `templates` sind fuer alle Rollen gesperrt -- das
    # steht so im Quelltext und ist Absicht.
    gesperrt = {"access", "templates"}

    leer = []
    for rolle in dr.ROLES:
        rechte = set(rolle.permissions)
        if rolle.key == "tester":
            continue  # sieht bewusst genau einen
        sichtbar = [
            t for t in reiter
            if t not in gesperrt
            and (t not in zuordnung or zuordnung[t] in rechte)
        ]
        if not sichtbar:
            leer.append(rolle.key)
    check("keine Rolle steht vor einer leeren Leiste", not leer,
          ", ".join(leer))

    # Der Tester sieht genau seinen Reiter.
    src = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))
    check("der Tester sieht nur seinen Reiter",
          'tabs.filter((tab) => tab.id === "tester")' in src)


def test_kein_reiter_ohne_recht():
    print("\nKein Reiter ohne hinterlegtes Recht")

    reiter, zuordnung = tab_rechte()

    # Ein Reiter ohne Eintrag wird JEDEM gezeigt -- auch dem
    # Trial-Moderator. Beim Klick kommt dann die Fehlermeldung des
    # Proxys. Genau so war es bei „Nutzer suchen“: 41 von 41 Rollen
    # sahen den Reiter, der Proxy verlangt dort team.view.
    gesperrt = {"access", "templates"}
    ohne = [t for t in reiter if t not in zuordnung and t not in gesperrt]
    check("jeder Reiter hat ein Recht", not ohne, ", ".join(ohne))

    # Die drei, die neu dazugekommen sind -- namentlich, weil sie der
    # Anlass waren.
    for tab, recht in (("userlookup", "team.view"),
                       ("premium", "premium.manage"),
                       ("speedrun", "server.manage")):
        check(f"{tab} verlangt {recht}", zuordnung.get(tab) == recht,
              f"steht auf {zuordnung.get(tab)!r}")

    # Und die Rechte muessen es wirklich geben.
    erfunden = [
        f"{t}={r}" for t, r in zuordnung.items()
        if r not in dr.PERMISSIONS_BY_KEY
    ]
    check("kein erfundenes Recht", not erfunden, ", ".join(erfunden))


def test_nutzer_suchen_ist_eng():
    print("\n»Nutzer suchen« ist nicht mehr fuer jeden")

    _, zuordnung = tab_rechte()
    recht = zuordnung.get("userlookup")
    duerfen = [r.key for r in dr.ROLES if recht in r.permissions]

    # Der Reiter kann jeden Nutzer auf ALLEN Servern des Bots bannen.
    # Vorher sahen ihn alle 41 Rollen, auch der Trial-Moderator.
    check("nur wenige Rollen sehen ihn", 0 < len(duerfen) <= 12,
          f"{len(duerfen)} von {len(dr.ROLES)}")
    check("ein Trial-Moderator nicht", "trial_moderator" not in duerfen)
    check("ein Tester auch nicht", "tester" not in duerfen)
    check("der Co-Owner schon", "co_owner" in duerfen)


# ══════════════════════════════════════════════════════════════════════
#  3. Ohne Rolle: nichts sehen
# ══════════════════════════════════════════════════════════════════════


def test_aktionen_nach_rechten():
    """Auch die Karten INNERHALB eines Reiters muessen passen.

    Im Browser aufgefallen: ein Trial-Moderator, der nur verwarnen
    darf, sah „Kicken“ und „Bannen“. Der Reiter war richtig gefiltert,
    die Karten darin nicht -- beim Klick kam 403.
    """
    print("\nAktionen richten sich nach den Rechten")

    src = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))

    check("es gibt eine Zuordnung Aktion -> Recht", "const AKTION_RECHT" in src)
    check("und eine Funktion, die sie benutzt", "function rechtFuer(" in src)
    check("die Sammelregel fuer Scans ist dabei",
          'action.startsWith("scan_")' in src and '"security.scan"' in src,
          "sonst faellt jede Scan-Aktion durch")

    # Die Filterung muss auch wirken -- nicht nur dastehen.
    check("die Mitglieder-Karten werden gefiltert",
          "const sichtbareMemberActions" in src
          and "memberActions.filter((card) => darf(card.action))" in src)
    check("und auch gerendert",
          "{sichtbareMemberActions.map((card) =>" in src,
          "sonst filtert die Liste ins Leere")
    check("die Schnellaktionen ebenso",
          "action.tab === activeTab && darf(action.action)" in src)

    # Ohne geladene Rechte: nichts. Sonst blitzt die volle Liste auf.
    check("ohne Rechte wird keine Aktion gezeigt",
          "if (!access) return false;" in src)

    # Faellt die gewaehlte Aktion weg, muss eine erlaubte nachruecken.
    check("die gewaehlte Aktion rueckt nach",
          "setMemberAction(sichtbareMemberActions[0].action)" in src,
          "sonst steht auf dem Knopf »Bannen ausfuehren« ohne Karte")
    check("und ohne jede Aktion steht dort ein Satz",
          "Deine Rolle erlaubt hier keine Aktion." in src)

    # Die Rechte muessen dieselben sein, die der Proxy prueft. Zwei
    # Listen, die dasselbe bedeuten, laufen sonst auseinander.
    proxy = strip_ts(read_dash(PROXY))
    for aktion, recht in (("ban", "moderation.ban"),
                          ("kick", "moderation.kick"),
                          ("purge", "moderation.purge"),
                          ("server_name", "server.manage")):
        im_panel = re.search(rf"^\s*{aktion}: \"{re.escape(recht)}\",", src, re.M)
        im_proxy = re.search(rf"^\s*{aktion}: \"{re.escape(recht)}\",", proxy, re.M)
        check(f"{aktion} verlangt beidseitig {recht}",
              bool(im_panel) and bool(im_proxy),
              f"panel={bool(im_panel)} proxy={bool(im_proxy)}")

    # Und kein erfundenes Recht.
    block = re.search(r"const AKTION_RECHT[^=]*=\s*\{(.*?)\n\};", src, re.S)
    erfunden = [
        f"{k}={v}" for k, v in re.findall(r'(\w+): "([^"]+)"', block.group(1))
        if v not in dr.PERMISSIONS_BY_KEY
    ]
    check("kein erfundenes Recht bei den Aktionen", not erfunden,
          ", ".join(erfunden))


def test_zahlen_stuerzen_nicht_ab():
    """Ein fehlendes Feld darf nicht die ganze Seite killen.

    Im Browser gesehen: „Application error: a client-side exception
    has occurred“ -- eine weisse Seite statt des Dashboards, weil
    `undefined.toLocaleString()` geworfen hat. Das passiert, sobald
    der Bot eine unvollstaendige Statistik liefert.
    """
    print("\nEine unvollstaendige Antwort kippt die Seite nicht")

    src = strip_ts(read_dash("components", "dashboard", "command-stats-panel.tsx"))

    check("num() vertraegt ein fehlendes Feld",
          "function num(value: number | null | undefined)" in src
          and "(value ?? 0).toLocaleString" in src,
          "sonst: weisse Seite statt Dashboard")

    # Die Listen ebenso -- `.length` auf undefined wirft genauso.
    for stelle in ("data.daily?.length", "(data.daily ?? [])",
                   "data.guilds?.length", "(data.guilds ?? [])",
                   "data.unused?.length", "(data.unused ?? [])"):
        check(f"abgesichert: {stelle}", stelle in src)

    # Und kein ungeschuetzter Zugriff mehr.
    ungeschuetzt = re.findall(r"data\.(daily|guilds|unused)\.(length|map|slice)", src)
    check("kein ungeschuetzter Listenzugriff", not ungeschuetzt,
          f"{ungeschuetzt[:3]}")


def test_ohne_rolle_kein_zugang():
    print("\nOhne Dashboard-Rolle: kein Link, keine Reiter, keine Seite")

    # (1) Der Link in der Seitenleiste.
    layout = strip_ts(read_dash("app", "dashboard", "layout.tsx"))
    check("der Admin-Link haengt an der Rolle",
          "isAdmin(session?.user?.id) || hasTeamRole" in layout)
    check("und hasTeamRole faellt im Fehlerfall auf false",
          "setHasTeamRole(false)" in layout,
          "sonst bliebe der Link nach einem Fehler stehen")

    # (2) Die Seite selbst.
    #
    # Es sind ZWEI Weiterleitungen, und beide werden gebraucht: die
    # erste fuer Leute ohne Sitzung, die zweite fuer Angemeldete ohne
    # Rolle. Nur nach dem Vorkommen zu suchen, deckt die zweite nicht
    # ab -- im Mutationstest blieb der Test gruen, obwohl die
    # Rollenpruefung ins Leere lief.
    seite = strip_ts(read_dash("app", "dashboard", "admin", "page.tsx"))
    check("die Seite hat beide Weiterleitungen",
          seite.count('redirect("/dashboard")') == 2,
          f"nur {seite.count(chr(39))and seite.count('redirect(\"/dashboard\")')}")
    check("die Rollenpruefung ist da",
          "access.roles.length > 0" in seite)

    # Die zweite Weiterleitung muss INNERHALB der Rollenpruefung
    # stehen, sonst leitet sie entweder jeden oder niemanden weiter.
    rollen_zweig = seite.split("const hasRole", 1)[-1]
    check("und leitet ohne Rolle wirklich weg",
          "if (!hasRole)" in rollen_zweig
          and 'redirect("/dashboard")' in rollen_zweig,
          "die Pruefung liefe sonst ins Leere")

    # (3) Die Reiter.
    src = strip_ts(read_dash("components", "dashboard", "admin-content.tsx"))
    check("ohne geladene Rechte wird nichts gezeigt",
          "if (!access) return [];" in src,
          "vorher stand hier `return tabs` -- also alles")
    check("und ohne Rolle ebenfalls nichts",
          "(access.roles?.length ?? 0) === 0) return [];" in src)

    # (4) Und statt einer leeren Flaeche ein Satz.
    check("es gibt einen Hinweis statt einer leeren Seite",
          "Für den Admin-Bereich fehlt dir eine Rolle." in src)
    check("und einen Zwischenzustand beim Laden",
          "Berechtigungen werden geprüft" in src)


# ══════════════════════════════════════════════════════════════════════
#  4. Die 404-Seite
# ══════════════════════════════════════════════════════════════════════


def test_404():
    print("\nDie 404-Seite")

    src = read_dash("app", "not-found.tsx")
    roh = strip_ts(src)

    # Sie war komplett auf Englisch.
    for satz in ("This page does not exist", "Back to the dashboard",
                 "Page not found", "Your servers", "Ask us on Discord"):
        check(f"kein »{satz[:26]}«", satz not in roh)

    check("die Ueberschrift ist deutsch",
          "Diese Seite gibt es nicht" in roh)
    check("und der Titel im Reiter auch",
          "Seite nicht gefunden" in src)

    # Sie hatte einen eigenen Hintergrund und eigene Blautoene.
    check("kein eigener Hintergrund mehr", "#070c18" not in roh,
          "der Rest der Seite steht auf #0a0a0c")
    check("die Seitenfarbe stimmt", "bg-[#0a0a0c]" in roh)
    check("der Akzent ist der der Seite", "#5865f2" in roh)
    for alt in ("from-blue-400", "text-blue-400", "bg-blue-500"):
        check(f"kein {alt}", alt not in roh)

    # Die Riesenzahl war das Lauteste auf dem Schirm.
    check("die 404 schreit nicht mehr",
          "18vw" not in roh and "clamp(5rem" not in roh,
          "die Zahl ist die unwichtigste Angabe auf dieser Seite")

    # Sie muss einen Weg hinaus anbieten -- und zwar den richtigen.
    check("Serverliste steht zuerst",
          roh.index("/dashboard/guilds") < roh.index('"/dashboard"'),
          "der haeufigste Grund ist ein toter Server-Link")
    check("es gibt einen Weg zurueck", 'href="/dashboard"' in roh)
    check("und zur Startseite", 'href="/"' in roh)
    check("Support ist verlinkt", "SUPPORT_INVITE" in roh)

    # Und sie sagt, warum man hier ist.
    check("sie nennt die Gruende",
          "Der Bot ist nicht mehr auf dem Server" in roh)


def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_rolle_ersetzt_nicht()
    test_hilfsfunktion()
    test_jede_rolle_sieht_etwas()
    test_kein_reiter_ohne_recht()
    test_nutzer_suchen_ist_eng()
    test_aktionen_nach_rechten()
    test_zahlen_stuerzen_nicht_ab()
    test_ohne_rolle_kein_zugang()
    test_404()

    print("\n" + "=" * 64)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Rollen ergaenzen, sie ersetzen nicht.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
