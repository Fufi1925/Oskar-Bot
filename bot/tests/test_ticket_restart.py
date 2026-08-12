#!/usr/bin/env python3
"""
Tickets nach einem Neustart, der Zaehler und der Proxy-Bereich.

Drei gemeldete Fehler:

  1. Nach einem Deploy tun die Knoepfe in offenen Tickets nichts mehr.
  2. "3 von 3 offen", obwohl die Kanaele von Hand geloescht wurden.
  3. "Unknown API scope" beim Anlegen eines Bewerbungs-Panels.

Der Zaehler-Abgleich wird wirklich ausgefuehrt -- mit einer Attrappe
fuer Discord, damit sich "Kanal weg" und "Kanal da" trennen lassen.

Run:  python3 tests/test_ticket_restart.py
"""

import ast
import os
import re
import sqlite3
import sys
import tempfile

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


ROH = read("cogs/commands/ticket.py")
BAUM = ast.parse(ROH)


def funktion(name):
    for k in ast.walk(BAUM):
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef)) and k.name == name:
            return k
    return None


# ── 1. Die Knoepfe nach einem Neustart ───────────────────────────────

def test_knoepfe_ueberleben():
    print("\n1. Die Knoepfe im Ticket ueberleben einen Deploy")

    # Jeder Knopf braucht eine feste ID -- ohne die kann Discord die
    # Interaktion nach einem Neustart gar nicht zuordnen.
    knopf_ids = set(re.findall(r'custom_id="((?:t|c)_[a-z]+)"', ROH))
    check("die Knoepfe im offenen Ticket haben IDs",
          {"t_lock", "t_unlock", "t_claim", "t_close"} <= knopf_ids,
          f"({sorted(knopf_ids)})")
    check("die Knoepfe im geschlossenen Ticket auch",
          {"c_reopen", "c_transcript", "c_delete"} <= knopf_ids,
          "-> ohne ID kommt die Interaktion nirgends an")

    # Und jeder muss abgefangen werden. Die Tabelle im Cog ist die
    # Zuordnung; fehlt einer, tut genau der nichts.
    tabelle = re.search(r"TICKET_BUTTONS\s*=\s*\{(.*?)\n    \}", ROH, re.S)
    check("es gibt eine Zuordnungstabelle", tabelle is not None)
    bekannt = set(re.findall(r'"((?:t|c)_[a-z]+)":', tabelle.group(1))) if tabelle else set()
    fehlend = knopf_ids - bekannt
    check("jeder Knopf ist darin eingetragen", not fehlend,
          f"-> {sorted(fehlend)} tun nach einem Deploy nichts")

    # Der Listener muss die Tabelle auch benutzen.
    oi = funktion("on_interaction")
    quelle = ast.get_source_segment(ROH, oi) if oi else ""
    check("der Listener wertet sie aus", "TICKET_BUTTONS" in quelle)
    check("und ruft die Verteilung auf", "_dispatch_ticket_button" in quelle)

    # Die Verteilung baut den View neu und prueft die Rechte weiter.
    dispatch = funktion("_dispatch_ticket_button")
    dq = ast.get_source_segment(ROH, dispatch) if dispatch else ""
    check("der View wird neu gebaut",
          "TicketActionsView(" in dq and "ClosedTicketActionsView(" in dq)
    check("die Rollenpruefung gilt weiter", "interaction_check" in dq,
          "-> sonst duerfte nach einem Neustart jeder das Ticket schliessen")
    check("offene und geschlossene Tickets werden getrennt",
          "closed_at" in dq)

    # add_view waere hier falsch -- das ist der Punkt, der leicht
    # uebersehen wird, deshalb ausdruecklich geprueft.
    lpv = funktion("load_persistent_views")
    lq = ast.get_source_segment(ROH, lpv) if lpv else ""
    check("die Ticket-Views werden NICHT ueber add_view registriert",
          "add_view(TicketActionsView" not in lq
          and "add_view(view)" not in lq,
          "-> gleiche custom_ids ohne message_id ueberschreiben sich")


# ── 2. Der Zaehler ───────────────────────────────────────────────────

def test_zaehler_code():
    print("\n2. Der Zaehler bei geloeschten Kanaelen")
    check("auf geloeschte Kanaele wird reagiert",
          funktion("on_guild_channel_delete") is not None,
          "-> ein von Hand geloeschter Kanal laesst den Zaehler stehen")

    delete = funktion("on_guild_channel_delete")
    dq = ast.get_source_segment(ROH, delete) if delete else ""
    check("der Listener ist registriert",
          any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "listener"
              for d in (delete.decorator_list if delete else [])),
          "-> ohne Dekorator wird er nie aufgerufen")
    check("er senkt den Zaehler", "ticket_count-1" in dq.replace(" ", ""))
    check("er zaehlt geschlossene Tickets nicht doppelt", "closed_at" in dq,
          "-> die haben den Zaehler schon gesenkt")
    check("er raeumt die Zeile weg", "DELETE FROM open_tickets" in dq)

    check("es gibt einen Abgleich beim Start",
          funktion("reconcile_counts") is not None,
          "-> ein bereits falscher Stand bliebe fuer immer stehen")


def test_zaehler_wirkung():
    """
    Der Abgleich wird ausgefuehrt.

    Die Pruefungen oben lesen den Quelltext; das faengt eine geloeschte
    Zeile, aber keine, die dasteht und nichts tut.
    """
    print("\n   -- der Abgleich, wirklich ausgefuehrt --")

    import asyncio

    from cogs.commands.ticket import TicketCog

    with tempfile.TemporaryDirectory() as tmp:
        pfad = os.path.join(tmp, "t.db")
        conn = sqlite3.connect(pfad)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE open_tickets (channel_id INTEGER PRIMARY KEY,
                ticket_number INTEGER, guild_id INTEGER, creator_id INTEGER,
                category_db_id INTEGER, created_at TEXT, closed_by_id INTEGER,
                closed_at TEXT, is_locked BOOLEAN, is_claimed BOOLEAN,
                claimed_by_id INTEGER);
            CREATE TABLE user_ticket_counts (guild_id INTEGER, user_id INTEGER,
                ticket_count INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id));
        """)
        # Drei offene Tickets, der Zaehler steht auf 3.
        for kanal in (101, 102, 103):
            conn.execute(
                "INSERT INTO open_tickets VALUES (?,1,7,42,1,'now',NULL,NULL,0,0,NULL)",
                (kanal,),
            )
        # Dazu ein GESCHLOSSENES, dessen Kanal ebenfalls weg ist. Es hat
        # den Zaehler beim Schliessen schon gesenkt und darf hier nicht
        # noch einmal abgezogen werden -- ohne diesen Fall faellt ein
        # fehlender `WHERE closed_at IS NULL` gar nicht auf.
        conn.execute(
            "INSERT INTO open_tickets VALUES (104,4,7,42,1,'now',9,'gestern',0,0,NULL)"
        )
        conn.execute("INSERT INTO user_ticket_counts VALUES (7,42,3)")
        conn.commit()

        class FakeDB:
            def fetchall(self, q, p=()):
                return conn.execute(q, p).fetchall()

            def fetchone(self, q, p=()):
                return conn.execute(q, p).fetchone()

            def execute(self, q, p=()):
                with conn:
                    return conn.execute(q, p)

        class FakeBot:
            def __init__(self, vorhanden):
                self.vorhanden = vorhanden

            def get_channel(self, cid):
                # Nur die Kanaele, die es noch gibt.
                return object() if cid in self.vorhanden else None

        cog = TicketCog.__new__(TicketCog)
        cog.db = FakeDB()
        # Zwei der drei Kanaele wurden von Hand geloescht.
        cog.bot = FakeBot({101})

        asyncio.run(cog.reconcile_counts())

        stand = conn.execute(
            "SELECT ticket_count FROM user_ticket_counts WHERE user_id=42"
        ).fetchone()[0]
        check("der Zaehler faellt auf die echten Tickets", stand == 1,
              f"(steht auf {stand}, es gibt aber nur einen Kanal)")

        uebrig = sorted(r[0] for r in conn.execute("SELECT channel_id FROM open_tickets"))
        check("die verwaisten offenen Zeilen sind weg", 102 not in uebrig
              and 103 not in uebrig, f"({uebrig})")
        check("das bestehende Ticket bleibt", 101 in uebrig, f"({uebrig})")
        check("das geschlossene wird nicht angefasst", 104 in uebrig,
              f"-> der Abgleich raeumt zu viel weg: {uebrig}")

        # Ein zweiter Lauf darf nichts weiter abziehen.
        asyncio.run(cog.reconcile_counts())
        stand2 = conn.execute(
            "SELECT ticket_count FROM user_ticket_counts WHERE user_id=42"
        ).fetchone()[0]
        check("ein zweiter Lauf aendert nichts", stand2 == 1, f"({stand2})")

        # Und wenn alles noch da ist, bleibt der Stand.
        cog.bot = FakeBot({101})
        asyncio.run(cog.reconcile_counts())
        check("bestehende Tickets bleiben unangetastet",
              conn.execute("SELECT COUNT(*) FROM open_tickets").fetchone()[0] == 2)
        conn.close()


# ── 3. Der Proxy-Bereich ─────────────────────────────────────────────

def test_listener_wirkung():
    """
    on_guild_channel_delete und die Knopf-Verteilung werden AUSGEFUEHRT.

    Die Pruefungen oben lesen nur den Quelltext. Das faengt eine
    geloeschte Zeile, aber keine, die dasteht und nichts mehr tut.
    """
    print("\n   -- Listener und Verteilung, wirklich ausgefuehrt --")

    import asyncio

    from cogs.commands.ticket import TicketCog

    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(os.path.join(tmp, "t.db"))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE open_tickets (channel_id INTEGER PRIMARY KEY,
                ticket_number INTEGER, guild_id INTEGER, creator_id INTEGER,
                category_db_id INTEGER, created_at TEXT, closed_by_id INTEGER,
                closed_at TEXT, is_locked BOOLEAN, is_claimed BOOLEAN,
                claimed_by_id INTEGER);
            CREATE TABLE user_ticket_counts (guild_id INTEGER, user_id INTEGER,
                ticket_count INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id));
        """)
        conn.execute(
            "INSERT INTO open_tickets VALUES (201,1,7,42,1,'now',NULL,NULL,0,0,NULL)"
        )
        # Ein geschlossenes: sein Zaehler ist schon gesenkt.
        conn.execute(
            "INSERT INTO open_tickets VALUES (202,2,7,42,1,'now',9,'gestern',0,0,NULL)"
        )
        conn.execute("INSERT INTO user_ticket_counts VALUES (7,42,2)")
        conn.commit()

        class FakeDB:
            def fetchall(self, q, p=()):
                return conn.execute(q, p).fetchall()

            def fetchone(self, q, p=()):
                return conn.execute(q, p).fetchone()

            def execute(self, q, p=()):
                with conn:
                    return conn.execute(q, p)

        class FakeGuild:
            id = 7

        class FakeChannel:
            def __init__(self, cid):
                self.id = cid
                self.guild = FakeGuild()

        cog = TicketCog.__new__(TicketCog)
        cog.db = FakeDB()

        def stand():
            return conn.execute(
                "SELECT ticket_count FROM user_ticket_counts WHERE user_id=42"
            ).fetchone()[0]

        # Ein OFFENES Ticket verschwindet -> Zaehler sinkt.
        asyncio.run(cog.on_guild_channel_delete(FakeChannel(201)))
        check("ein geloeschtes offenes Ticket senkt den Zaehler", stand() == 1,
              f"(steht auf {stand()})")
        check("und die Zeile ist weg",
              conn.execute("SELECT COUNT(*) FROM open_tickets WHERE channel_id=201")
              .fetchone()[0] == 0)

        # Ein GESCHLOSSENES verschwindet -> Zaehler bleibt.
        asyncio.run(cog.on_guild_channel_delete(FakeChannel(202)))
        check("ein geschlossenes Ticket zaehlt nicht doppelt", stand() == 1,
              f"(steht auf {stand()} -- der Zaehler war beim Schliessen schon unten)")

        # Ein fremder Kanal darf gar nichts tun.
        asyncio.run(cog.on_guild_channel_delete(FakeChannel(999)))
        check("ein fremder Kanal aendert nichts", stand() == 1, f"({stand()})")
        conn.close()

    # Die Knopf-Verteilung: baut sie den richtigen View?
    with tempfile.TemporaryDirectory() as tmp:
        conn = sqlite3.connect(os.path.join(tmp, "t2.db"))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE open_tickets (channel_id INTEGER PRIMARY KEY,
                ticket_number INTEGER, guild_id INTEGER, creator_id INTEGER,
                category_db_id INTEGER, created_at TEXT, closed_by_id INTEGER,
                closed_at TEXT, is_locked BOOLEAN, is_claimed BOOLEAN,
                claimed_by_id INTEGER);
            CREATE TABLE ticket_categories (category_id INTEGER PRIMARY KEY,
                guild_id INTEGER, name TEXT, emoji TEXT, notified_roles TEXT,
                button_style INTEGER, discord_category_id INTEGER);
        """)
        conn.execute(
            "INSERT INTO open_tickets VALUES (301,1,7,42,5,'now',NULL,NULL,0,0,NULL)"
        )
        conn.execute(
            "INSERT INTO open_tickets VALUES (302,2,7,42,5,'now',9,'gestern',0,0,NULL)"
        )
        conn.execute(
            "INSERT INTO ticket_categories VALUES (5,7,'Support','',NULL,1,99)"
        )
        conn.commit()

        class FakeDB2:
            def fetchone(self, q, p=()):
                return conn.execute(q, p).fetchone()

            def fetchall(self, q, p=()):
                return conn.execute(q, p).fetchall()

            def execute(self, q, p=()):
                with conn:
                    return conn.execute(q, p)

        gesendet = []

        class FakeResponse:
            def is_done(self):
                return False

            async def send_message(self, text, **kw):
                gesendet.append(text)

        class FakeInter:
            def __init__(self, kanal):
                self.channel_id = kanal
                self.response = FakeResponse()

        cog = TicketCog.__new__(TicketCog)
        cog.db = FakeDB2()

        # Ein Knopf des OFFENEN Tickets auf einem GESCHLOSSENEN --
        # das muss auffallen, statt etwas Falsches zu tun.
        asyncio.run(cog._dispatch_ticket_button(FakeInter(302), "t_close"))
        check("ein Knopf am falschen Stand wird abgelehnt",
              gesendet and "anderen Stand" in gesendet[0],
              f"({gesendet})")

        # Ein unbekannter Kanal ebenso.
        gesendet.clear()
        asyncio.run(cog._dispatch_ticket_button(FakeInter(999), "t_close"))
        check("ein unbekanntes Ticket wird gemeldet",
              gesendet and "Datenbank" in gesendet[0], f"({gesendet})")

        # Und der richtige Fall kommt bis zur Rollenpruefung. Die
        # Kategorie hat keine Rollen -> interaction_check lehnt ab und
        # sagt das. Genau dieser Weg belegt, dass der View wirklich
        # gebaut und benutzt wird.
        gesendet.clear()
        asyncio.run(cog._dispatch_ticket_button(FakeInter(301), "t_close"))
        check("beim richtigen Stand wird der View gebaut und geprueft",
              gesendet and "misconfigured" in gesendet[0].lower(),
              f"-> die Rollenpruefung des Views lief nicht: {gesendet}")
        conn.close()

    # Und der Abgleich muss beim Start wirklich aufgerufen werden.
    lpv = funktion("load_persistent_views")
    aufgerufen = any(
        isinstance(k, ast.Call)
        and ast.unparse(k).startswith("self.reconcile_counts")
        for k in ast.walk(lpv)
    ) if lpv else False
    check("der Abgleich laeuft beim Start", aufgerufen,
          "-> ein bereits falscher Stand bliebe fuer immer stehen")


def test_proxy_bereich():
    print("\n3. Der Dashboard-Proxy kennt /applications")
    proxy = open(
        os.path.join(DASH, "app/api/bot/[...path]/route.ts"), encoding="utf-8"
    ).read()
    ohne = "\n".join(
        z for z in re.sub(r"/\*.*?\*/", "", proxy, flags=re.S).splitlines()
        if not z.strip().startswith("//")
    )
    bereiche = set(re.findall(r'scope === "([a-z-]+)"', ohne))
    check("applications ist eingetragen", "applications" in bereiche,
          f"-> 404 'Unknown API scope'; bekannt sind {len(bereiche)} Bereiche")

    # Jeder Reiter mit eigener API braucht hier einen Eintrag. Das ist
    # inzwischen sechsmal vergessen worden, also wird es mitgeprueft.
    tabs = open(os.path.join(DASH, "components/guild-tabs.tsx"),
                encoding="utf-8").read()
    slugs = set(re.findall(r'slug: "([a-z-]+)"', tabs))
    api_ts = open(os.path.join(DASH, "lib/api.ts"), encoding="utf-8").read()

    fehlend = []
    for slug in sorted(slugs):
        # Nur Reiter, die auch eine eigene API-Route unter ihrem Namen
        # ansprechen -- viele teilen sich /guilds.
        if f"/{slug}/${{guildId}}" in api_ts or f'`/{slug}/' in api_ts:
            if slug not in bereiche:
                fehlend.append(slug)
    check("jeder Reiter mit eigener Route ist im Proxy bekannt", not fehlend,
          f"-> {fehlend} bekaemen 404")


def main():
    test_knoepfe_ueberleben()
    test_zaehler_code()
    test_zaehler_wirkung()
    test_listener_wirkung()
    test_proxy_bereich()

    print("\n" + "=" * 64)
    if failures:
        print(f"{len(failures)} FEHLGESCHLAGEN")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("Tickets nach Neustart, Zaehler und Proxy: alles bestanden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
