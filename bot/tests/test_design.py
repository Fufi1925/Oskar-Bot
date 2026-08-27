#!/usr/bin/env python3
"""
Die Design-Routen echt ueber HTTP.

Der wichtigste Punkt: die Rechte. Premium allein darf NICHT reichen --
sonst koennte jeder mit einem Key das Aussehen auf jedem Server
bestimmen, auf dem er zufaellig Rechte hat. Und die Freischaltliste
darf im Nutzer-Dashboard nirgends sichtbar werden.

Run:   python3 tests/test_design.py
"""

import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
START = os.getcwd()
sys.path.insert(0, BOT)
os.chdir(tempfile.mkdtemp(prefix="design-"))
os.makedirs("db", exist_ok=True)
os.environ.setdefault("PREMIUM_KEY_PEPPER", "test-pepper")

fehler = []

INHABER = 1303627964734246944
FREMDER = 1033826242270609449
GILDE = 1530378233579704370
GILDE2 = 1530742522589089952


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


class FakeAsset:
    def __init__(self, url):
        self.url = url


class FakeMe:
    def __init__(self, guild):
        self.id = 1530349205372145715
        self.name = "University Bot"
        self.nick = None
        self.display_name = "University Bot"
        self.display_avatar = FakeAsset("https://cdn.example/av.png")
        self.guild_avatar = None
        self.guild_banner = None
        self._guild = guild
        self.geaendert = {}

        class P:
            change_nickname = True
        self.guild_permissions = P()

    async def edit(self, **kw):
        kw.pop("reason", None)
        self.geaendert.update(kw)
        if "nick" in kw:
            self.nick = kw["nick"]
            self.display_name = kw["nick"] or self.name
        # Wie discord.py: `avatar=None` LOESCHT das Bild, ein
        # fehlender Schluessel laesst es stehen. Der Unterschied ist
        # der ganze Punkt beim Knopf „Auf Standard“ -- deshalb wird
        # hier auf `in kw` geprueft und nicht auf Wahrheitswert.
        if "avatar" in kw:
            self.guild_avatar = (
                FakeAsset("https://cdn.example/guild-av.png")
                if kw["avatar"] else None
            )
        if "banner" in kw:
            self.guild_banner = (
                FakeAsset("https://cdn.example/guild-bn.png")
                if kw["banner"] else None
            )


class FakeGuild:
    def __init__(self, gid, owner_id):
        self.id = gid
        self.name = f"Server {gid}"
        self.owner_id = owner_id
        self.icon = None
        self.me = FakeMe(self)


def baue_app(guilds):
    from fastapi import FastAPI

    from api.dependencies import get_bot
    from api.routes import design

    class FakeBot:
        def get_guild(self, gid):
            return guilds.get(int(gid))

    app = FastAPI()
    app.include_router(design.router, prefix="/design")
    app.dependency_overrides[get_bot] = lambda: FakeBot()
    return app


# Ein winziges gueltiges PNG.
PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def main():
    from fastapi.testclient import TestClient

    from utils import premium_store

    guilds = {GILDE: FakeGuild(GILDE, INHABER), GILDE2: FakeGuild(GILDE2, FREMDER)}
    client = TestClient(baue_app(guilds))

    linie("1  Ohne Premium")
    r = client.get(f"/design/{GILDE}?actor={INHABER}")
    pruefe("GET geht auch ohne Premium", r.status_code == 200, r.text[:150])
    d = r.json()
    pruefe("premium ist false", d["premium"] is False)
    pruefe("may_edit ist false", d["may_edit"] is False)
    pruefe("die Vorschau kommt trotzdem", bool(d.get("current")),
           "ohne sie sieht man nicht, was man kaufen wuerde")

    r = client.post(f"/design/{GILDE}", json={"actor": str(INHABER), "nickname": "Test"})
    pruefe("Speichern wird ohne Premium abgelehnt", r.status_code == 403,
           str(r.status_code))
    pruefe("die Meldung nennt Premium", "Premium" in r.text, r.text[:120])

    linie("2  Mit Premium, als Inhaber")
    schluessel = premium_store.create_key(created_by="test", duration_days=30,
                                          product="main_bot")["key"]
    premium_store.redeem(schluessel, INHABER)

    r = client.get(f"/design/{GILDE}?actor={INHABER}")
    d = r.json()
    pruefe("premium ist jetzt true", d["premium"] is True, str(d))
    pruefe("may_edit ist true", d["may_edit"] is True)

    r = client.post(f"/design/{GILDE}",
                    json={"actor": str(INHABER), "nickname": "Support-Bot"})
    pruefe("Speichern geht", r.status_code == 200, r.text[:200])
    pruefe("der Nickname ist gesetzt",
           guilds[GILDE].me.nick == "Support-Bot", str(guilds[GILDE].me.nick))
    pruefe("die Vorschau zeigt ihn",
           r.json()["current"]["nickname"] == "Support-Bot")

    linie("3  Mit Premium, aber NICHT Inhaber")
    r = client.get(f"/design/{GILDE2}?actor={INHABER}")
    d = r.json()
    pruefe("premium bleibt true", d["premium"] is True)
    pruefe("may_edit ist false", d["may_edit"] is False,
           "Premium allein darf nicht reichen")

    r = client.post(f"/design/{GILDE2}",
                    json={"actor": str(INHABER), "nickname": "Fremd"})
    pruefe("Speichern wird abgelehnt", r.status_code == 403, str(r.status_code))
    pruefe("die Freischaltliste wird NICHT erwaehnt",
           "freigeschaltet" not in r.text.lower()
           and "unlock" not in r.text.lower(),
           r.text[:150])

    linie("4  Nach der Freischaltung durch das Admin-Dashboard")
    r = client.post("/design/admin/unlocked",
                    json={"guild_id": str(GILDE2), "actor": "admin", "note": "Partner"})
    pruefe("Freischalten geht", r.status_code == 200, r.text[:150])

    r = client.get(f"/design/{GILDE2}?actor={INHABER}")
    d = r.json()
    pruefe("may_edit ist jetzt true", d["may_edit"] is True)

    # Der entscheidende Punkt: nichts verraet, WARUM.
    roh = r.text.lower()
    for wort in ("unlock", "freigeschaltet", "freischalt", "granted", "owner"):
        pruefe(f"'{wort}' steht nicht in der Antwort", wort not in roh,
               "die Freischaltliste soll im Nutzer-Dashboard unsichtbar sein")

    r = client.post(f"/design/{GILDE2}",
                    json={"actor": str(INHABER), "nickname": "Partner-Bot"})
    pruefe("Speichern geht jetzt", r.status_code == 200, r.text[:150])

    linie("5  Bilder")
    r = client.post(f"/design/{GILDE}", json={"actor": str(INHABER), "avatar": PNG})
    pruefe("ein PNG wird angenommen", r.status_code == 200, r.text[:200])
    pruefe("der Server-Avatar ist gesetzt",
           guilds[GILDE].me.guild_avatar is not None)

    r = client.post(f"/design/{GILDE}",
                    json={"actor": str(INHABER), "avatar": "data:text/plain;base64,aGk="})
    pruefe("ein falsches Format wird abgelehnt", r.status_code == 400,
           str(r.status_code))

    r = client.post(f"/design/{GILDE}",
                    json={"actor": str(INHABER), "avatar": "https://example.com/x.png"})
    pruefe("eine blosse URL wird abgelehnt", r.status_code == 400,
           "es muss ein hochgeladenes Bild sein")

    # Etwas, das ein Komma hat, aber keine data-URL ist. Die Variante
    # oben trifft die Praefix-Pruefung gar nicht -- sie scheitert
    # schon am split(). Im Mutationstest aufgefallen.
    r = client.post(f"/design/{GILDE}",
                    json={"actor": str(INHABER), "avatar": "irgendwas,aGk="})
    pruefe("etwas ohne data:-Praefix wird abgelehnt", r.status_code == 400,
           str(r.status_code))

    # Zu gross: die Grenze liegt bei 8 MB.
    gross = "data:image/png;base64," + ("A" * (12 * 1024 * 1024))
    r = client.post(f"/design/{GILDE}", json={"actor": str(INHABER), "avatar": gross})
    pruefe("ein zu grosses Bild wird abgelehnt", r.status_code == 400,
           str(r.status_code))
    pruefe("die Meldung nennt die Grenze", "MB" in r.text, r.text[:120])

    linie("6  Grenzen")
    r = client.post(f"/design/{GILDE}",
                    json={"actor": str(INHABER), "nickname": "x" * 99})
    pruefe("ein zu langer Name wird abgelehnt", r.status_code == 400,
           str(r.status_code))

    r = client.post(f"/design/{GILDE}", json={"actor": str(INHABER)})
    pruefe("eine leere Anfrage wird abgelehnt", r.status_code == 400,
           str(r.status_code))

    r = client.get("/design/999999999999999999?actor=1")
    pruefe("ein fremder Server gibt 404", r.status_code == 404, str(r.status_code))

    linie("6b  Auf Standard -- zurueck auf das Developer Portal")

    # Der Ausgangspunkt: auf GILDE hat der Inhaber weiter oben einen
    # Namen und ein Bild gesetzt. Beides muss der Knopf wegbekommen.
    r = client.post(f"/design/{GILDE}", json={
        "actor": str(INHABER), "nickname": "Umbenannt", "avatar": PNG,
        "banner": PNG,
    })
    pruefe("Vorbereitung: Design gesetzt", r.status_code == 200, r.text[:150])

    d = r.json()
    pruefe("das Dashboard erfaehrt von der Abweichung",
           d["deviates"]["abweichung"] is True, str(d.get("deviates")))
    for feld in ("nickname", "avatar", "banner"):
        pruefe(f"'{feld}' wird als abweichend gemeldet",
               feld in d["deviates"]["felder"], str(d["deviates"]))

    # Ohne Premium darf niemand zuruecksetzen -- sonst koennte jeder
    # das Aussehen eines fremden Servers platt machen.
    r = client.post(f"/design/{GILDE}/standard", json={"actor": "424242424242424242"})
    pruefe("ohne Premium abgelehnt", r.status_code == 403, str(r.status_code))

    # Der wichtige Fall: INHABER eines Servers, aber KEIN Premium.
    #
    # `may_edit` sagt hier Ja -- er ist ja der Inhaber. Nur die
    # Premium-Pruefung haelt ihn auf. Ohne diesen Fall bliebe der Test
    # gruen, selbst wenn die Premium-Pruefung ganz herausfaellt:
    # nachgemessen im Mutationstest, das war eine echte Luecke.
    ARM = 424242424242424242
    GILDE_ARM = 1530742522589089954
    guilds[GILDE_ARM] = FakeGuild(GILDE_ARM, ARM)

    r = client.get(f"/design/{GILDE_ARM}?actor={ARM}")
    d = r.json()
    pruefe("Vorbedingung: er ist Inhaber, hat aber kein Premium",
           d["premium"] is False, str(d.get("premium")))

    r = client.post(f"/design/{GILDE_ARM}/standard", json={"actor": str(ARM)})
    pruefe("Inhaber OHNE Premium wird abgelehnt", r.status_code == 403,
           f"HTTP {r.status_code} -- nur die Premium-Pruefung haelt ihn auf")
    pruefe("die Meldung nennt Premium", "Premium" in r.text, r.text[:120])

    # Premium, aber weder Inhaber noch freigeschaltet.
    #
    # Ein dritter Server, eigens dafuer: GILDE gehoert INHABER, und
    # GILDE2 wurde weiter oben freigeschaltet -- an beiden liesse sich
    # nicht zeigen, dass Premium allein zu wenig ist.
    GILDE3 = 1530742522589089953
    guilds[GILDE3] = FakeGuild(GILDE3, FREMDER)
    r = client.post(f"/design/{GILDE3}/standard", json={"actor": str(INHABER)})
    pruefe("Premium allein reicht nicht", r.status_code == 403,
           str(r.status_code))
    pruefe("die Freischaltliste wird dabei nicht erwaehnt",
           "freischalt" not in r.text.lower() and "unlock" not in r.text.lower(),
           r.text[:150])

    # Jetzt der echte Fall.
    r = client.post(f"/design/{GILDE}/standard", json={"actor": str(INHABER)})
    pruefe("Zuruecksetzen geht", r.status_code == 200, r.text[:200])

    me = guilds[GILDE].me
    pruefe("der Nickname ist WEG", me.nick is None, repr(me.nick))
    pruefe("der Server-Avatar ist WEG", me.guild_avatar is None,
           "genau das ging vorher nicht -- repro/bug_design_reset.py")
    pruefe("das Server-Banner ist WEG", me.guild_banner is None,
           "genau das ging vorher nicht -- repro/bug_design_reset.py")

    d = r.json()
    pruefe("die Antwort meldet keine Abweichung mehr",
           d["deviates"]["abweichung"] is False, str(d.get("deviates")))
    pruefe("und keine Felder", d["deviates"]["felder"] == [],
           str(d["deviates"]))

    # Auch die eigene Tabelle muss leer sein, sonst zeigt das
    # Dashboard nach einem Neuladen wieder alte Werte an.
    for feld in ("nickname", "avatar_url", "banner_url"):
        pruefe(f"gespeichertes '{feld}' ist geleert", d[feld] is None,
               repr(d[feld]))

    # Die Freischaltung darf ein Zuruecksetzen ueberleben: sie liegt
    # in einer eigenen Tabelle und hat mit dem Aussehen nichts zu tun.
    #
    # Gefragt wird als INHABER: er hat Premium, ist auf GILDE2 aber
    # NICHT Inhaber -- sein `may_edit` haengt dort allein an der
    # Freischaltung aus Abschnitt 4. FREMDER taugt dafuer nicht, der
    # hat gar kein Premium und waere immer `false`.
    r = client.get(f"/design/{GILDE2}?actor={INHABER}")
    pruefe("die Freischaltung ueberlebt das Zuruecksetzen",
           r.json()["may_edit"] is True)

    # Nichts mehr da, aber der Aufruf darf trotzdem nicht scheitern.
    r = client.post(f"/design/{GILDE}/standard", json={"actor": str(INHABER)})
    pruefe("zweimal zuruecksetzen ist harmlos", r.status_code == 200,
           r.text[:150])

    r = client.post("/design/999999999999999999/standard",
                    json={"actor": str(INHABER)})
    pruefe("ein fremder Server gibt 404", r.status_code == 404,
           str(r.status_code))

    linie("7  Die Freischaltliste selbst")
    r = client.get("/design/admin/unlocked")
    pruefe("die Liste ist abrufbar", r.status_code == 200, r.text[:120])
    eintraege = r.json()["servers"]
    pruefe("der Eintrag steht drin", len(eintraege) == 1, str(eintraege))
    pruefe("die ID ist eine Zeichenkette",
           isinstance(eintraege[0]["guild_id"], str),
           "eine rohe Zahl kaeme im Browser verschoben an")

    r = client.delete(f"/design/admin/unlocked/{GILDE2}")
    pruefe("Zuruecknehmen geht", r.status_code == 200, r.text[:120])

    r = client.get(f"/design/{GILDE2}?actor={INHABER}")
    pruefe("danach darf er nicht mehr",
           r.json()["may_edit"] is False)

    linie("8  Anbindung")

    import re

    def strip_ts(src):
        ohne = re.sub(r"(?<!:)//[^\n]*", "", src)
        return re.sub(r"/\*.*?\*/", "", ohne, flags=re.S)

    # Router eingebunden?
    server = open(os.path.join(BOT, "api", "server.py"), encoding="utf-8").read()
    pruefe("der Router ist importiert",
           re.search(r"from api\.routes import[^\n]*\bdesign\b", server) is not None)
    pruefe("und eingebunden", 'prefix="/design"' in server)

    # Die Admin-Routen muessen VOR /{guild_id} stehen.
    from api.routes import design as design_modul
    pfade = [getattr(r, "path", "") for r in design_modul.router.routes]
    pruefe("die Admin-Routen stehen vor /{guild_id}",
           pfade.index("/admin/unlocked") < pfade.index("/{guild_id}"),
           f"Reihenfolge: {pfade}")

    # Premium gilt fuer beide Bots -- es gibt nur eins.
    prem = open(os.path.join(BOT, "api", "routes", "premium.py"),
                encoding="utf-8").read()
    pruefe("der Hauptbot hat echtes Premium",
           "zustand = store.status(user_id)" in prem,
           "vorher stand hier fest coming_soon, dann zwei Produkte")
    pruefe("Keys lassen sich fuer den Hauptbot ausstellen",
           '"main_bot"' in prem and "product=produkt" in prem)

    # Dashboard.
    seite = os.path.join(DASH, "app", "dashboard", "guild", "[guildId]",
                         "design", "page.tsx")
    pruefe("die Seite gibt es", os.path.isfile(seite))

    panel_pfad = os.path.join(DASH, "components", "dashboard", "design-panel.tsx")
    pruefe("das Panel gibt es", os.path.isfile(panel_pfad))
    if os.path.isfile(panel_pfad):
        panel = strip_ts(open(panel_pfad, encoding="utf-8").read())
        pruefe("es zeigt die Premium-Sperre",
               "Premium erforderlich" in panel)
        # Auf die Wirkung zielen: die Sperre muss an `premium` haengen.
        pruefe("die Sperre haengt am Premium-Zustand",
               re.search(r"\{!premium && <PremiumSperre", panel) is not None,
               "sonst ist sie Zierde")
        pruefe("es gibt eine Live-Vorschau",
               "Live-Vorschau" in panel and "zeigtName" in panel)
        pruefe("die Vorschau nutzt den Entwurf",
               "nickname.trim() || jetzt.name" in panel,
               "sonst zeigt sie nur den gespeicherten Stand")
        # Die Freischaltliste darf im Nutzer-Panel nicht vorkommen.
        for wort in ("unlocked", "freischalt", "Freischalt"):
            pruefe(f"'{wort}' steht nicht im Nutzer-Panel", wort not in panel)

    layout = open(os.path.join(DASH, "app", "dashboard", "layout.tsx"),
                  encoding="utf-8").read()
    pruefe("der Reiter steht in der Seitenleiste", "/design`" in layout)
    pruefe("er ist gelb hervorgehoben", "highlight: true" in layout)
    # Ganz oben: direkt nach der Uebersicht.
    pruefe("er steht ganz oben",
           layout.find('name: "Design"') < layout.find('name: "Schutz"'),
           "er soll der erste Eintrag sein")

    tabs = open(os.path.join(DASH, "components", "guild-tabs.tsx"),
                encoding="utf-8").read()
    pruefe("und in der Reiterleiste", 'slug: "design"' in tabs)

    admin = open(os.path.join(DASH, "components", "dashboard",
                              "admin-content.tsx"), encoding="utf-8").read()
    # Auf die Wirkung zielen: der Import allein zeigt nichts an.
    pruefe("das Admin-Panel ist importiert", "DesignUnlockPanel" in admin)
    pruefe("und wird auch gerendert",
           re.search(r'activeTab === "designunlock" && <DesignUnlockPanel', admin)
           is not None,
           "sonst ist der Reiter da und bleibt leer")
    pruefe("der Reiter steht in der Liste",
           re.search(r'id: "designunlock"', admin) is not None)

    api_ts = open(os.path.join(DASH, "lib", "api.ts"), encoding="utf-8").read()
    for name in ("design:", "designSave:", "designUnlocked:", "designUnlock:",
                 "designLock:"):
        pruefe(f"api.ts kennt {name.rstrip(':')}", name in api_ts)

    proxy = strip_ts(open(os.path.join(DASH, "app", "api", "bot", "[...path]",
                                       "route.ts"), encoding="utf-8").read())
    pruefe("der Proxy kennt den Bereich", 'scope === "design"' in proxy)
    zweig = proxy[proxy.find('scope === "design"'):]
    zweig = zweig[:zweig.find('scope === "honeypot"')]
    # Der Admin-Zweig muss wirklich sperren, nicht nur existieren.
    admin_zweig = zweig[zweig.find('rest[0] === "admin"'):]
    admin_zweig = admin_zweig[:admin_zweig.find("const guildId")]
    pruefe("die Freischaltliste ist nur fuer Admins",
           "isGlobalAdmin" in admin_zweig and "deny(" in admin_zweig,
           "sonst koennte sich jeder selbst freischalten")
    pruefe("Nicht-Admins bekommen kein stilles Ja",
           not re.search(r'rest\[0\] === "admin"\)\s*\{\s*return \{ ok: true \};',
                         admin_zweig),
           "ein bedingungsloses ok waere die Luecke")

    os.chdir(START)

    print()
    if fehler:
        print(f"{len(fehler)} Probleme:")
        for f in fehler:
            print(f"  - {f}")
        return 1
    print("Alle Routen verhalten sich richtig.")
    return 0


sys.exit(asyncio.run(main()))
