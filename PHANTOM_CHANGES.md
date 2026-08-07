# Phantom Bot & Dashboard – Änderungen (für die Aufgabe)

## Ziele erfüllt

1. **Keine Server-Konfiguration, wo der Bot nicht drauf ist**
   - Phantom Dashboard zeigt **ausschließlich** Server aus der `bot_guilds`-Tabelle.
   - Diese Tabelle wird **ausschließlich** vom Phantom-Bot gefüllt (`on_ready`, `on_guild_join`, `on_guild_remove`, `on_guild_update` + alle 5 Minuten Sync).
   - In `/dashboard` und `/dashboard/guild/{id}` wird hart geprüft: `await dbmod.is_bot_in_guild(...)`.

2. **Bearbeiten nur, wenn Bot auf dem Server ist + User Rechte hat**
   - Beim Öffnen einer Guild-Seite wird zuerst geprüft, ob der **Bot** Mitglied ist.
   - Danach wird geprüft, ob der **eingeloggte User** Manage-Rechte hat (über seine OAuth-Guilds).
   - Wenn Bot nicht da ist → klare Fehlermeldung + Redirect.

3. **Übersicht wie beim Main Bot**
   - Dashboard-Übersicht hat jetzt eine **Live-Statistik-Reihe** (ähnlich Main-Bot):
     - Server (Bot aktiv)
     - Offene Tickets
     - Geclaimte Tickets
     - Aktive Tickets gesamt
     - Aktivität (24h)
   - Pro-Server-Seite (`/dashboard/guild/...`) hat jetzt **"Live Übersicht"** mit:
     - Offene Tickets (live)
     - Tickets gesamt
     - Letzte aktive Tickets

4. **Ticket-System komplett real + live**
   - Alle Aktionen schreiben **sofort** in die DB:
     - Ticket erstellen → `register_ticket` + `update_ticket_activity`
     - Claimen → `set_ticket_claim` + `update_ticket_activity`
     - Schließen → `delete_ticket`
   - Dashboard liest immer **live** aus `open_tickets`
   - `last_activity` Timestamp wird bei jeder Aktion aktualisiert
   - Bot synchronisiert alle Guilds, auf denen er wirklich Member ist
   - Periodischer Sync alle 5 Minuten (falls Events verpasst werden)
   - Guild-Listen werden bei Join/Remove/Update automatisch aktualisiert

---

## Was NICHT angefasst wurde

- **Main Dashboard** (`/dashboard/`) → komplett unverändert (wie gewünscht)
- Haupt-Bot (`bot/`) → unverändert
- Alle Änderungen sind **ausschließlich** im `phantom/` Ordner

---

## Wichtige neue / geänderte Dateien

| Datei                              | Änderung |
|------------------------------------|----------|
| `phantom/app/db.py`                | `bot_guilds` Tabelle + Sync-Funktionen + `get_phantom_stats()` + `get_guild_live_stats()` + `last_activity` + `update_ticket_activity` |
| `phantom/bot/ticket_bot.py`        | `on_guild_join/remove/update`, `sync_bot_guilds_to_db()`, periodischer Sync, Activity-Updates bei allen Ticket-Aktionen |
| `phantom/app/main.py`              | Strenge Filterung auf Bot-Guilds + User-Rechte + Live-Stats in beide Templates |
| `phantom/app/templates/dashboard.html` | Main-Bot-Style Live-Stats-Block |
| `phantom/app/templates/guild.html` | Live-Übersicht + erweiterte Ticket-Tabelle + Timestamps |

---

## So funktioniert es jetzt (real)

1. Phantom-Bot startet → sync't **alle** Guilds, auf denen er Member ist → `bot_guilds`
2. User loggt sich im Phantom-Dashboard ein (Discord OAuth)
3. Dashboard zeigt **nur** die Server, bei denen:
   - Der **Phantom-Bot** Member ist (aus `bot_guilds`)
   - **Der User** Manage-Rechte hat
4. User klickt auf einen Server → nur erlaubt, wenn Bot drauf ist
5. Alle Ticket-Aktionen (erstellen/claimen/schließen) sind **live** in der DB und sofort im Dashboard sichtbar

---

## Nächste Schritte (empfohlen)

```bash
# Phantom starten (im Root)
cd /home/user/Oskar-Bot

# 1. Phantom-Bot (separater Token)
PHANTOM_BOT_TOKEN=dein_phantom_token python phantom/run_bot.py

# 2. Phantom-Dashboard (wird automatisch unter /phantom gemountet)
# (wird von start.sh oder manuell gestartet)
```

Oder über das Haupt-`start.sh` (wenn `PHANTOM_BOT_TOKEN` gesetzt ist).

---

**Fazit:**  
Das Phantom-Ticket-System ist jetzt **vollständig eigenständig**, zeigt **nur reale Bot-Server**, hat **echte Live-Daten** und eine **Main-Bot-ähnliche Übersicht** – ohne dass das Haupt-Dashboard angerührt wurde.