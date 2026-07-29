# 🎓 University Bot — Railway Deployment Guide

## So deployst du Bot + Dashboard als EIN Projekt auf Railway

---

## ⚠️ ZUERST: Volume anlegen (sonst gehen alle Daten verloren)

Railway baut den Container bei **jedem Deploy neu**. Ohne Volume sind
danach alle 61 Datenbanken weg — jeder Server verliert jede Einstellung,
jedes Mal.

**Das musst du einmal im Railway-Dashboard klicken:**

1. Dein Projekt öffnen → auf den Service klicken
2. Reiter **Variables** → prüfen, dass `DATA_DIR` auf `/data` steht
   (steht schon im Dockerfile, also normalerweise nichts zu tun)
3. Rechtsklick auf den Service → **Add Volume**
   *(oder: Service → Settings → Volumes → New Volume)*
4. Als **Mount Path** eintragen: `/data`
5. Speichern → Railway startet neu

**Fertig.** Beim nächsten Start schiebt der Bot alles Vorhandene ins
Volume und meldet im Log:

```
[storage] db/ -> /data/db
[storage] jsondb/ -> /data/jsondb
[storage] rr.db moved
[storage] j2c_data.db linked
[storage] data lives in /data
```

### Woran du merkst, dass es NICHT geklappt hat

Steht das im Log, fehlt das Volume noch:

```
[storage] WARNING: DATA_DIR is set but nothing is mounted there.
```

Im Dashboard steht es auch: **Admin → Health → storage**. Dort heißt es
entweder „Alles in Ordnung — die Daten liegen auf einem Volume" oder es
sagt dir genau, was fehlt.

### Warum nicht einfach ein Volume auf `bot/db`?

Weil drei Dinge außerhalb liegen: `rr.db` (Reaktions-Rollen),
`j2c_data.db` (Join to Create) und der Ordner `jsondb/`. Ein Volume nur
auf `bot/db` hätte die stillschweigend liegen lassen — der Bot wäre
sauber gestartet und die Reaktions-Rollen wären trotzdem weg gewesen.
Deshalb liegt alles unter `/data`.

### Ein Volume ist kein Backup

Es überlebt Deploys, aber nicht ein gelöschtes Volume und keinen
Bedienfehler. Unter **Admin → Backups** kannst du jederzeit eine
Sicherung herunterladen. Ein automatischer Zeitplan dafür ist noch nicht
gebaut.

### Kostet das was?

Nein. Railway gibt 1 GB Volume im kostenlosen Tarif. Aktueller
Verbrauch: unter 1 MB.

---

### Architektur

```
┌─────────────────────────────────────────────────┐
│           Railway (1 Service, 1 Container)      │
│                                                  │
│  ┌──────────────┐     ┌──────────────────────┐  │
│  │  Discord Bot  │     │  FastAPI + Dashboard │  │
│  │  (discord.py) │     │  (Port 8000)         │  │
│  │               │◄───►│                      │  │
│  └──────────────┘     │  /api/v1/* → API     │  │
│                        │  /health   → Check   │  │
│  ┌──────────────┐     │  /*        → Dashboard│  │
│  │  Next.js SSR  │◄───│                      │  │
│  │  (Port 3000)  │     └──────────┬───────────┘  │
│  └──────────────┘                │               │
│                                  ▼               │
│                        Railway Public URL :80    │
└─────────────────────────────────────────────────┘
```

Alles läuft in **einem Container** auf **einem Port**:
- `/api/v1/*` → Bot REST API (mit API-Key-Auth)
- `/health` → Health Check
- `/*` → Dashboard (Next.js mit SSR für OAuth2)

---

### Schritt-für-Schritt Anleitung

#### 1️⃣ GitHub Repository pushen

```bash
git push origin main
```

#### 2️⃣ Railway Projekt erstellen

1. Gehe zu [railway.app](https://railway.app) → **New Project**
2. **Deploy from GitHub repo** → Wähle dein Repository
3. Railway erkennt automatisch das Dockerfile

#### 3️⃣ Environment Variables setzen

Gehe zu deinem Service → **Variables** und füge ALLE Variablen aus `.env.example` hinzu:

| Variable | Wert | Pflicht |
|----------|------|---------|
| `TOKEN` | Discord Bot Token | ✅ |
| `OWNER_IDS` | Deine Discord User ID | ✅ |
| `DASHBOARD_API_KEY` | Starkes Secret (z.B. `mein_geheimer_key_123`) | ✅ |
| `DISCORD_CLIENT_ID` | Discord OAuth2 Client ID | ✅ |
| `DISCORD_CLIENT_SECRET` | Discord OAuth2 Client Secret | ✅ |
| `NEXTAUTH_SECRET` | Langer Random String ([Generator](https://generate-secret.vercel.app/32)) | ✅ |
| `NEXTAUTH_URL` | Wird automatisch gesetzt (Railway URL) | ⚡ Auto |
| `ADMIN_IDS` | Discord IDs mit Admin-Zugang (serverseitige Prüfung) | ✅ |
| `NEXT_PUBLIC_ADMIN_IDS` | Gleiche IDs, nur für die Anzeige im UI | ✅ |
| `NEXT_PUBLIC_BRAND_NAME` | `University Bot` | ✅ |
| `NEXT_PUBLIC_BRAND_NAME_WORD` | `UB` | ✅ |
| `LAVALINK_HOST` | `lavalink.jirayu.net` | Optional |
| `LAVALINK_PASSWORD` | `youshallnotpass` | Optional |
| `LAVALINK_SECURE` | `false` | Optional |
| `LAVALINK_PORT` | `13592` | Optional |
| `GIPHY_API_KEY` | Key von developers.giphy.com | Optional |
| `GOOGLE_API_KEY` / `GROQ_API_KEY` | Für die KI-Commands | Optional |
| `API_ENABLED` | `true` | ✅ |
| `brand_name` | `University Bot` | ✅ |

> ⚠️ **Setze niemals `NEXT_PUBLIC_DASHBOARD_API_KEY`.**
> Variablen mit `NEXT_PUBLIC_` werden beim Build in das JavaScript eingebettet,
> das an jeden Browser ausgeliefert wird. Der API-Key wäre damit öffentlich.
> `start.sh` entfernt die Variable inzwischen automatisch, falls sie gesetzt ist.
> Browser-Anfragen laufen über `/api/bot`, wo der Key erst serverseitig
> angehängt wird — nachdem geprüft wurde, ob der eingeloggte Nutzer den
> betroffenen Server überhaupt verwalten darf.

#### 4️⃣ Discord App konfigurieren

1. Gehe zu [discord.com/developers/applications](https://discord.com/developers/applications)
2. Erstelle eine neue Application (oder nutze eine bestehende)
3. **Bot** → Reset Token → Kopiere den Token → Setze als `TOKEN` Variable
4. **OAuth2** → General:
   - Copy **Client ID** → `DISCORD_CLIENT_ID`
   - Copy **Client Secret** → `DISCORD_CLIENT_SECRET`
   - **Add Redirect:** `https://DEINE-RAILWAY-URL.up.railway.app/api/auth/callback/discord`
5. **Bot** → Privileged Gateway Intents:
   - ✅ SERVER MEMBERS INTENT
   - ✅ PRESENCE INTENT
   - ✅ MESSAGE CONTENT INTENT

#### 5️⃣ Domain generieren

1. Gehe zu deinem Railway Service → **Settings** → **Networking**
2. **Generate Domain** → Du bekommst eine URL wie `https://university-bot-xxx.up.railway.app`
3. Diese URL ist dein `NEXTAUTH_URL` (wird meist automatisch gesetzt)

#### 6️⃣ Fertig! 🎉

Öffne deine Railway URL im Browser → Das Dashboard lädt dich zum Discord-Login ein.

---

### Lokales Development

```bash
# 1. .env Datei erstellen
cp .env.example .env
# .env mit deinen Werten füllen

# 2. Bot starten (Terminal 1)
cd bot
pip install -r requirements.txt
python university_bot.py

# 3. Dashboard starten (Terminal 2)
cd dashboard
npm install
npm run build
npm run start

# 4. Öffne http://localhost:8000
```

---

### Troubleshooting

| Problem | Lösung |
|---------|--------|
| Dashboard zeigt "starting up" | Näch.js Server braucht ~30s zum Starten, neu laden |
| OAuth2 Login fehlerhaft | Redirect URL in Discord Developer Portal prüfen |
| Bot geht offline | Token und Intents prüfen |
| Musik funktioniert nicht | Lavalink Credentials prüfen |
| 502 Bad Gateway | Dashboard-Server abgestürzt → Railway Logs checken |
| CORS Fehler | `CORS_ORIGINS` Variable mit deiner URL setzen |
