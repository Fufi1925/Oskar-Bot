#!/usr/bin/env python3
"""
Die Regeln der Ticket-Benachrichtigungen.

Der Ablauf, um den es geht, ist als Reihenfolge formuliert -- und
danach ist dieser Test sortiert:

  1. Ist die Funktion im Dashboard an?
  2. Wurde das Ticket gerade erst erstellt (nur Bot und Nutzer)? Dann
     keine DM.
  3. Schreibt ein Teammitglied, wird fuenf Minuten gewartet.
  4. Hat der Nutzer inzwischen selbst geschrieben, entfaellt die DM.
  5. Hat er fuer dieses Ticket in der letzten Stunde schon eine
     bekommen, entfaellt sie ebenfalls.
  6. Dieselbe Kette umgekehrt fuer das Team.
  7. ``>sleep`` legt ein Ticket still -- fuer beide Richtungen.

Alles laeuft gegen echtes SQLite. Geprueft wird die Wirkung, nicht ob
ein Wort im Quelltext vorkommt.

Run:  python3 tests/test_ticket_notify.py
"""

import ast
import asyncio
import os
import re
import sys
import tempfile
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)
sys.path.insert(0, BOT)

from utils import ticket_notify as tn  # noqa: E402

failures: list[str] = []

GUILD = 1530378233579704370
KANAL = 555666777888
USER = 1303627964734246944
STAFF_A = 1033826242270609449
STAFF_B = 111222333444555

T0 = 1770000000


def check(name, ok, extra=""):
    if ok:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name} {extra}")
        failures.append(f"{name} {extra}")


def strip_py(src: str) -> str:
    src = re.sub(r"^\s*#.*$", "", src, flags=re.M)
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    lines = src.split("\n")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc and node.body:
                first = node.body[0]
                for i in range(first.lineno - 1, first.end_lineno):
                    lines[i] = ""
    return "\n".join(lines)


async def frisches_ticket(kanal=KANAL, **einstellungen):
    """
    Ein Ticket im Ausgangszustand, mit beiden Richtungen an.

    Alle Zeiten werden hier ausdruecklich zurueckgesetzt. ``save_settings``
    fuehrt bewusst mit dem bestehenden Stand zusammen -- das Dashboard
    schickt beim Umlegen eines Schalters ja auch nur dieses eine Feld.
    Ohne das Zuruecksetzen wuerde ein Test, der die Wartezeit aendert,
    den naechsten beeinflussen.
    """
    await tn.forget(kanal)
    grund = {
        "user_dm_enabled": True,
        "staff_dm_enabled": True,
        "user_delay": tn.DEFAULT_USER_DELAY,
        "staff_delay": tn.DEFAULT_STAFF_DELAY,
        "user_cooldown": tn.DEFAULT_USER_COOLDOWN,
        "staff_cooldown": tn.DEFAULT_STAFF_COOLDOWN,
        "quiet_enabled": False,
    }
    grund.update(einstellungen)
    await tn.save_settings(GUILD, grund)
    await tn.register_ticket(kanal, GUILD, USER)
    return kanal


# ── 1. Der Schalter ──────────────────────────────────────────────────

async def test_schalter():
    print("\n1. Ohne Schalter im Dashboard passiert nichts")
    k = await frisches_ticket(user_dm_enabled=False, staff_dm_enabled=False)

    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0)
    d = await tn.decide(k, "user", now=T0 + 9999)
    check("Nutzer-DM aus -> keine DM", not d.send and d.reason == "disabled",
          f"({d.reason})")

    await tn.note_message(k, author_id=USER, is_staff=False, now=T0 + 10)
    d = await tn.decide(k, "staff", now=T0 + 9999)
    check("Team-DM aus -> keine DM", not d.send and d.reason == "disabled",
          f"({d.reason})")

    # Und mit Schalter geht es -- sonst prueft der Test nur, dass nichts geht.
    await tn.save_settings(GUILD, {"user_dm_enabled": True, "staff_dm_enabled": True})
    d = await tn.decide(k, "staff", now=T0 + 9999)
    check("mit Schalter geht es wieder", d.send, f"({d.reason})")


# ── 2. Frisches Ticket ───────────────────────────────────────────────

async def test_frisches_ticket():
    print("\n2. Im frisch erstellten Ticket kommt nie eine DM")
    k = await frisches_ticket()

    # Nur der Nutzer schreibt -- so sieht ein neues Ticket aus.
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0 + 60)

    d = await tn.decide(k, "user", now=T0 + 99999)
    check("keine Nutzer-DM ohne Team im Ticket",
          not d.send and d.reason == "fresh_ticket", f"({d.reason})")

    # Auch das Team bekommt nichts: es hat noch nie geantwortet, es kann
    # also niemanden geben, der "nicht zurueckgeschrieben" hat.
    d = await tn.decide(k, "staff", now=T0 + 99999)
    check("keine Team-DM ohne vorherige Team-Antwort",
          not d.send, f"({d.reason})")


# ── 3. Wartezeit ─────────────────────────────────────────────────────

async def test_wartezeit():
    print("\n3. Nach der Team-Antwort wird gewartet")
    k = await frisches_ticket()
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 100)

    d = await tn.decide(k, "user", now=T0 + 100)
    check("sofort danach: nein", not d.send and d.reason == "too_soon", f"({d.reason})")

    d = await tn.decide(k, "user", now=T0 + 100 + 299)
    check("nach 4:59 Minuten: nein", not d.send and d.reason == "too_soon",
          f"({d.reason})")

    d = await tn.decide(k, "user", now=T0 + 100 + 300)
    check("nach genau 5 Minuten: ja", d.send, f"({d.reason})")
    check("die DM geht an den Ersteller", d.target_id == USER, f"({d.target_id})")

    # Und die eingestellte Zeit muss auch wirken.
    await tn.save_settings(GUILD, {"user_delay": 600})
    d = await tn.decide(k, "user", now=T0 + 100 + 300)
    check("laengere Wartezeit wird beachtet",
          not d.send and d.reason == "too_soon", f"({d.reason})")
    d = await tn.decide(k, "user", now=T0 + 100 + 600)
    check("nach der laengeren Wartezeit: ja", d.send, f"({d.reason})")


# ── 4. Der Nutzer hat selbst geschrieben ─────────────────────────────

async def test_nutzer_war_da():
    print("\n4. Wenn der Nutzer selbst schreibt, entfaellt die DM")
    k = await frisches_ticket()
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 100)
    # Der Nutzer liest und antwortet innerhalb der Wartezeit.
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0 + 150)

    d = await tn.decide(k, "user", now=T0 + 9999)
    check("keine Nutzer-DM mehr", not d.send and d.reason == "answered",
          f"({d.reason})")

    # Die Erinnerung muss auch im Zustand geloescht sein, nicht nur in
    # der Entscheidung. Sonst bleibt das Ticket fuer immer im
    # Hintergrundlauf haengen: alle 30 Sekunden wird es geprueft, jedes
    # Mal verworfen. Ueber decide() ist das nicht zu sehen -- der
    # Zeitstempelvergleich deckt es zu -- also wird hier direkt in den
    # Zustand geschaut.
    st = await tn.get_state(k)
    check("Erinnerung ist im Zustand geloescht", st["pending_user"] == 0,
          f"(pending_user={st['pending_user']})")
    # Nur die Nutzer-Seite darf hier weg sein. Dass jetzt eine
    # Team-Erinnerung ansteht, ist richtig so -- der Nutzer wartet ja.
    offen = [t for t in await tn.due_tickets() if t["channel_id"] == k]
    check("keine Nutzer-Erinnerung mehr im Hintergrundlauf",
          all(t["pending_user"] == 0 for t in offen), f"({offen})")

    # Hier greifen ZWEI Ebenen: note_message loescht die Erinnerung, und
    # decide() vergleicht zusaetzlich die Zeitstempel. Faellt eine weg,
    # faengt die andere den Fehler auf -- und der Test bliebe gruen,
    # obwohl das System nur noch halb funktioniert. Also wird jede Ebene
    # einzeln geprueft, mit einem von Hand gebauten Zustand.
    print("     -- jede Ebene fuer sich --")

    # Ebene A: die Erinnerung ist geloescht, die Zeitstempel wuerden aber
    # noch fuer eine DM sprechen.
    nur_geloescht = {
        "channel_id": k, "guild_id": GUILD, "creator_id": USER,
        "last_user_msg": T0 + 50, "last_staff_msg": T0 + 100,
        "last_staff_id": STAFF_A, "staff_has_written": True,
        "sleeping": False, "sleep_by": None,
        "pending_user": 0, "pending_staff": 0,
    }
    d = await tn.decide(k, "user", now=T0 + 9999, state=nur_geloescht)
    check("Ebene A: ohne Erinnerung keine DM", not d.send, f"({d.reason})")

    # Ebene B: die Erinnerung steht noch, aber der Nutzer hat zuletzt
    # geschrieben. Genau der Fall nach einem verpassten Loeschen.
    nur_zeitstempel = dict(nur_geloescht)
    nur_zeitstempel["pending_user"] = T0 + 100
    nur_zeitstempel["last_user_msg"] = T0 + 150
    d = await tn.decide(k, "user", now=T0 + 9999, state=nur_zeitstempel)
    check("Ebene B: Nutzer hat zuletzt geschrieben -> keine DM",
          not d.send and d.reason == "answered", f"({d.reason})")

    # Und die Gegenprobe: steht die Erinnerung UND hat das Team zuletzt
    # geschrieben, muss die DM rausgehen. Sonst wuerde der Test auch
    # dann bestehen, wenn gar nichts mehr zugestellt wird.
    echt_faellig = dict(nur_geloescht)
    echt_faellig["pending_user"] = T0 + 100
    d = await tn.decide(k, "user", now=T0 + 9999, state=echt_faellig)
    check("Gegenprobe: echter Fall geht raus", d.send, f"({d.reason})")


# ── 5. Sperrzeit ─────────────────────────────────────────────────────

async def test_sperrzeit():
    print("\n5. Zweite DM zum selben Ticket erst nach der Sperrzeit")
    k = await frisches_ticket()
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 100)

    d = await tn.decide(k, "user", now=T0 + 500)
    check("erste DM darf raus", d.send, f"({d.reason})")
    await tn.record_sent(k, GUILD, USER, "user", now=T0 + 500)

    # Team schreibt nochmal -> neue Erinnerung, aber Sperrzeit laeuft.
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 600)
    d = await tn.decide(k, "user", now=T0 + 1200)
    check("zweite DM innerhalb der Stunde: nein",
          not d.send and d.reason == "cooldown", f"({d.reason})")

    d = await tn.decide(k, "user", now=T0 + 600 + 3601)
    check("nach Ablauf der Sperrzeit: ja", d.send, f"({d.reason})")

    # Die Sperrzeit gilt pro Ticket, nicht pro Person.
    k2 = await frisches_ticket(kanal=KANAL + 1)
    await tn.note_message(k2, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k2, author_id=STAFF_A, is_staff=True, now=T0 + 100)
    d = await tn.decide(k2, "user", now=T0 + 1200)
    check("anderes Ticket ist nicht gesperrt", d.send, f"({d.reason})")


# ── 6. Die Gegenrichtung ─────────────────────────────────────────────

async def test_team_richtung():
    print("\n6. Das Team wird benachrichtigt, wenn der Nutzer wartet")
    k = await frisches_ticket()
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 100)
    # Nutzer antwortet -- ab jetzt wartet er.
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0 + 200)

    d = await tn.decide(k, "staff", now=T0 + 400)
    check("vor Ablauf der Wartezeit: nein", not d.send and d.reason == "too_soon",
          f"({d.reason})")

    d = await tn.decide(k, "staff", now=T0 + 500)
    check("nach 5 Minuten: ja", d.send, f"({d.reason})")
    check("geht an das zuletzt aktive Teammitglied", d.target_id == STAFF_A,
          f"({d.target_id})")

    # Schreibt ein zweites Teammitglied, wandert das Ziel mit.
    await tn.note_message(k, author_id=STAFF_B, is_staff=True, now=T0 + 600)
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0 + 700)
    d = await tn.decide(k, "staff", now=T0 + 1100)
    check("jetzt an das neue Teammitglied", d.send and d.target_id == STAFF_B,
          f"({d.target_id})")

    # Antwortet das Team rechtzeitig, entfaellt die DM.
    await tn.note_message(k, author_id=STAFF_B, is_staff=True, now=T0 + 1150)
    d = await tn.decide(k, "staff", now=T0 + 9999)
    check("Team hat geantwortet -> keine DM", not d.send and d.reason == "answered",
          f"({d.reason})")

    print("     -- jede Ebene fuer sich --")

    def zustand(**abweichung):
        basis = {
            "channel_id": k, "guild_id": GUILD, "creator_id": USER,
            "last_user_msg": T0 + 200, "last_staff_msg": T0 + 100,
            "last_staff_id": STAFF_A, "staff_has_written": True,
            "sleeping": False, "sleep_by": None,
            "pending_user": 0, "pending_staff": T0 + 200,
        }
        basis.update(abweichung)
        return basis

    d = await tn.decide(k, "staff", now=T0 + 9999, state=zustand(pending_staff=0))
    check("Ebene A: ohne Erinnerung keine Team-DM", not d.send, f"({d.reason})")

    d = await tn.decide(k, "staff", now=T0 + 9999,
                        state=zustand(last_staff_msg=T0 + 300))
    check("Ebene B: Team hat zuletzt geschrieben -> keine DM",
          not d.send and d.reason == "answered", f"({d.reason})")

    d = await tn.decide(k, "staff", now=T0 + 9999, state=zustand())
    check("Gegenprobe: echter Fall geht raus", d.send, f"({d.reason})")

    # Die Sperrzeit der Team-Richtung, ebenfalls einzeln. Ohne eigenen
    # Kanal wuerde die Nutzer-Sperrzeit den Fall mit abdecken.
    k3 = KANAL + 20
    await tn.forget(k3)
    await tn.register_ticket(k3, GUILD, USER)
    await tn.note_message(k3, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k3, author_id=STAFF_A, is_staff=True, now=T0 + 100)
    await tn.note_message(k3, author_id=USER, is_staff=False, now=T0 + 200)

    d = await tn.decide(k3, "staff", now=T0 + 600)
    check("Team-Sperrzeit: erste DM darf raus", d.send, f"({d.reason})")
    await tn.record_sent(k3, GUILD, STAFF_A, "staff", now=T0 + 600)

    await tn.note_message(k3, author_id=USER, is_staff=False, now=T0 + 700)
    d = await tn.decide(k3, "staff", now=T0 + 1300)
    check("Team-Sperrzeit greift", not d.send and d.reason == "cooldown",
          f"({d.reason})")
    d = await tn.decide(k3, "staff", now=T0 + 700 + 3601)
    check("Team-Sperrzeit laeuft ab", d.send, f"({d.reason})")
    await tn.forget(k3)

    # Und die Erinnerung fuer das Team darf nur entstehen, wenn vorher
    # wirklich jemand vom Team da war. Sonst bekaeme das Team eine DM
    # ueber ein Ticket, das es noch nie gesehen hat.
    k4 = KANAL + 21
    await tn.forget(k4)
    await tn.register_ticket(k4, GUILD, USER)
    st = await tn.note_message(k4, author_id=USER, is_staff=False, now=T0)
    check("ohne Team-Antwort entsteht keine Team-Erinnerung",
          st is not None and st["pending_staff"] == 0, f"({st})")
    st = await tn.note_message(k4, author_id=USER, is_staff=False, now=T0 + 60)
    check("auch nach mehreren Nutzer-Nachrichten nicht",
          st is not None and st["pending_staff"] == 0, f"({st})")
    await tn.forget(k4)


# ── 7. >sleep ────────────────────────────────────────────────────────

async def test_sleep():
    print("\n7. >sleep legt das Ticket still")
    k = await frisches_ticket()
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 100)

    d = await tn.decide(k, "user", now=T0 + 500)
    check("vorher wuerde eine DM rausgehen", d.send, f"({d.reason})")

    await tn.set_sleeping(k, True, STAFF_A)

    d = await tn.decide(k, "user", now=T0 + 500)
    check("Nutzer-DM ist still", not d.send and d.reason == "sleeping", f"({d.reason})")

    # Auch die Gegenrichtung, und auch fuer spaeter entstehende Faelle.
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0 + 600)
    d = await tn.decide(k, "staff", now=T0 + 1200)
    check("Team-DM ist still", not d.send and d.reason == "sleeping", f"({d.reason})")

    # Schlafende Tickets tauchen im Hintergrundlauf nicht auf.
    offen = [t for t in await tn.due_tickets() if t["channel_id"] == k]
    check("faellt aus dem Hintergrundlauf raus", len(offen) == 0, f"({offen})")

    await tn.set_sleeping(k, False)
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 2000)
    d = await tn.decide(k, "user", now=T0 + 2400)
    check("nach >wake geht es wieder", d.send, f"({d.reason})")

    # Und beim Schliessen ist alles weg.
    await tn.forget(k)
    d = await tn.decide(k, "user", now=T0 + 3000)
    check("geschlossenes Ticket -> nichts", not d.send and d.reason == "closed",
          f"({d.reason})")


# ── 8. Ruhezeit ──────────────────────────────────────────────────────

async def test_ruhezeit():
    print("\n8. Ruhezeit")
    s = {"quiet_enabled": True, "quiet_start": 22, "quiet_end": 8}

    def um(stunde):
        return datetime(2026, 8, 10, stunde, 0, tzinfo=timezone.utc)

    # Ueber Mitternacht -- der Fall, den man leicht falsch macht.
    check("23 Uhr ist Ruhezeit", tn.in_quiet_hours(s, um(23)))
    check("3 Uhr ist Ruhezeit", tn.in_quiet_hours(s, um(3)))
    check("7 Uhr ist Ruhezeit", tn.in_quiet_hours(s, um(7)))
    check("8 Uhr ist keine mehr", not tn.in_quiet_hours(s, um(8)))
    check("14 Uhr ist keine", not tn.in_quiet_hours(s, um(14)))
    check("22 Uhr ist wieder Ruhezeit", tn.in_quiet_hours(s, um(22)))

    # Und der gewoehnliche Fall ohne Mitternacht.
    s2 = {"quiet_enabled": True, "quiet_start": 1, "quiet_end": 6}
    check("1 bis 6: 3 Uhr ja", tn.in_quiet_hours(s2, um(3)))
    check("1 bis 6: 23 Uhr nein", not tn.in_quiet_hours(s2, um(23)))

    check("ausgeschaltet ist nie Ruhezeit",
          not tn.in_quiet_hours({"quiet_enabled": False, "quiet_start": 0,
                                 "quiet_end": 23}, um(5)))
    check("Start gleich Ende ist keine Ruhezeit",
          not tn.in_quiet_hours({"quiet_enabled": True, "quiet_start": 5,
                                 "quiet_end": 5}, um(5)))

    # Und die Entscheidung muss sie auch wirklich anwenden.
    k = await frisches_ticket(quiet_enabled=True, quiet_start=22, quiet_end=8)
    await tn.note_message(k, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(k, author_id=STAFF_A, is_staff=True, now=T0 + 100)
    nachts = int(datetime(2026, 8, 10, 23, 30, tzinfo=timezone.utc).timestamp())
    d = await tn.decide(k, "user", now=nachts)
    check("nachts geht keine DM raus", not d.send and d.reason == "quiet_hours",
          f"({d.reason})")


# ── 9. Einstellungen ─────────────────────────────────────────────────

async def test_einstellungen():
    print("\n9. Einstellungen werden gespeichert und begrenzt")
    await tn.save_settings(GUILD, {
        "user_dm_enabled": True, "staff_dm_enabled": False,
        "user_delay": 600, "staff_cooldown": 7200,
    })
    s = await tn.get_settings(GUILD)
    check("Schalter gespeichert", s["user_dm_enabled"] and not s["staff_dm_enabled"])
    check("Wartezeit gespeichert", s["user_delay"] == 600, f"({s['user_delay']})")
    check("Sperrzeit gespeichert", s["staff_cooldown"] == 7200,
          f"({s['staff_cooldown']})")

    # Ohne Untergrenze koennte 0 bei jeder Nachricht eine DM ausloesen.
    s = await tn.save_settings(GUILD, {"user_delay": 0, "user_cooldown": 1})
    check("Wartezeit hat eine Untergrenze", s["user_delay"] >= 30,
          f"({s['user_delay']})")
    check("Sperrzeit hat eine Untergrenze", s["user_cooldown"] >= 60,
          f"({s['user_cooldown']})")

    s = await tn.save_settings(GUILD, {"user_delay": 999999999})
    check("Wartezeit hat eine Obergrenze", s["user_delay"] <= 86400,
          f"({s['user_delay']})")

    s = await tn.save_settings(GUILD, {"user_delay": "keine Zahl"})
    check("Unsinn aendert nichts", s["user_delay"] == 86400, f"({s['user_delay']})")

    # Ein unbekannter Server bekommt die Voreinstellung, und die ist AUS.
    s = await tn.get_settings(999999999999)
    check("Voreinstellung ist aus",
          not s["user_dm_enabled"] and not s["staff_dm_enabled"])
    check("Voreinstellung 5 Minuten", s["user_delay"] == 300)
    check("Voreinstellung 1 Stunde", s["user_cooldown"] == 3600)


# ── 10. Der Hintergrundlauf ──────────────────────────────────────────

async def test_hintergrundlauf():
    print("\n10. Faellige Tickets werden gefunden")
    for kanal in (KANAL, KANAL + 1, KANAL + 2):
        await tn.forget(kanal)
    await tn.save_settings(GUILD, {"user_dm_enabled": True, "staff_dm_enabled": True,
                                   "quiet_enabled": False})

    a = KANAL + 10
    await tn.register_ticket(a, GUILD, USER)
    await tn.note_message(a, author_id=USER, is_staff=False, now=T0)
    await tn.note_message(a, author_id=STAFF_A, is_staff=True, now=T0 + 100)

    offen = [t for t in await tn.due_tickets() if t["channel_id"] == a]
    check("offene Erinnerung wird gefunden", len(offen) == 1, f"({offen})")
    check("und zwar als Nutzer-Erinnerung",
          offen and offen[0]["pending_user"] > 0 and not offen[0]["pending_staff"])

    # Nach dem Versand ist sie weg.
    await tn.record_sent(a, GUILD, USER, "user", now=T0 + 500)
    offen = [t for t in await tn.due_tickets() if t["channel_id"] == a]
    check("nach dem Versand nicht mehr offen", len(offen) == 0, f"({offen})")

    await tn.forget(a)


# ── 11. Verdrahtung ──────────────────────────────────────────────────

def test_verdrahtung():
    print("\n11. Cog, Route und Schema sind eingetragen")
    init = open(os.path.join(BOT, "cogs/__init__.py"), encoding="utf-8").read()
    check("Cog wird importiert",
          "from .events.ticket_notify import TicketNotify" in init)
    check("Cog wird hinzugefuegt", "add_cog(TicketNotify(bot))" in init)

    cog_src = open(os.path.join(BOT, "cogs/events/ticket_notify.py"),
                   encoding="utf-8").read()
    baum = ast.parse(cog_src)

    # Ein on_message ohne Dekorator wird nie aufgerufen.
    hat_listener = False
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.AsyncFunctionDef) and knoten.name == "on_message":
            for dek in knoten.decorator_list:
                if isinstance(dek, ast.Call) and getattr(dek.func, "attr", "") == "listener":
                    hat_listener = True
    check("on_message ist als Listener registriert", hat_listener)

    def ruft_auf(funktionsname, methode):
        for knoten in ast.walk(baum):
            if isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and knoten.name == funktionsname:
                for unter in ast.walk(knoten):
                    if isinstance(unter, ast.Call) \
                            and isinstance(unter.func, ast.Attribute) \
                            and unter.func.attr == methode:
                        return True
        return False

    check("Hintergrundlauf wird gestartet", ruft_auf("__init__", "start"))
    check("Hintergrundlauf wird gestoppt", ruft_auf("cog_unload", "cancel"))
    check("wartet auf den Bot", ruft_auf("before_check", "wait_until_ready"))

    stripped = strip_py(cog_src)
    check("check_pending ist ein tasks.loop",
          bool(re.search(r"@tasks\.loop\([^)]*\)\s*\n\s*async def check_pending",
                         stripped)))
    check("es gibt >sleep", 'name="sleep"' in stripped)
    check("es gibt >wake", 'name="wake"' in stripped)

    # Die Route.
    route = open(os.path.join(BOT, "api/routes/tickets.py"), encoding="utf-8").read()
    check("GET /notify vorhanden", '"/{guild_id}/notify"' in route)
    check("PATCH /notify vorhanden", route.count('"/{guild_id}/notify"') >= 2)

    guard = open(os.path.join(BOT, "api/schema_guard.py"), encoding="utf-8").read()
    check("schema_guard kennt db/ticket_notify.db", '"db/ticket_notify.db"' in guard)

    # Das Ticket muss beim Erstellen angemeldet und beim Schliessen
    # vergessen werden -- sonst laeuft der Zustand voll.
    #
    # "Der Name kommt vor" reicht hier nicht: `pass  # forget` enthaelt
    # ihn auch. Deshalb wird im Syntaxbaum nachgesehen, ob in der
    # jeweiligen Funktion wirklich ein Aufruf steht.
    ticket_baum = ast.parse(open(os.path.join(BOT, "cogs/commands/ticket.py"),
                                 encoding="utf-8").read())

    def ruft_notify(methode: str) -> list[str]:
        """In welchen Funktionen wird ticket_notify.<methode>() aufgerufen?"""
        treffer = []
        for knoten in ast.walk(ticket_baum):
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for unter in ast.walk(knoten):
                if (isinstance(unter, ast.Call)
                        and isinstance(unter.func, ast.Attribute)
                        and unter.func.attr == methode
                        and getattr(unter.func.value, "id", "") == "ticket_notify"):
                    treffer.append(knoten.name)
        return treffer

    check("Ticket wird beim Erstellen wirklich angemeldet",
          "create_ticket_flow" in ruft_notify("register_ticket"),
          f"({ruft_notify('register_ticket')})")

    vergessen = ruft_notify("forget")
    check("Ticket wird beim Schliessen wirklich vergessen",
          len(vergessen) >= 1, f"({vergessen})")
    check("auch beim endgueltigen Loeschen des Kanals",
          len(vergessen) >= 2,
          f"-> nur in {vergessen}; sonst bleibt der Zustand einer geloeschten "
          f"Ticketnummer stehen")

    # Die DM darf kein content= benutzen -- mit V2 lehnt Discord das ab.
    dm = strip_py(open(os.path.join(BOT, "utils/ticket_dm.py"), encoding="utf-8").read())
    check("DM nutzt kein content=", "content=" not in dm,
          "-> mit Components V2 antwortet Discord mit 50035")
    check("DM ist Components V2", "LayoutView" in dm and "Container" in dm)
    check("DM hat einen Link-Knopf", "ButtonStyle.link" in dm)


# ── 12. Die DM laesst sich wirklich bauen ────────────────────────────

def test_dm_baut():
    print("\n12. Die DM-Nachricht laesst sich bauen")
    from utils import ticket_dm

    v = ticket_dm.build_user_dm(
        guild_name="LSPD I Dunya",
        kanal_url="https://discord.com/channels/1/2/3",
        ticket_nr=42,
    )
    check("Nutzer-DM gebaut", v is not None)
    # Genau ein Baustein auf oberster Ebene: der Container. Der Knopf
    # gehoert hinein, nicht daneben -- eine ActionRow direkt in der
    # LayoutView rendert ausserhalb der Karte. test_v2_buttons.py
    # prueft dieselbe Regel fuer das ganze Repo.
    check("nur der Container auf oberster Ebene", len(v.children) == 1,
          f"({len(v.children)} Bausteine -> ein Knopf sitzt ausserhalb der Karte)")

    container = v.children[0]
    hat_knopf = any(
        type(kind).__name__ == "ActionRow" for kind in getattr(container, "children", [])
    )
    check("der Knopf sitzt im Container", hat_knopf)

    v2 = ticket_dm.build_staff_dm(
        guild_name="LSPD I Dunya",
        kanal_url="https://discord.com/channels/1/2/3",
        user_name="Fufi",
        ticket_nr=42,
    )
    check("Team-DM gebaut", v2 is not None)
    check("die beiden sind verschieden farbig",
          ticket_dm.FARBE_ANTWORT != ticket_dm.FARBE_WARTET)


async def main():
    with tempfile.TemporaryDirectory() as tmp:
        alt = os.getcwd()
        os.chdir(tmp)
        try:
            await test_schalter()
            await test_frisches_ticket()
            await test_wartezeit()
            await test_nutzer_war_da()
            await test_sperrzeit()
            await test_team_richtung()
            await test_sleep()
            await test_ruhezeit()
            await test_einstellungen()
            await test_hintergrundlauf()
        finally:
            os.chdir(alt)

    test_verdrahtung()
    test_dm_baut()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Ticket-Benachrichtigungen: alle Pruefungen bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
