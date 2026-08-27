#!/usr/bin/env python3
"""
Die 7-Tage-Probewoche.

Woher sie kommt
---------------
Der Template-Bot (Branch ``arena/019ffd1a``) vergibt persoenliche Keys,
die genau sieben Tage gelten, und meldet das hierher:

    POST /api/v1/premium/grant
    X-Partner-Token: <PREMIUM_PARTNER_TOKEN>
    {user_id, guild_id, expires_at, duration_days}

Ohne diese Meldung wuesste der University Bot nichts davon -- er kennt
nur seine eigenen verkauften Keys, und im Dashboard stuende „kein
Premium", obwohl der Nutzer welches hat.

Die Regeln, die hier festgehalten werden
----------------------------------------
  1. **Eine Probewoche pro Konto, fuer immer.** Deshalb bleibt die
     Zeile beim Ablauf stehen: sie ist der Beleg. Wuerde sie geloescht,
     koennte sich jeder nach sieben Tagen eine neue holen.
  2. **Zuruecksetzen ist nicht Beenden.** Beenden stoppt die laufende
     Woche, der Eintrag bleibt. Zuruecksetzen gibt den Weg frei -- fuer
     Support-Faelle, absichtlich und nachvollziehbar.
  3. **Die Ablauf-DM geht genau einmal raus.** Auch wenn sie nicht
     zugestellt werden kann: sonst laeuft der Zustellversuch alle zehn
     Minuten erneut.
  4. **`status()` zaehlt die Probewoche mit**, aber verkuerzt nie eine
     laengere bezahlte Lizenz.
  5. **`/premium/grant` ist nicht ueber den Browser erreichbar.** Sonst
     schreibt sich jeder per Klick eine Probewoche auf ein fremdes
     Konto.

Run:  python3 tests/test_premium_trial.py
"""

import ast
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
DASH = os.path.join(BOT, "..", "dashboard")
sys.path.insert(0, BOT)

from utils import premium_trial as trial  # noqa: E402

failures: list[str] = []

USER = "1303627964734246944"
USER2 = "1033826242270609449"
GUILD = "1530378233579704370"


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(*teile) -> str:
    with open(os.path.join(BOT, *teile), encoding="utf-8") as f:
        return f.read()


def read_dash(*teile) -> str:
    with open(os.path.join(DASH, *teile), encoding="utf-8") as f:
        return f.read()


def strip_ts(src: str) -> str:
    # Reihenfolge: erst die Zeilenkommentare, dann die Bloecke. Ein
    # Pfad mit Sternchen in einem //-Kommentar eroeffnet sonst einen
    # Schein-Block, der den halben Quelltext verschluckt.
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


def strip_py(src: str) -> str:
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        baum = ast.parse(src)
    except SyntaxError:
        return src
    for knoten in ast.walk(baum):
        if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef,
                               ast.ClassDef, ast.Module)):
            doc = ast.get_docstring(knoten, clean=False)
            if doc:
                src = src.replace(doc, "")
    return src


def frische_db():
    trial.DB_PATH = os.path.join(tempfile.mkdtemp(), "premium_trial.db")


# ══════════════════════════════════════════════════════════════════════
#  Verhalten -- echtes SQLite
# ══════════════════════════════════════════════════════════════════════


def test_eine_pro_konto():
    print("\nEine Probewoche pro Konto")
    frische_db()

    check("vorher hatte niemand eine", trial.had_trial(USER) is False)

    jetzt = int(time.time())
    erste = trial.grant(USER, guild_id=GUILD,
                        expires_at=jetzt + 7 * 86400, duration_days=7)
    check("die erste wird angenommen", erste["ok"] is True)
    check("und laeuft", trial.is_active(USER) is True)

    zweite = trial.grant(USER, guild_id=GUILD, duration_days=7)
    check("die zweite nicht", zweite["ok"] is False)
    check("mit Begruendung", zweite.get("error") == "already_used")
    check(
        "und das Datum bleibt unangetastet",
        trial.get(USER)["expires_at"] == jetzt + 7 * 86400,
        "sonst haette sich der Nutzer heimlich verlaengert",
    )


def test_abgelaufen_bleibt_verbraucht():
    print("\nAbgelaufen heisst verbraucht, nicht vergessen")
    frische_db()

    trial.grant(USER, expires_at=int(time.time()) - 10, duration_days=7)
    check("nicht mehr aktiv", trial.is_active(USER) is False)
    check(
        "der Eintrag bleibt",
        trial.had_trial(USER) is True,
        "sonst holt sich jeder nach sieben Tagen eine neue",
    )
    check("und es gibt keine neue", trial.grant(USER)["ok"] is False)


def test_beenden_und_zuruecksetzen():
    print("\nBeenden ist nicht Zuruecksetzen")
    frische_db()

    trial.grant(USER, duration_days=7)

    check("Beenden meldet Erfolg", trial.revoke(USER) is True)
    check("die Woche ist vorbei", trial.is_active(USER) is False)
    check(
        "aber verbraucht",
        trial.had_trial(USER) is True,
        "Beenden darf den Weg NICHT freigeben",
    )
    check("also keine neue", trial.grant(USER)["ok"] is False)

    check("Zuruecksetzen meldet Erfolg", trial.reset(USER, actor="fufi") is True)
    check("jetzt ist der Weg frei", trial.had_trial(USER) is False)
    check("und eine neue geht", trial.grant(USER, duration_days=7)["ok"] is True)

    check(
        "Zuruecksetzen ohne Eintrag meldet False",
        trial.reset("999999999999999999") is False,
    )
    check(
        "Beenden ohne Eintrag ebenso",
        trial.revoke("999999999999999999") is False,
    )


def test_dm_genau_einmal():
    print("\nDie Ablauf-Nachricht geht genau einmal raus")
    frische_db()

    trial.grant(USER, expires_at=int(time.time()) - 10, duration_days=7)
    trial.grant(USER2, duration_days=7)  # laeuft noch

    faellig = [e["user_id"] for e in trial.due_for_expiry_dm()]
    check("der Abgelaufene ist faellig", USER in faellig, str(faellig))
    check("der Laufende nicht", USER2 not in faellig)

    trial.mark_dm_sent(USER)
    check(
        "danach nicht mehr",
        USER not in [e["user_id"] for e in trial.due_for_expiry_dm()],
        "sonst kommt sie alle zehn Minuten erneut",
    )


def test_neue_spalte():
    print("\nEine neue Spalte wird nachgeruestet")
    import sqlite3

    ordner = tempfile.mkdtemp()
    pfad = os.path.join(ordner, "alt.db")
    conn = sqlite3.connect(pfad)
    conn.execute(
        "CREATE TABLE premium_trials (user_id TEXT PRIMARY KEY, guild_id TEXT,"
        " product TEXT, granted_at INTEGER, expires_at INTEGER)"
    )
    conn.execute(
        "INSERT INTO premium_trials VALUES (?, NULL, 'template_bot', 1, 2)",
        (USER,),
    )
    conn.commit()
    conn.close()

    trial.DB_PATH = pfad
    fehler = ""
    try:
        trial.get(USER)
    except Exception as exc:
        fehler = str(exc)
    check("kein 'no such column'", not fehler, fehler)

    spalten = {
        z[1] for z in sqlite3.connect(pfad).execute("PRAGMA table_info(premium_trials)")
    }
    for name in ("times_granted", "expiry_dm_sent", "reset_by", "duration_days"):
        check(f"{name} wurde ergaenzt", name in spalten, str(sorted(spalten)))

    quelle = strip_py(read("utils", "premium_trial.py"))
    check(
        "das Schema leitet sich aus COLUMNS ab",
        "for name, typ in COLUMNS" in quelle,
        "zwei handgepflegte Listen laufen auseinander",
    )


def test_status_zaehlt_mit():
    print("\nDie Probewoche zaehlt als Premium")
    frische_db()

    from utils import premium_store

    # premium_store hat eine eigene Datei; nur die Probewoche wird hier
    # gesetzt, Keys gibt es keine.
    premium_store.DB_PATH = os.path.join(tempfile.mkdtemp(), "premium.db")

    vorher = premium_store.status(USER)
    check("ohne alles: kein Premium", vorher["premium"] is False)
    check("und keine Probewoche", vorher.get("via_trial") is False)

    trial.grant(USER, expires_at=int(time.time()) + 7 * 86400, duration_days=7)
    nachher = premium_store.status(USER)
    check("mit Probewoche: Premium", nachher["premium"] is True)
    check("und als solche erkennbar", nachher["via_trial"] is True,
          "sonst steht im Dashboard 'Premium' statt '7 Tage kostenlos'")
    check("mit Ablaufdatum", bool(nachher["expires_at"]))
    check("und sieben Tagen", nachher["duration_days"] == 7,
          str(nachher["duration_days"]))
    check("nicht als Lifetime", nachher["lifetime"] is False)

    # Nach Ablauf faellt sie weg.
    trial.revoke(USER)
    check("abgelaufen: kein Premium mehr", premium_store.status(USER)["premium"] is False)


# ══════════════════════════════════════════════════════════════════════
#  Die Schnittstelle
# ══════════════════════════════════════════════════════════════════════


def test_route():
    print("\nDie Route, die der Template-Bot ruft")

    src = strip_py(read("api", "routes", "premium.py"))
    check("es gibt /grant", '@router.post("/grant"' in src)

    # Das Token muss IN der grant-Funktion geprueft werden, nicht
    # irgendwo in der Datei: `_require_partner_token` steht auch in
    # `check`. Wird die Zeile aus `grant` entfernt, faellt das an einer
    # Dateisuche nicht auf -- im Mutationstest genau so durchgerutscht.
    # Ohne sie koennte jeder ohne Token Probewochen verteilen.
    rumpf = ""
    if 'async def grant_trial' in src:
        rumpf = src.split("async def grant_trial", 1)[1]
        rumpf = rumpf.split("\n@router", 1)[0]
    check("sie verlangt das Partner-Token",
          "_require_partner_token(x_partner_token)" in rumpf,
          "in der grant-Funktion selbst, nicht irgendwo in der Datei")
    check("und zwar VOR dem Eintragen",
          rumpf.find("_require_partner_token") < rumpf.find("premium_trial.grant("),
          "danach waere die Probewoche schon geschrieben")
    check("und meldet eine verbrauchte Probewoche zurueck",
          '"status": "already_used"' in src and '"granted": False' in src,
          "der Template-Bot entscheidet daran, was er dem Nutzer sagt")
    check("die Verwaltung gibt es auch",
          '@router.get("/trials"' in src
          and '@router.post("/trials/reset"' in src
          and '@router.post("/trials/revoke"' in src)


def test_proxy():
    print("\nDer Proxy")

    proxy = strip_ts(read_dash("app", "api", "bot", "[...path]", "route.ts"))

    # grant gehoert dem Template-Bot. Ueber den Browser erreichbar
    # waere sie ein Weg, sich selbst eine Probewoche zu schreiben.
    check("grant ist im Browser gesperrt",
          'rest[0] === "grant"' in proxy
          and "Not available through the dashboard" in proxy)

    # Die Verwaltung ist Teamsache -- „zuruecksetzen" verschenkt Tage.
    check("trials verlangt eine Team-Rolle",
          '"trials"' in proxy and '"keys", "revoke", "delete", "purge", "trials"' in proxy)

    api_ts = strip_ts(read_dash("lib", "api.ts"))
    for name in ("listPremiumTrials", "resetPremiumTrial", "revokePremiumTrial"):
        check(f"{name} ist verdrahtet", f"{name}:" in api_ts)


def test_oberflaeche():
    print("\nDie Oberflaeche")

    # Der Nutzer sieht, dass es eine Probewoche ist.
    panel = strip_ts(read_dash("components", "dashboard", "premium-panel.tsx"))
    check("das Nutzer-Panel kennt die Probewoche",
          "zustand?.via_trial" in panel,
          "frueher hiess das Feld template?.via_trial -- es gibt nur "
          "noch ein Produkt")
    # Das Panel muss den NEUEN Schluessel bevorzugen.
    #
    # Ohne diese Pruefung bliebe der Test gruen, wenn jemand wieder
    # `status?.template_bot` allein liest: `via_trial` stuende dann
    # immer noch in der Datei. Der Mutationstest hat genau das
    # durchgelassen.
    check("und liest den neuen Schluessel zuerst",
          "status?.premium ?? status?.template_bot" in panel,
          "sonst haengt die Anzeige wieder am alten Produkt")
    check("und schreibt es hin",
          "Tage Premium – kostenlos" in panel,
          "'Premium ist aktiv' liest sich wie etwas Bezahltes")
    check("es sagt auch, dass sie endet",
          "nur einmal pro Konto" in panel)

    # Der Admin-Bereich.
    admin = strip_ts(read_dash("components", "dashboard", "premium-trials.tsx"))
    check("es gibt den Baustein", "export function PremiumTrials" in admin)
    check("er laedt die Liste", "listPremiumTrials" in admin)
    check("beenden geht", "revokePremiumTrial" in admin)
    check("zuruecksetzen auch", "resetPremiumTrial" in admin)
    check(
        "der Unterschied steht auf dem Bildschirm",
        "Beenden" in admin and "Zurücksetzen" in admin
        and "verbraucht" in admin,
        "zwei Knoepfe, deren Unterschied man nicht sieht, sind eine Falle",
    )

    eingebaut = strip_ts(read_dash("components", "dashboard", "premium-admin.tsx"))
    check("und ist im Premium-Reiter eingebaut",
          re.search(r"<PremiumTrials\b", eingebaut) is not None
          and "premium-trials" in eingebaut)


def test_dm_cog():
    print("\nDie Nachricht bei Ablauf")

    cog = strip_py(read("cogs", "commands", "premium.py"))
    check("der Lauf ruft sie auf", "_notify_expired_trials()" in cog)
    check("sie holt die faelligen", "due_for_expiry_dm()" in cog)
    check("und merkt sich den Versand", "mark_dm_sent(" in cog)
    # Der Riegel muss AUSSERHALB der `if nutzer is not None`-Bedingung
    # stehen. Steht er darin, bleibt ein Konto, das der Bot gar nicht
    # findet, ewig in der Warteschlange und loest alle zehn Minuten
    # einen Zustellversuch aus. Eine blosse Reihenfolgen-Pruefung
    # bemerkt das nicht -- im Mutationstest durchgerutscht.
    zeilen = [z for z in cog.split("\n") if "mark_dm_sent(" in z and "def " not in z]
    check("der Riegel wird gesetzt", bool(zeilen), "kein Aufruf gefunden")
    if zeilen:
        einzug = len(zeilen[0]) - len(zeilen[0].lstrip())
        check(
            "auch nach einem Fehlschlag",
            einzug <= 12,
            f"Einzug {einzug}: steht in einer Bedingung statt in der Schleife",
        )
    check("die Nachricht nennt die Verlaengerung",
          "Verlaengern kannst du hier" in cog)
    # content= neben einer LayoutView ist Discord-Fehler 50035.
    check("kein content= neben der Karte",
          "content=" not in cog.split("_trial_over_card")[-1][:900])


def main() -> int:
    check("das Dashboard-Verzeichnis wurde gefunden", os.path.isdir(DASH), DASH)
    if not os.path.isdir(DASH):
        return 1

    test_eine_pro_konto()
    test_abgelaufen_bleibt_verbraucht()
    test_beenden_und_zuruecksetzen()
    test_dm_genau_einmal()
    test_neue_spalte()
    test_status_zaehlt_mit()
    test_route()
    test_proxy()
    test_oberflaeche()
    test_dm_cog()

    print("\n" + "=" * 64)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Die Probewoche steht.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
