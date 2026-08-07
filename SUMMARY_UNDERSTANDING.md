# Oskar-Bot / University Bot – Vollständige Analyse & Verständnis (Main Branch)

**Repo:** https://github.com/Fufi1925/Oskar-Bot.git (nur `main`)
**Klon-Datum:** 2026-08-07
**Ziel:** Alles verstehen – Architektur, Features, Code-Flow, Deployment, Probleme.

---

## 1. Überblick (High-Level)

**University Bot** (auch "Oskar-Bot", "universitybot X", "CODEx" etc. genannt) ist ein **feature-reicher Discord-Bot + modernes Web-Dashboard**, das **als EIN einziges Railway-Deployment** läuft.

- **Ein Container, ein Port (8080)**.
- Bot (Python + discord.py) + FastAPI Backend + Next.js 14 Dashboard laufen zusammen.
- Ziel: Alles über eine URL erreichbar (https://dein-app.up.railway.app).

**Kern-Features:**
- **17 Antinuke-Module** (sehr stark: Anti-Ban, Anti-Kick, Anti-Channel/Role/Webhook Flood, etc.)
- **Automod** (Anti-Spam, Anti-Caps, Anti-Links, Anti-Invites, etc.)
- **Musik** mit Lavalink v4 (YouTube, SoundCloud, JioSaavn)
- **12+ Minispiele** (Chess, Battleship, Wordle, 2048, TicTacToe, Country Guess, Memory, Lights Out, ... + Blackjack/Slots)
- **Leveling + XP + Leaderboard**
- **Tickets**, Giveaways, Verification, Join-to-Create Voice, Birthday, AFK, Autorole, Autoresponder, Reaction Roles, Vanity Roles, Custom Roles, Nitro, QR, Encryption, etc.
- **Dashboard** (Next.js): Per-Server-Konfiguration für fast alles + Admin-Panel + OAuth2 Login (Discord)

**Branding:** University Bot / Oskar-Bot / CODEx (inkonsistent im Code).

---

## 2. Architektur & Technischer Aufbau

### Gesamtdiagramm (Railway)

```
Railway Container
├── start.sh
│   ├── node server.js (Next.js Standalone, Port 3000)
│   └── python university_bot.py
│       ├── discord.py Bot (AutoShardedBot)
│       │   ├── 100+ Cogs (Commands + Events + Antinuke + Automod)
│       │   └── setup_hook → load_extensions("cogs")
│       └── FastAPI (uvicorn, Port 8080)
│           ├── /api/v1/*   → Bot-API (mit verify_api_key + Rate Limit)
│           ├── /health
│           └── /*          → Proxy zu Next.js (inkl. NextAuth /api/auth/*)
└── Phantom (optionaler separater Ticket-Bot unter /phantom)
```

**Wichtige Mechanismen:**
- **start.sh** wartet auf Dashboard-Readiness (curl), startet dann Bot.
- Bot startet **FastAPI in einem Daemon-Thread**.
- FastAPI **proxyt** alle nicht-API-Routen an Next.js weiter (inkl. korrektem Set-Cookie-Handling für NextAuth).
- Alle DBs: **35 separate SQLite-Dateien** in `bot/db/` (keine ORM/Migrationen, jedes Modul legt seine Tabellen selbst an).
- **Kein Connection Pooling** im Bot (jeder aiosqlite.connect öffnet neu).

### Bot (Python)
- **Einstieg:** `bot/university_bot.py` (Setup, Events, FastAPI-Start, Command-Logging)
- **Bot-Klasse:** `bot/core/universitybot.py`
  - `get_prefix()` → liest **bei jeder Nachricht** aus DB (Prefix + No-Prefix-Cache)
  - Presence-Rotation alle 15s (viele Texte mit Emojis)
  - No-Prefix-Whitelist (Users + Roles) → cached + refresh alle 60s
- **Cogs laden:** Manuell in `bot/cogs/__init__.py` (~140 `add_cog()` Aufrufe)
  - Struktur: `commands/`, `events/`, `antinuke/`, `automod/`, `moderation/`, `universitybot/` (Hilfe-Texte)
- **Core:** Context, Cog-Base

### API (FastAPI)
- `bot/api/server.py`
- `/api/v1` Sub-App mit `verify_api_key`
- Router: bot, guilds (55 Endpoints!), admin, moderation, actions, tickets, leveling, antinuke, automod, ...
- **Proxy** für Dashboard + NextAuth
- Rate-Limiting (SlowAPI + custom)
- Viele Pydantic-Schemas

### Dashboard (Next.js 14)
- App Router + Tailwind + Radix + lucide + sonner
- NextAuth (Discord Provider, JWT 30 Tage)
- i18n (DE/EN) via LanguageContext + DOM-Translationen
- ~23 Guild-Konfig-Seiten + Admin-Dashboard + Overview + Leaderboard
- Client-Calls gehen über Next.js Route-Handler (sollten Key nicht leaken)
- **Probleme (siehe unten)**

### Phantom (isolierter Stack)
- Unter `/phantom`
- Eigenes Dashboard + Ticket-Bot (separater Token möglich)
- Für "Phantom Tickets"

---

## 3. Wichtige Verzeichnisse & Dateien

| Pfad                        | Inhalt                                      | Bemerkung |
|-----------------------------|---------------------------------------------|---------|
| `bot/university_bot.py`    | Main Entry + FastAPI Thread + Events       | Wichtigster Einstieg |
| `bot/core/universitybot.py`| Bot-Klasse, Prefix, Presence, No-Prefix    | Kern |
| `bot/cogs/__init__.py`     | Alle Cogs manuell registriert (~140)       | Sehr lang |
| `bot/cogs/commands/`       | 60+ Commands (ai, leveling, music, tickets...) | |
| `bot/cogs/antinuke/`       | 17 Anti-Module                             | Herzstück |
| `bot/cogs/automod/`        | 6 Anti-Module                              | |
| `bot/cogs/moderation/`     | Ban, Kick, Mute, Warn etc.                 | |
| `bot/api/`                 | FastAPI + Routes + Schemas                 | |
| `bot/api/routes/guilds.py` | ~1000 Zeilen Guild-Config (viele Module)   | Zentral |
| `bot/api/server.py`        | App + Proxy + Middleware                   | |
| `bot/db/`                  | 35 SQLite DBs (leer nach Klon)             | Wird zur Laufzeit angelegt |
| `dashboard/`               | Next.js 14 App                             | |
| `dashboard/app/dashboard/guild/[id]/...` | Viele Config-Seiten | |
| `start.sh`                 | Orchestrierung                             | Sehr defensiv |
| `Dockerfile`               | Multi-Stage (Node Build + Python + Node 18) | |
| `.env.example`             | Alle Config-Variablen (gut dokumentiert)   | |
| `CODE_ANALYSE.md`          | Sehr detaillierte frühere Analyse          | Lesen! |

Weitere: `games/`, `utils/`, `phantom/`, `tools/`, `statusbot/`

---

## 4. Features im Detail (Auswahl)

**Sicherheit:**
- 17 Antinuke (AntiBan, AntiKick, AntiChannelCreate/Delete/Update, AntiRole*, AntiWebhook*, AntiGuild, AntiPrune, AntiIntegration, AntiEveryone, AntiMassMention via Automod)
- Whitelist / Emergency Lockdown
- Automod mit DB-Tracking

**Musik:**
- wavelink + Lavalink
- Queue, Loop, Autoplay, Shuffle, Filters

**Spiele:**
- Separate Games-Ordner + Commands/Games.py
- Chess, Battleship, Connect4, Wordle, 2048, TicTacToe, CountryGuess, Memory, LightsOut, NumberSlider, TypeRacer, RPS, Blackjack, Slots

**Engagement:**
- Leveling (XP, Rank-Cards mit Pillow)
- Tickets (volles System mit Kategorien)
- Giveaways, Verification (Captcha?), Join-to-Create, Autorole, Reaction Roles, Vanity Roles, Custom Roles, Booster, Sticky Messages, AFK, Birthday, Counting, etc.

**Sonstiges:**
- AI (Groq + Google Gemini + OpenAI)
- Minecraft Status, YouTube, Translate, QR, Encryption, Nitro, Image Commands
- Logging (viele Kategorien)
- Invite Tracking + Leaderboard
- No-Prefix für bestimmte User/Rollen
- Nickname Rules (Prefix/Suffix nach Rolle)

**Dashboard:**
- OAuth Login → Guild-Auswahl → Tabs für fast jedes Modul
- Live-Stats, Admin-Panel mit Quick-Actions (ban/kick etc. mit Permission-Checks)
- Config Export/Import
- Module-Status Overview

---

## 5. Konfiguration & Deployment

### .env (wichtigste Vars)
- `TOKEN`, `OWNER_IDS`
- `DASHBOARD_API_KEY` (stark! **nie** als NEXT_PUBLIC_*)
- `DISCORD_CLIENT_ID/SECRET`
- `NEXTAUTH_SECRET/URL`
- Lavalink, GIPHY, GOOGLE/GROQ API Keys
- `DASHBOARD_URL`, `PARTNER_*` für Anti-Nuke Recovery

Siehe `.env.example` für vollständige Erklärung.

### Lokal starten
```bash
# 1. .env anlegen
cp .env.example .env

# 2. Bot
cd bot
pip install -r requirements.txt
python university_bot.py   # (API + Bot)

# 3. Dashboard (separat)
cd ../dashboard
npm install
npm run dev
```

**Besser:** `./start.sh` (wie im Container)

### Railway
- Siehe `RAILWAY_DEPLOYMENT.md`
- Volume für `/data` (für DBs) empfohlen
- `DATA_DIR=/data`
- OAuth Redirect: `https://.../api/auth/callback/discord`

---

## 6. Bekannte Probleme & Kritische Befunde (aus CODE_ANALYSE.md + eigener Sicht)

**🔴 Sicherheit (kritisch)**
- `NEXT_PUBLIC_DASHBOARD_API_KEY` wird teilweise noch verwendet → Key im Browser!
- **Keine Guild-Autorisierung** in den meisten `/guilds/{id}/*` Endpoints (jeder mit Key kann jede Guild konfigurieren)
- `verify_api_key` erlaubt localhost ohne Key (Proxy kommt von dort)
- Hardcodierter Giphy-Key in `fun.py`
- `eval()` in calc.py + autorole.py

**🟠 Deployment / Stabilität**
- `pillow` war auskommentiert → jetzt in requirements.txt (gut)
- Viele fehlende Ordner/DBs beim ersten Start (db/, instructions/, channels.json)
- 35 SQLite-Dateien ohne Pooling → hohe I/O
- `get_prefix()` öffnet DBs bei **jeder** Nachricht
- Dockerfile Node-Version nicht perfekt gepinnt
- Viele bare `except:`

**🟡 Code-Qualität**
- Sehr viele manuelle Cog-Registrierungen
- Obfuskierte Dateien (leveling, verification, ai, booster) – schwer wartbar
- Inkonsistentes Branding
- Viele tote Dateien / doppelte Routen
- 50 Fake-Admin-Feature-Flags (nicht implementiert)
- Hardcodierte IDs im Code

**Positives:**
- Proxy-Lösung elegant (ein Port)
- start.sh sehr robust
- Viele Permission-Checks im Admin-Bereich
- Gute Modularität der Features
- Detaillierte .env.example + Docs

---

## 7. Code-Flow (wichtige Pfade)

1. `start.sh` → Dashboard (3000) + Bot
2. `university_bot.py`:
   - `_prepare_storage()` + bootstrap
   - `universitybot()` Client
   - `keep_alive()` → FastAPI-Thread
   - `client.start(TOKEN)`
3. `setup_hook()` → Feature-Flags, Gates, load_extensions("cogs")
4. Bei Nachricht: `get_prefix()` → DB + No-Prefix-Cache → `process_commands`
5. Dashboard-Request → Proxy oder `/api/v1/guilds/...` → db_manager + Bot-Aktion

---

## 8. Nächste Schritte / Empfehlungen (falls du es nutzen/modifizieren willst)

1. **Sicherheit zuerst**:
   - API-Key komplett serverseitig machen
   - Guild-Permission-Checks (MANAGE_GUILD + Session)
   - Keys aus .env holen

2. **Stabilität**:
   - DB-Pooling oder aiosqlite Pool
   - Prefix-Caching verbessern
   - Fehlende Dateien defensiv anlegen

3. **Weiterentwicklung**:
   - Cogs aufräumen / in Gruppen laden
   - Feature-Flags wirklich nutzen
   - Tests hinzufügen

4. **Lokal testen**:
   - `docker build -t oskar-bot .`
   - Mit Volume laufen lassen

---

**Zusammenfassung:**  
Das ist ein **sehr umfangreiches, monolithisches All-in-One-Discord-Bot-Projekt** mit starkem Fokus auf Moderation/Sicherheit + vollwertigem Dashboard. Der Ansatz "alles in einem Container" ist clever für Railway, aber bringt Komplexität (Proxy, Threads, viele DBs).

Alles verstanden? Brauchst du:
- Tiefenanalyse eines spezifischen Moduls (z.B. Antinuke)?
- Hilfe beim Laufenlassen?
- Refactoring-Vorschläge?
- Oder eine bestimmte Datei erklären?

Sag Bescheid! 🚀
