#!/usr/bin/env python3
"""Datenbankschicht: keine offenen Dateien, kein Bot-Muell im Verlauf, sichere Ablaeufe."""
import os
import sqlite3
import tempfile
import time
from pathlib import Path

DB = Path(tempfile.gettempdir()) / "lbost-runtime-test.sqlite3"
for suffix in ("", "-wal", "-shm"):
    Path(str(DB) + suffix).unlink(missing_ok=True)

os.environ.update({
    "LBOST_SHOP_DB_PATH": str(DB),
    "LBOST_SHOP_SECRET_KEY": "runtime-secret",
    "LBOST_SHOP_TOKEN_ENCRYPTION_KEY": "runtime-token-secret",
})

from lbost_shop_app import db  # noqa: E402
from lbost_shop_app.config import get_settings  # noqa: E402

settings = get_settings()
db.init_features(settings)


def offene_dateien() -> int:
    return len(list(Path("/proc/self/fd").iterdir()))


# ── 1) Kein Verbindungsleck ───────────────────────────────────────────
vorher = offene_dateien()
for _ in range(400):
    db.get_feature(11, "tickets", settings)
    db.all_features(11, settings)
nachher = offene_dateien()
assert nachher - vorher <= 2, f"Date-Descriptor-Leck: +{nachher - vorher} bei 800 Lesungen"

# Auch Schreiben duerfen keine Dateien hinterlassen
vorher = offene_dateien()
for index in range(200):
    db.set_state(11, f"kurz{index % 5}", {"i": index}, settings)
assert offene_dateien() - vorher <= 2, "set_state leckt Verbindungen"

# ── 2) Geschriebenes ist fuer einen zweiten Prozess sichtbar ─────────
db.set_feature(12, "tickets", {"enabled": True, "ticket_title": "T"}, 5, settings)
fremd = sqlite3.connect(DB)
roh = fremd.execute("SELECT data_json FROM guild_features WHERE guild_id=12").fetchone()
assert roh and "ticket_title" in roh[0], "Dashboard-Schreiben war für den Bot unsichtbar (fehlender Commit)"
fremd.close()

# ── 3) Bot-Schreiben zaehlt nicht als Konfigurationsaenderung ─────────
vorher = db.feature_history(13, settings)
db.set_feature(13, "automation", {"enabled": True}, 5, settings)
nach_user = db.feature_history(13, settings)
assert sum(p["amount"] for p in nach_user) - sum(p["amount"] for p in vorher) == 1
for _ in range(9):
    db.set_state(13, "announce:13", {"0": int(time.time()) + 60}, settings)
nach_bot = db.feature_history(13, settings)
assert sum(p["amount"] for p in nach_bot) == sum(p["amount"] for p in nach_user), "Laufzeit-Zustand taucht im Verlaufsgraphen auf"

# ── 4) Verlaufs-Aeume: audit=False schreibt trotzdem, aber leise ─────
db.set_feature(14, "automation", {"enabled": True}, 5, settings, audit=False)
with sqlite3.connect(DB) as con:
    anzahl = con.execute("SELECT COUNT(*) FROM feature_audit WHERE guild_id=14").fetchone()[0]
assert anzahl == 0, f"audit=False hat trotzdem protokolliert: {anzahl}"
assert db.get_feature(14, "automation", settings)["enabled"] is True

# ── 5) Alt-Verlauf wird weggeraeumt, frischer bleibt ─────────────────
with sqlite3.connect(DB) as con:
    con.execute("INSERT INTO feature_audit(guild_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)",
                 (15, 1, "configure:tickets", "{}", int(time.time()) - 400 * 86400))
    con.execute("INSERT INTO feature_audit(guild_id,actor_id,action,details,created_at) VALUES(?,?,?,?,?)",
                (15, 1, "configure:tickets", "{}", int(time.time()) - 60))
    con.commit()
db.prune_audit(settings)
with sqlite3.connect(DB) as con:
    reste = con.execute("SELECT COUNT(*) FROM feature_audit WHERE guild_id=15").fetchone()[0]
assert reste == 1, f"Prune hat {reste} statt 1 frischem Eintrag behalten"

# ── 6) Verwarnungen: Fallnummern, Zahl, Loeschen ────────────────────
erste = db.warnung_anlegen(16, 500, 900, "Spam", settings)
zweite = db.warnung_anlegen(16, 500, 900, "Links", settings)
assert (erste, zweite) == (1, 2), (erste, zweite)
assert db.warnungen_fuer_nutzer(16, 500, settings) == 2
assert db.warnungen_fuer_nutzer(16, 999, settings) == 0
eintrag = db.warnungen_fuer_gilde(16, settings, 10)[0]
assert eintrag["case_number"] == 2 and eintrag["user_id"] == 500
assert db.warnung_loeschen(16, int(eintrag["id"]), settings) is True
assert db.warnung_loeschen(16, int(eintrag["id"]), settings) is False, "zweites Loeschen meldet Erfolg"
assert db.warnungen_fuer_nutzer(16, 500, settings) == 1
# Fremder Server kommt nicht an die Zeile des anderen Servers
assert db.warnung_loeschen(17, 1, settings) is False

# ── 7) Tickets: Nummer, Zahl, Status ────────────────────────────────
assert db.naechste_ticket_nummer(18, settings) == 1
db.ticket_anlegen(18, 111, 222, "default", 1, [{"label": "x", "type": "short", "value": "y"}], settings)
db.ticket_anlegen(18, 112, 333, "billing", 2, [], settings)
assert db.naechste_ticket_nummer(18, settings) == 3
kennzahlen = db.ticket_kennzahlen(18, settings)
assert kennzahlen["offen"] == 2 and kennzahlen["gesamt"] == 2 and kennzahlen["neu_7_tage"] == 2
db.ticket_setzen(111, settings, claimed_by=900)
assert db.ticket_kennzahlen(18, settings)["beansprucht"] == 1
db.ticket_setzen(111, settings, status="closed", closed_at=int(time.time()), closed_by=900)
nach = db.ticket_kennzahlen(18, settings)
assert nach["offen"] == 1 and nach["geschlossen"] == 1
assert db.offene_tickets_fuer_nutzer(18, 333, settings) == 112
assert db.offene_tickets_fuer_nutzer(18, 222, settings) is None, "geschlossenes Ticket gilt als offen"
# Unbekannte Felder duerfen nicht in die SQL gelangen
db.ticket_setzen(112, settings, status="deleted", bose="spaltname")
assert db.ticket_fuer_kanal(112, settings)["status"] == "deleted"
assert db.offene_tickets_fuer_nutzer(18, 333, settings) is None

# ── 8) Giveaways: Teilnahmepruefung und nur ein Abschluss ───────────
db.giveaway_anlegen(777, 19, 1, "Preis", 2, int(time.time()) + 600, settings)
assert db.giveaway_beitreten(777, 5, settings) == "beitritt"
assert db.giveaway_beitreten(777, 5, settings) == "bereits"
assert db.giveaway_beitreten(777, 6, settings) == "beitritt"
assert db.giveaway_teilnehmer(777, settings) == [5, 6]
assert db.giveaway_beitreten(778, 5, settings) == "unbekannt"
belegt = db.giveaway_belegen(777, settings)
assert belegt and belegt["status"] == "ending", belegt
assert db.giveaway_belegen(777, settings) is None, "zweiter Lauf darf denselben Wettbewerb nochmal eroeffnen"
db.giveaway_abschliessen(777, [5], settings)
assert db.giveaway_beitreten(777, 9, settings) == "beendet"
abgeschlossen = db.giveaways_fuer_gilde(19, settings, 5)[0]
assert abgeschlossen["status"] == "ended" and abgeschlossen["winner_ids"] == "[5]"

# ── 9) Sitzungen ─────────────────────────────────────────────────────
db.save_oauth_session("s-1", 500, {"access_token": "geheimer-zugriffswert", "refresh_token": "geheimer-frischwert", "expires_in": 60}, settings)
db.save_oauth_session("s-2", 501, {"access_token": "b", "refresh_token": "c", "expires_in": 60}, settings)
with sqlite3.connect(DB) as con:
    zeile = con.execute("SELECT access_token, refresh_token FROM oauth_sessions WHERE session_id='s-1'").fetchone()
assert b"geheimer-zugriffswert" not in zeile[0] and b"geheimer-frischwert" not in zeile[1], "Token liegt unverschluesselt in der Datei"
assert zeile[0][:6] == b"gAAAAA", "kein Fernet-Schluesseltext -> Verschluesselung laeuft nicht"
assert db.offene_sitzungen(settings) and len(db.offene_sitzungen(settings)) == 2
assert db.alle_sitzungen_loeschen(settings) == 2
assert db.offene_sitzungen(settings) == []

# ── 10) Alte Datenbank ohne neuen Spalten laeuft weiter ──────────────
ALT = Path(tempfile.gettempdir()) / "lbost-alt.sqlite3"
for suffix in ("", "-wal", "-shm"):
    Path(str(ALT) + suffix).unlink(missing_ok=True)
with sqlite3.connect(ALT) as con:
    con.executescript("""
    CREATE TABLE guild_features (guild_id INTEGER NOT NULL, feature TEXT NOT NULL,
        data_json TEXT NOT NULL DEFAULT '{}', updated_at INTEGER NOT NULL, PRIMARY KEY (guild_id, feature));
    CREATE TABLE feature_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        actor_id INTEGER NOT NULL, action TEXT NOT NULL, details TEXT NOT NULL, created_at INTEGER NOT NULL);
    CREATE TABLE tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        channel_id INTEGER UNIQUE NOT NULL, owner_id INTEGER NOT NULL, panel_key TEXT NOT NULL,
        claimed_by INTEGER, status TEXT NOT NULL DEFAULT 'open', created_at INTEGER NOT NULL, closed_at INTEGER);
    CREATE TABLE warnings (id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL, moderator_id INTEGER NOT NULL, reason TEXT NOT NULL, created_at INTEGER NOT NULL);
    CREATE TABLE giveaways (message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL,
        prize TEXT NOT NULL, winners INTEGER NOT NULL, ends_at INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', winner_ids TEXT NOT NULL DEFAULT '[]');
    CREATE TABLE giveaway_entries (message_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY(message_id,user_id));
    """)
    con.execute("INSERT INTO tickets(guild_id,channel_id,owner_id,panel_key,created_at) VALUES(1,1,1,'default',1)")
    con.commit()
settings_alt = get_settings()
settings_alt.db_path = str(ALT)
db.reset_schema_cache()
db.init_features(settings_alt)
assert db.naechste_ticket_nummer(1, settings_alt) == 2
assert db.ticket_fuer_kanal(1, settings_alt)["ticket_number"] == 0
assert db.warnung_anlegen(1, 2, 3, "Grund", settings_alt) == 1
db.reset_schema_cache()

print("ok   keine Lecks, saubere Verlaeufe, Fallnummern, ein Abschluss pro Giveaway")
