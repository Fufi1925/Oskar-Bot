<div align="center">

# 🎓 University Bot

**Feature-rich Discord Bot + Modern Dashboard — Alles in einem Railway-Deployment**

</div>

---

## ✦ Overview

University Bot ist ein vollausgestatteter Discord Bot mit integriertem Web-Dashboard. Bot, API und Dashboard laufen zusammen als **ein einziges Projekt** — deployfertig für Railway.

```
┌──────────────────────────────────────────────────┐
│         Railway (1 Container, 1 Port)            │
│                                                   │
│  🤖 Discord Bot ──► FastAPI ──► Dashboard (SSR)  │
│  (discord.py)      (/api/v1/*)  (Next.js)         │
│                                                   │
│  Single URL: https://your-app.up.railway.app     │
└──────────────────────────────────────────────────┘
```

---

## ✦ Features

### 🛡️ Security
- **Antinuke** — 17 Schutzmodule gegen Bans, Kicks, Channel/Role/ Webhook-Flut
- **Automod** — Anti-Spam, Anti-Caps, Anti-Links, Anti-Invites, Anti-Mass-Mentions
- Whitelist/Unwhitelist, Emergency Lockdown

### 🎵 Music
- Lavalink v4 mit YouTube, SoundCloud, JioSaavn
- Queue, Loop, Autoplay, Shuffle

### 🎮 Games (12+)
Chess, Battleship, Connect Four, Wordle, 2048, TicTacToe, Country Guess, Memory, Lights Out, Number Slider, TypeRacer, RPS

### 🎉 Engagement
- Leveling + XP + Leaderboard
- Birthday Tracker, AFK, Autorole, Autoresponder
- Tickets, Giveaways, Verification
- Join-to-Create Voice

### 🌐 Dashboard
- Discord OAuth2 Login
- Per-Server Einstellungen
- Live Stats
- Alles auf einer URL

---

## ✦ Quick Deploy auf Railway

Siehe [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) für die vollständige Anleitung.

**Kurzfassung:**
1. Repository auf GitHub pushen
2. Railway → New Project → Deploy from GitHub
3. Environment Variables setzen (siehe `.env.example`)
4. Discord OAuth2 Redirect URL konfigurieren
5. Fertig! ✓

---

## ✦ Environment Variablen

Kopiere `.env.example` als `.env` und fülle alle Werte aus:

```bash
cp .env.example .env
```

Alle Variablen sind in der `.env.example` Datei erklärt.

---

## ✦ Projektstruktur

```
.
├── bot/                    # Python Discord Bot + FastAPI
│   ├── university_bot.py   # Einstiegspunkt
│   ├── core/               # Bot-Kern
│   ├── cogs/               # 100+ Feature-Module
│   ├── api/                # Dashboard REST API + Proxy
│   ├── games/              # Spiel-Module
│   └── utils/              # Hilfsfunktionen
│
├── dashboard/              # Next.js 14 Dashboard
│   ├── app/                # Seiten & API-Routes
│   └── components/         # UI-Komponenten
│
├── Dockerfile              # Railway Deployment
├── start.sh                # Start-Script (Bot + Dashboard)
├── .env.example            # Konfiguration
└── railway.toml            # Railway Config
```

---

## ✦ Local Development

```bash
# Bot
cd bot && pip install -r requirements.txt
python university_bot.py

# Dashboard (anderes Terminal)
cd dashboard && npm install && npm run dev
```

---

## ✦ Lizenz

**Alle Rechte vorbehalten.** Der Quellcode ist nicht öffentlich und
steht unter keiner freien Lizenz — siehe [LICENSE](LICENSE).

Dieses Repository ist privat. Zugriff darauf ist keine Erlaubnis, den
Code zu verwenden, zu kopieren oder weiterzugeben.

> Hier stand vorher „MIT License". Das war falsch: MIT hätte jedem
> erlaubt, den Code zu kopieren und weiterzuverbreiten. Dieselbe
> Falschangabe stand im Impressum der Website und ist dort ebenfalls
> korrigiert.

## ✦ Sicherheit

Eine Lücke gefunden? Bitte **nicht** als öffentliches Issue melden —
siehe [.github/SECURITY.md](.github/SECURITY.md).

## ✦ Mitarbeit

Dies ist kein offenes Projekt; Pull Requests von außen werden nicht
angenommen. Fehlerberichte und Vorschläge sind trotzdem willkommen, am
besten im [Support-Server](https://discord.gg/F3TedBAVZT).
