#!/usr/bin/env python3
"""
Der Anti-Nuke: wann er eingreift, wann er schweigt.

Vier Aenderungen, alle vom Nutzer bestellt:

  1. **Kein Eingriff ohne Macht.** Steht die Bot-Rolle unter oder auf
     gleicher Hoehe wie die des Angreifers, oder fehlt das Recht zum
     Bannen und Kicken, passiert **gar nichts** -- kein Versuch, keine
     Meldung. Woertlich: „nie reagiren nie nix machdn".

     Vorher lief der Bot in den Ban, bekam ein ``Forbidden`` und
     meldete „konnte nicht eingreifen" -- bei einem Angriff mit
     vierzig Kanaelen vierzigmal. Wer die Rolle zu tief gehaengt hat,
     wurde von seiner eigenen Fehlkonfiguration zugespamt.

  2. **Selbst-Eskalation auf Administrator.** Eng gefasst, genau wie
     bestellt:

       * hat schon Administrator -> nichts (er koennte es ohnehin)
       * kein Administrator, gibt sich eine Admin-Rolle -> 10 Minuten
         Timeout, Rolle weg, Eintrag im Log-Kanal, **keine DM**
       * gibt sich eine Rolle mit anderen Rechten (bannen, kicken) ->
         **gar nichts**
       * ohne Log-Kanal doch eine DM, sonst merkt es niemand

  3. **Die Aktionen sind einzeln schaltbar** -- das gab es schon: 14
     Stueck im Dashboard-Reiter.

  4. **``TRUSTED_BOTS``**: Discord-IDs bekannter Bots, die nie
     angegriffen werden. Global gesetzt, nicht pro Server -- wer sie
     pro Server pflegen duerfte, koennte den eigenen Zweitbot
     eintragen und den Schutz aushebeln.

Run:  python3 tests/test_nuke_guard.py
"""

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
ROOT = os.path.dirname(BOT)
DASH = os.path.join(ROOT, "dashboard")
ANTINUKE = os.path.join(BOT, "cogs", "antinuke")

sys.path.insert(0, BOT)

failures: list[str] = []


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def read(pfad: str) -> str:
    if not os.path.exists(pfad):
        return ""
    with open(pfad, encoding="utf-8") as f:
        return f.read()


def module() -> list[str]:
    return sorted(
        n for n in os.listdir(ANTINUKE)
        if n.endswith(".py") and n != "__init__.py"
    )


# ══════════════════════════════════════════════════════════════════════
#  Attrappen -- damit die Entscheidungen wirklich laufen
# ══════════════════════════════════════════════════════════════════════


class Rechte:
    def __init__(self, **kw):
        self.ban_members = kw.get("ban_members", False)
        self.kick_members = kw.get("kick_members", False)
        self.administrator = kw.get("administrator", False)


class Rolle:
    def __init__(self, name, position, **rechte):
        self.name = name
        self.position = position
        self.permissions = Rechte(**rechte)

    def __gt__(self, other):
        return self.position > other.position

    def __lt__(self, other):
        return self.position < other.position


class Mitglied:
    def __init__(self, uid, top_role, guild_permissions=None):
        self.id = uid
        self.top_role = top_role
        self.guild_permissions = guild_permissions or Rechte()


class ExMitglied:
    """Wer den Server verlassen hat: ein ``User``, kein ``Member``.

    Hat gar kein ``top_role`` -- nicht ``None``, sondern das Attribut
    fehlt. Der Unterschied ist wichtig: gegen so jemanden laesst sich
    trotzdem ein Bann aussprechen.
    """

    def __init__(self, uid):
        self.id = uid


class Server:
    def __init__(self, owner_id, me, mitglieder=None):
        self.owner_id = owner_id
        self.me = me
        self._m = mitglieder or {}

    def get_member(self, uid):
        return self._m.get(uid)


OWNER, ANGREIFER, BOT_ID = 1, 2, 999
HOCH = Rolle("hoch", 10)
MITTEL = Rolle("mittel", 5)
TIEF = Rolle("tief", 1)
DARF = Rechte(ban_members=True, kick_members=True)


def server(bot_rolle, gegner_rolle, rechte=None):
    ich = Mitglied(BOT_ID, bot_rolle, rechte if rechte is not None else DARF)
    gegner = Mitglied(ANGREIFER, gegner_rolle)
    return Server(OWNER, ich, {BOT_ID: ich, ANGREIFER: gegner})


# ══════════════════════════════════════════════════════════════════════
#  1. Kein Eingriff ohne Macht
# ══════════════════════════════════════════════════════════════════════


def test_rangfolge():
    print("\nOhne Macht passiert gar nichts")

    from utils import nuke_guard

    g = server(HOCH, MITTEL)
    check("Bot ueber dem Angreifer -> eingreifen",
          nuke_guard.can_act_on(g, g.get_member(ANGREIFER)))

    g = server(TIEF, HOCH)
    check("Bot unter dem Angreifer -> nichts",
          not nuke_guard.can_act_on(g, g.get_member(ANGREIFER)))

    # Discord verweigert auch bei Gleichstand. `>=` waere hier ein
    # stiller Fehler: der Bot haelt sich fuer maechtig und laeuft in
    # jedes Forbidden.
    g = server(Rolle("a", 5), Rolle("b", 5))
    check("gleiche Rollenhoehe -> nichts",
          not nuke_guard.can_act_on(g, g.get_member(ANGREIFER)),
          "Discord verweigert auch gegen Gleichrangige")

    g = server(HOCH, MITTEL, Rechte())
    check("kein Bann- und kein Kick-Recht -> nichts",
          not nuke_guard.can_act_on(g, g.get_member(ANGREIFER)))

    g = server(HOCH, MITTEL, Rechte(kick_members=True))
    check("nur Kick-Recht reicht",
          nuke_guard.can_act_on(g, g.get_member(ANGREIFER)))

    # Der Inhaber bekommt hier ausdruecklich eine TIEFERE Rolle als
    # der Bot. Mit gleicher Rolle scheiterte schon der
    # Rangfolge-Vergleich -- der eigene Riegel gegen den Inhaber
    # haette wegfallen koennen, ohne dass es auffaellt. Genau so ist
    # die Mutation zuerst entwischt.
    g = server(HOCH, MITTEL)
    check("gegen den Server-Inhaber nie -- auch wenn der Bot hoeher steht",
          not nuke_guard.can_act_on(g, Mitglied(OWNER, TIEF)),
          "der Inhaber ist unantastbar, unabhaengig von der Rangfolge")

    g = Server(OWNER, Mitglied(BOT_ID, HOCH, DARF), {})
    check("gegen jemanden, der weg ist, geht ein Bann",
          nuke_guard.can_act_on(g, ExMitglied(ANGREIFER)),
          "ein User ohne top_role ist nicht dasselbe wie top_role=None")


def test_alle_module_fragen_nach():
    """Jedes der siebzehn Module muss den Waechter benutzen.

    Vorher stand die Freigabe-Liste siebzehnmal kopiert da. Die
    Rangfolge fehlte in allen siebzehn -- genau das ist der Grund,
    warum sie jetzt an einer Stelle steht.
    """
    print("\nAlle Module fragen den Waechter")

    dateien = module()
    check("es gibt die Module", len(dateien) >= 15, str(len(dateien)))

    ohne = [n for n in dateien if "nuke_guard.should_skip" not in read(
        os.path.join(ANTINUKE, n))]
    check("jedes Modul ruft should_skip", not ohne, ", ".join(ohne))

    ohne_import = [n for n in dateien if "nuke_guard" not in read(
        os.path.join(ANTINUKE, n)).split("class ")[0]]
    check("und importiert ihn", not ohne_import, ", ".join(ohne_import))

    # Die alte, kopierte Pruefung darf nicht daneben stehenbleiben --
    # sonst greift bei einem Modul weiter die Fassung ohne Rangfolge.
    alt = [n for n in dateien
           if "self.bot.user.id}" in read(os.path.join(ANTINUKE, n))]
    check("die alte kopierte Pruefung ist ueberall weg",
          not alt, ", ".join(alt))


# ══════════════════════════════════════════════════════════════════════
#  2. Selbst-Eskalation
# ══════════════════════════════════════════════════════════════════════


def test_selbst_eskalation():
    print("\nWer sich selbst zum Administrator macht")

    quelle = read(os.path.join(ANTINUKE, "anti_member_update.py"))
    check("das Modul existiert", bool(quelle))
    if not quelle:
        return

    check("der Selbstfall wird erkannt",
          "executor.id == after.id" in quelle,
          "sonst zaehlt Selbstvergabe wie Fremdvergabe")

    # Nur den Rumpf der Behandlung ansehen: weiter unten steht
    # `take_action_and_revert`, das richtigerweise bannt. Ein
    # Suchmuster ueber die ganze Datei faende dessen `ban(`.
    rumpf = re.search(
        r"async def handle_self_escalation\(.*?\n(?=    async def |\Z)",
        quelle, re.S,
    )
    check("es gibt eine eigene Behandlung", rumpf is not None)
    if not rumpf:
        return
    body = rumpf.group(0)

    check("zehn Minuten Timeout",
          "datetime.timedelta(minutes=10)" in body)
    check("die Rolle wird entzogen", "remove_roles(new_role" in body)
    check("kein Bann",
          "ban(" not in body,
          "eine Rechte-Ausweitung ist kein Nuke -- ausdrueckliche Vorgabe")

    # Reihenfolge: erst Rolle weg, dann Timeout. Ein Timeout nimmt
    # keine Administrator-Rechte -- andersherum waere die Rolle zehn
    # Minuten laenger scharf.
    check("erst die Rolle, dann der Timeout",
          body.index("remove_roles(new_role") < body.index("member.timeout("),
          "ein Timeout hindert einen Administrator an nichts")

    # Die Bedingungen davor.
    # Nicht "kommt hatte_admin vor": `if False: return` laesst die
    # Variable stehen und steigt trotzdem nie aus. Geprueft wird der
    # Zweig selbst.
    check("wer schon Administrator ist, wird nicht angefasst",
          re.search(r"if hatte_admin:\s*\n\s*return", quelle) is not None,
          "er koennte sich die Rechte ohnehin jederzeit geben")
    check("und die Variable wird wirklich berechnet",
          re.search(r"hatte_admin = any\(", quelle) is not None,
          "sonst steht dort ein fester Wert")
    check("nur Administrator zaehlt, nicht jedes Recht",
          "if not new_role.permissions.administrator:" in quelle,
          "eine Rolle mit Bann-Recht selbst zu nehmen bleibt folgenlos "
          "-- ausdrueckliche Vorgabe")


def test_meldung_ohne_dm():
    print("\nDie Meldung geht in den Log-Kanal, nicht per DM")

    alert = read(os.path.join(BOT, "utils", "nuke_alert.py"))

    check("es gibt die Meldefunktion",
          "async def report_self_escalation" in alert)

    rumpf = re.search(
        r"async def report_self_escalation\(.*?\n(?=async def |\Z)",
        alert, re.S,
    )
    check("der Rumpf ist lesbar", rumpf is not None)
    if not rumpf:
        return
    body = rumpf.group(0)

    check("der Log-Kanal wird gesucht", "alert_channel(" in body)
    check("und beschrieben", "channel.send(" in body)

    # Die DM darf NUR kommen, wenn kein Kanal erreichbar ist. Also
    # muss das Senden an den Kanal vor dem an den Inhaber stehen --
    # mit einem `return` dazwischen.
    check("die DM steht hinter dem Kanal",
          body.index("channel.send(") < body.index("owner.send("),
          "sonst kaeme sie immer")
    zwischen = body[body.index("channel.send("):body.index("owner.send(")]
    check("und wird uebersprungen, wenn der Kanal ging",
          "return" in zwischen,
          "ohne das return kaeme beides -- ausdruecklich nicht gewollt")

    # Und sie geht NICHT ueber `report()`, weil das die DM-Regel
    # anhand von nuke_policy entscheidet.
    check("nicht ueber report()",
          "await report(" not in body,
          "report() entscheidet ueber nuke_policy, ob eine DM faellig "
          "ist -- genau die soll hier nie kommen")

    check("datetime ist importiert",
          re.search(r"^import datetime$", alert, re.M) is not None,
          "sonst faellt die Funktion zur Laufzeit auf die Nase")


# ══════════════════════════════════════════════════════════════════════
#  4. TRUSTED_BOTS
# ══════════════════════════════════════════════════════════════════════


def test_trusted_bots():
    print("\nVertraute Bots aus TRUSTED_BOTS")

    from utils import nuke_guard

    vorher = os.environ.get("TRUSTED_BOTS")
    try:
        os.environ["TRUSTED_BOTS"] = "155149108183695360, 235148962103951360"
        nuke_guard.reset_cache()
        check("beide IDs werden gelesen",
              nuke_guard.trusted_bot_ids()
              == {155149108183695360, 235148962103951360},
              str(nuke_guard.trusted_bot_ids()))
        check("ein eingetragener Bot ist vertraut",
              nuke_guard.is_trusted_bot(155149108183695360))
        check("ein fremder nicht", not nuke_guard.is_trusted_bot(123))

        g = server(HOCH, MITTEL)
        check("und er wird uebersprungen",
              nuke_guard.should_skip(
                  g, Mitglied(155149108183695360, TIEF), BOT_ID))

        # Ein Tippfehler darf den Anti-Nuke nicht lahmlegen: waere die
        # Liste dann leer oder wuerfe sie, staende der Server ohne
        # Schutz da.
        os.environ["TRUSTED_BOTS"] = "abc, , 42 ; 77"
        nuke_guard.reset_cache()
        check("Schrott wird uebersprungen, Zahlen bleiben",
              nuke_guard.trusted_bot_ids() == {42, 77},
              str(nuke_guard.trusted_bot_ids()))

        os.environ["TRUSTED_BOTS"] = ""
        nuke_guard.reset_cache()
        check("ohne Variable ist niemand vertraut",
              nuke_guard.trusted_bot_ids() == frozenset())
    finally:
        if vorher is None:
            os.environ.pop("TRUSTED_BOTS", None)
        else:
            os.environ["TRUSTED_BOTS"] = vorher
        nuke_guard.reset_cache()


def test_trusted_ist_global():
    """Die Liste darf nicht pro Server einstellbar sein.

    Wer sie im Dashboard pflegen duerfte, koennte den eigenen
    Zweitbot eintragen -- und damit den Schutz aushebeln, den der
    Reiter verspricht.
    """
    print("\nDie Liste gilt global")

    panel = read(os.path.join(
        DASH, "components", "dashboard", "antinuke-panel.tsx"))

    check("der Reiter zeigt sie an", "trusted_bots" in panel,
          "sonst wirkt ein ungestraft handelnder Bot wie ein Fehler")
    check("aber ohne Eingabefeld dafuer",
          not re.search(r"trustedBots[^\n]*onChange", panel),
          "sie wird in Railway gesetzt, nicht hier")
    check("und sagt das auch",
          "nur vom Betreiber" in panel or "für alle Server" in panel, "")

    route = read(os.path.join(BOT, "api", "routes", "antinuke.py"))
    check("die API liefert sie", "trusted_bots" in route)
    check("und nimmt sie nicht entgegen",
          "trusted_bots" not in route.split("async def patch_antinuke")[-1],
          "ein PATCH darauf waere die Hintertuer")

    # Die IDs muessen als Zeichenkette gehen: eine Discord-ID ist
    # groesser als Number.MAX_SAFE_INTEGER.
    check("die IDs gehen als Zeichenkette raus",
          '"id": str(kennung)' in route,
          "JavaScript rundet grosse Zahlen stillschweigend")


def test_dokumentiert():
    print("\nDie Variable ist dokumentiert")

    doku = read(os.path.join(ROOT, "RAILWAY_DEPLOYMENT.md"))
    # Gezielt die TABELLENZEILE, nicht irgendein Vorkommen: der Name
    # steht dreimal in der Datei (Tabelle, Ueberschrift, Beispiel).
    # Die Zeile konnte verschwinden, ohne dass die Pruefung anschlug.
    check("sie steht in der Variablentabelle",
          re.search(r"^\| `TRUSTED_BOTS` \|", doku, re.M) is not None,
          "sonst findet sie beim Einrichten niemand")
    check("mit einem Beispiel", 'TRUSTED_BOTS="' in doku)
    check("und der Begruendung, warum global",
          "aushebeln" in doku,
          "sonst fragt der Naechste, warum es nicht im Dashboard steht")


def main() -> int:
    test_rangfolge()
    test_alle_module_fragen_nach()
    test_selbst_eskalation()
    test_meldung_ohne_dm()
    test_trusted_bots()
    test_trusted_ist_global()
    test_dokumentiert()

    print()
    if failures:
        print(f"FAILED: {len(failures)}")
        for eintrag in failures:
            print(f"  - {eintrag}")
        return 1
    print("Alles gruen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
