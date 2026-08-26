#!/usr/bin/env python3
"""
Die Beta-Routen echt ueber HTTP.

Schwerpunkte:
  * ein Antrag pro Konto, abgelehnte duerfen erneut
  * Annahme vergibt Premium und schickt eine DM
  * Entzug nimmt Premium UND setzt den Antrag zurueck
  * das goldene Fenster kommt genau einmal -- und nach einem Entzug
    mit Neuvergabe wieder, dann als Rueckkehr

Run:   python3 tests/test_beta.py
"""

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
START = os.getcwd()
sys.path.insert(0, BOT)
os.environ.setdefault("PREMIUM_KEY_PEPPER", "test-pepper")
os.chdir(tempfile.mkdtemp(prefix="beta-"))
os.makedirs("db", exist_ok=True)

fehler = []
USER = "1303627964734246944"
USER2 = "1033826242270609449"


def pruefe(name, ok, hinweis=""):
    if ok:
        print(f"  OK   {name}")
    else:
        print(f"  FAIL {name}" + (f" -- {hinweis}" if hinweis else ""))
        fehler.append(name)


def linie(t):
    print()
    print("=" * 66)
    print(t)
    print("=" * 66)


class FakeUser:
    def __init__(self, uid, offen=True):
        self.id = uid
        self.offen = offen
        self.nachrichten = []

    async def send(self, **kw):
        import discord
        if not self.offen:
            raise discord.Forbidden(_Antwort(), "zu")
        self.nachrichten.append(kw)


class _Antwort:
    status = 403
    reason = "Forbidden"


def baue_app(users):
    from fastapi import FastAPI

    from api.dependencies import get_bot
    from api.routes import beta

    class FakeBot:
        def get_user(self, uid):
            return users.get(str(uid))

        async def fetch_user(self, uid):
            return users.get(str(uid))

    app = FastAPI()
    app.include_router(beta.router, prefix="/beta")
    app.dependency_overrides[get_bot] = lambda: FakeBot()
    return app


def main():
    from fastapi.testclient import TestClient

    from utils import beta_applications as store
    from utils import premium_store

    users = {USER: FakeUser(USER), USER2: FakeUser(USER2, offen=False)}
    client = TestClient(baue_app(users))

    linie("1  Das Formular")
    r = client.get(f"/beta/form?user_id={USER}&user_name=Fufi&avatar=http://a/b.png")
    pruefe("GET /form geht", r.status_code == 200, r.text[:150])
    d = r.json()
    pruefe("es gibt fuenf Fragen", len(d["questions"]) == 5,
           str(len(d["questions"])))
    pruefe("die erste ist das Discord-Konto",
           d["questions"][0]["key"] == "discord")
    pruefe("und sie ist nicht ausfuellbar",
           d["questions"][0]["readonly"] is True,
           "der Nutzer soll dort nichts eintragen koennen")
    pruefe("die anderen vier sind ausfuellbar",
           all(not q["readonly"] for q in d["questions"][1:]))
    pruefe("das Konto kommt mit", d["user"]["id"] == USER)
    pruefe("noch kein Antrag", d["application"] is None)
    pruefe("bewerben ist moeglich", d["can_apply"] is True)

    linie("2  Antrag stellen")
    gute = {
        "warum": "Ich betreue einen grossen Server und moechte helfen zu testen.",
        "gut": "Das Ticket-System und der Anti-Nuke laufen sehr zuverlaessig.",
        "besser": "Die Musik koennte stabiler sein und mehr Quellen kennen.",
        "schluss": "Danke fuer die Arbeit am Bot.",
    }
    r = client.post("/beta/apply",
                    json={"user_id": USER, "user_name": "Fufi", **gute})
    pruefe("Antrag geht durch", r.status_code == 200, r.text[:200])
    antrag_id = r.json()["application"]["id"]

    r = client.post("/beta/apply",
                    json={"user_id": USER, "user_name": "Fufi", **gute})
    pruefe("ein zweiter offener Antrag wird abgelehnt", r.status_code == 400,
           str(r.status_code))

    r = client.post("/beta/apply", json={"user_name": "X", **gute})
    pruefe("ohne Anmeldung geht nichts", r.status_code == 401, str(r.status_code))

    kurz = dict(gute, warum="zu kurz")
    r = client.post("/beta/apply", json={"user_id": USER2, **kurz})
    pruefe("zu kurze Antworten werden abgelehnt", r.status_code == 400,
           r.text[:150])

    linie("3  Das Fenster: noch kein Premium")
    r = client.get(f"/beta/notice?user_id={USER}")
    pruefe("ohne Premium kein Fenster", r.json()["zeigen"] is False, r.text[:120])

    linie("4  Annehmen")
    r = client.post("/beta/admin/decide",
                    json={"id": antrag_id, "accept": True, "actor": "admin"})
    pruefe("Annahme geht", r.status_code == 200, r.text[:200])
    pruefe("die DM kam an", r.json()["dm"] == "sent", r.json().get("dm"))
    pruefe("der Nutzer hat jetzt Premium",
           premium_store.status(USER, product="main_bot")["premium"] is True)
    # `str(StatusCard)` zeigt nur "<StatusCard ...>", nicht den Text.
    # Also in die Komponenten schauen -- das ist ohnehin das, was
    # Discord wirklich bekommt.
    import json as _json
    roh = ""
    for n in users[USER].nachrichten:
        v = n.get("view")
        if v is not None:
            roh += _json.dumps(v.to_components())
    pruefe("die DM nennt die Beta und das Premium",
           "Beta" in roh and "Premium" in roh, roh[:200])

    linie("5  Das goldene Fenster")
    r = client.get(f"/beta/notice?user_id={USER}")
    d = r.json()
    pruefe("jetzt erscheint es", d["zeigen"] is True, str(d))
    pruefe("und zwar als Erstfassung", d["rueckkehr"] is False)

    client.post("/beta/notice/seen", json={"user_id": USER})
    r = client.get(f"/beta/notice?user_id={USER}")
    pruefe("nach dem Wegklicken nie wieder", r.json()["zeigen"] is False,
           r.text[:120])

    r = client.get(f"/beta/notice?user_id={USER}")
    pruefe("auch beim dritten Aufruf nicht", r.json()["zeigen"] is False)

    linie("6  Premium entziehen")
    r = client.post("/beta/admin/revoke",
                    json={"user_id": USER, "actor": "admin"})
    pruefe("Entzug geht", r.status_code == 200, r.text[:150])
    pruefe("Premium ist weg",
           premium_store.status(USER, product="main_bot")["premium"] is False)

    letzter = store.letzter_antrag(USER)
    pruefe("der Antrag gilt nicht mehr als angenommen",
           letzter["status"] != store.STATUS_ANGENOMMEN, str(letzter["status"]))

    r = client.get(f"/beta/notice?user_id={USER}")
    pruefe("ohne Premium kein Fenster", r.json()["zeigen"] is False)

    linie("7  Wieder aufnehmen -- Willkommen zurueck")
    r = client.post("/beta/apply",
                    json={"user_id": USER, "user_name": "Fufi", **gute})
    pruefe("nach einer Ablehnung darf man erneut", r.status_code == 200,
           r.text[:200])
    neue_id = r.json()["application"]["id"]

    client.post("/beta/admin/decide",
                json={"id": neue_id, "accept": True, "actor": "admin"})
    r = client.get(f"/beta/notice?user_id={USER}")
    d = r.json()
    pruefe("das Fenster kommt wieder", d["zeigen"] is True, str(d))
    pruefe("diesmal als Rueckkehr", d["rueckkehr"] is True,
           "sonst steht dort wieder der Erst-Text")

    linie("8  Ablehnen")
    r = client.post("/beta/apply",
                    json={"user_id": USER2, "user_name": "Vexo", **gute})
    zweite_id = r.json()["application"]["id"]

    r = client.post("/beta/admin/decide",
                    json={"id": zweite_id, "accept": False, "actor": "admin"})
    pruefe("Ablehnung ohne Grund wird verweigert", r.status_code == 400,
           "eine Ablehnung ohne Begruendung ist wertlos")

    r = client.post("/beta/admin/decide",
                    json={"id": zweite_id, "accept": False,
                          "reason": "Server zu klein.", "actor": "admin"})
    pruefe("mit Grund geht sie", r.status_code == 200, r.text[:150])
    pruefe("geschlossene DMs werden ehrlich gemeldet",
           r.json()["dm"] == "dms_closed", r.json().get("dm"))
    pruefe("kein Premium fuer Abgelehnte",
           premium_store.status(USER2, product="main_bot")["premium"] is False)

    linie("9  Die Liste")
    r = client.get("/beta/admin/list")
    d = r.json()
    pruefe("die Liste kommt", r.status_code == 200)
    pruefe("die Zahlen stimmen",
           d["counts"]["gesamt"] == len(d["applications"]),
           str(d["counts"]))
    pruefe("IDs sind Zeichenketten",
           all(isinstance(a["user_id"], str) for a in d["applications"]))

    linie("10  Das Fenster bei der allerersten Vergabe")

    # Isoliert pruefen, mit frischer Datenbank.
    #
    # Im Ablauf oben lief vorher schon ein `notice`-Aufruf ohne
    # Premium -- danach war die Zeile bekannt, und die Mutation
    # "bekannt = True" fiel nicht auf. Der Fall, auf den es ankommt,
    # ist der allererste Kontakt ueberhaupt.
    import importlib
    import tempfile as _tf

    _alt_cwd = os.getcwd()
    os.chdir(_tf.mkdtemp(prefix="notice-"))
    os.makedirs("db", exist_ok=True)
    from utils import premium_notice as _pn
    importlib.reload(_pn)

    _u = "999888777666555444"
    _erst = _pn.zustand(_u, True)
    pruefe("die allererste Vergabe zeigt das Fenster",
           _erst["zeigen"] is True, str(_erst))
    pruefe("und NICHT als Rueckkehr",
           _erst["rueckkehr"] is False,
           "sonst steht 'Willkommen zurueck' bei jemandem, der zum "
           "ersten Mal Premium bekommt")

    # Auch wenn vorher ein Aufruf ohne Premium lief und die Annahme
    # `zuruecksetzen()` aufgerufen hat -- genau dieser Ablauf hat den
    # Fehler urspruenglich erzeugt.
    _u2 = "999888777666555445"
    _pn.zustand(_u2, False)
    _pn.zuruecksetzen(_u2)
    _zweit = _pn.zustand(_u2, True)
    pruefe("auch nach zuruecksetzen() bei der Erstvergabe keine Rueckkehr",
           _zweit["rueckkehr"] is False, str(_zweit))

    # Gegenprobe: eine echte Rueckkehr muss als solche erkannt werden.
    _pn.als_gesehen(_u2)
    _pn.zustand(_u2, False)
    _pn.zuruecksetzen(_u2)
    _dritt = _pn.zustand(_u2, True)
    pruefe("eine echte Rueckkehr wird erkannt",
           _dritt["zeigen"] is True and _dritt["rueckkehr"] is True,
           str(_dritt))

    os.chdir(_alt_cwd)

    linie("11  Anbindung")

    import re

    def strip_ts(src):
        ohne = re.sub(r"(?<!:)//[^\n]*", "", src)
        return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)

    server = open(os.path.join(BOT, "api", "server.py"), encoding="utf-8").read()
    pruefe("der Router ist eingebunden", 'prefix="/beta"' in server)

    # Der Proxy MUSS die user_id aus der Sitzung setzen.
    proxy = strip_ts(open(os.path.join(DASH, "app", "api", "bot", "[...path]",
                                       "route.ts"), encoding="utf-8").read())
    pruefe("der Proxy kennt den Bereich", 'scope === "beta"' in proxy)
    pruefe("beim Schreiben kommt die user_id aus der Sitzung",
           re.search(r'segments\[0\] === "beta"\)\s*\{\s*parsed\.user_id = actorId',
                     proxy) is not None,
           "sonst stellt jeder Antraege auf fremde Konten")
    pruefe("beim Lesen ebenso",
           re.search(r'segments\[0\] === "beta" && request\.method === "GET"',
                     proxy) is not None,
           "sonst liest jeder fremde Antraege aus")
    beta_zweig = proxy[proxy.find('scope === "beta"'):]
    beta_zweig = beta_zweig[:beta_zweig.find('scope === "design"')]
    pruefe("nur Admins duerfen entscheiden",
           "isGlobalAdmin" in beta_zweig and 'rest[0] === "admin"' in beta_zweig)

    # Das Formular.
    form = os.path.join(DASH, "components", "dashboard", "beta-form.tsx")
    pruefe("das Formular gibt es", os.path.isfile(form))
    if os.path.isfile(form):
        f = strip_ts(open(form, encoding="utf-8").read())
        pruefe("die erste Frage ist nicht ausfuellbar",
               "f.readonly ?" in f,
               "das Discord-Konto darf man nicht eintippen")
        pruefe("es gibt den Abmelde-Hinweis daneben",
               "Bin ich nicht" in f and "signOut" in f)
        pruefe("die Fragen kommen vom Server",
               "daten?.questions" in f,
               "sonst gibt es zwei Listen, die auseinanderlaufen")

    # Das goldene Fenster.
    popup = os.path.join(DASH, "components", "premium-hinweis.tsx")
    pruefe("das Premium-Fenster gibt es", os.path.isfile(popup))
    if os.path.isfile(popup):
        pp = strip_ts(open(popup, encoding="utf-8").read())
        pruefe("es ist golden",
               "amber-400" in pp and "border-2" in pp)
        pruefe("der Knopf heisst wie gewuenscht",
               "Ich hab verstanden" in pp)
        pruefe("er wartet fuenf Sekunden",
               "WARTEN_SEKUNDEN = 5" in pp)
        # Auf die Wirkung zielen: der Knopf muss wirklich gesperrt sein.
        pruefe("und ist solange gesperrt",
               re.search(r"disabled=\{rest > 0\}", pp) is not None,
               "sonst laeuft nur eine Zahl herunter")
        pruefe("bei einer Rueckkehr entfaellt die Wartezeit",
               "daten.rueckkehr ? 0 : WARTEN_SEKUNDEN" in pp)
        pruefe("es meldet das Wegklicken",
               "notice/seen" in pp)

    layout = open(os.path.join(DASH, "app", "layout.tsx"), encoding="utf-8").read()
    pruefe("das Fenster ist eingebunden", "<PremiumHinweis />" in layout)

    # Premium-Tab: kein "demnaechst" mehr.
    panel = strip_ts(open(os.path.join(DASH, "components", "dashboard",
                                       "premium-panel.tsx"), encoding="utf-8").read())
    pruefe("der Premium-Tab bietet die Beta an",
           "Beta" in panel and "20" in panel)
    pruefe("und verlinkt das Formular",
           "/dashboard/premium/beta" in panel)

    seite = os.path.join(DASH, "app", "dashboard", "premium", "beta", "page.tsx")
    pruefe("die Formularseite gibt es", os.path.isfile(seite))

    # Admin.
    admin = open(os.path.join(DASH, "components", "dashboard",
                              "admin-content.tsx"), encoding="utf-8").read()
    pruefe("das Admin-Panel ist eingebunden",
           re.search(r'activeTab === "beta" && <BetaAdmin', admin) is not None)
    pruefe("der Reiter steht in der Liste", 'id: "beta"' in admin)

    api_ts = open(os.path.join(DASH, "lib", "api.ts"), encoding="utf-8").read()
    for name in ("betaForm:", "betaApply:", "betaNotice:", "betaNoticeSeen:",
                 "betaList:", "betaDecide:", "betaRevoke:"):
        pruefe(f"api.ts kennt {name.rstrip(':')}", name in api_ts)

    # Der Zuruecksetzen-Knopf im Design-Tab.
    #
    # Er hiess frueher „Auf Original" und verwarf nur die Eingaben im
    # Formular. Auf Wunsch heisst er jetzt „Auf Standard" und loescht
    # das Server-Profil wirklich bei Discord -- Einzelheiten und die
    # Route stehen in test_premium_seite.py. Hier bleibt nur, was
    # dieser Test schon immer festhielt: dass es genau einen solchen
    # Knopf gibt und dass er an einer echten Bedingung haengt.
    dp = strip_ts(open(os.path.join(DASH, "components", "dashboard",
                                    "design-panel.tsx"), encoding="utf-8").read())
    pruefe("das Design-Panel hat einen Zuruecksetzen-Knopf",
           "Auf Standard" in dp)
    # Auf die Wirkung zielen: der Knopf selbst muss an der Bedingung
    # haengen, nicht irgendein Block in der Datei. Eine Suche nach
    # "{weichtAb && (" allein bliebe gruen, wenn die Bedingung des
    # Knopfes auf `true` gesetzt wuerde und ein zweiter Block sie
    # weiterhin truege.
    knopf_block = re.search(
        r"\{([^}]*)\s*&&\s*\(\s*<button\s+onClick=\{aufStandard[^}]*\}", dp
    )
    pruefe("der Zuruecksetzen-Knopf haengt an einer Bedingung",
           knopf_block is not None, "er steht ohne Bedingung da")
    if knopf_block:
        pruefe("und zwar an 'weichtAb'",
               knopf_block.group(1).strip() == "weichtAb",
               f"Bedingung: {knopf_block.group(1).strip()!r} -- ein "
               "dauerhaft wirkungsloser Knopf ist Rauschen")
    pruefe("er vergleicht gegen den echten Stand",
           "daten?.current?.nickname" in dp)

    os.chdir(START)

    print()
    if fehler:
        print(f"{len(fehler)} Probleme:")
        for f in fehler:
            print(f"  - {f}")
        return 1
    print("Alle Routen verhalten sich richtig.")
    return 0


sys.exit(main())
