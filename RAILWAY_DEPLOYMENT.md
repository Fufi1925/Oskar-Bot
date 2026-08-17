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

### Was besonders schmerzt, wenn das Volume fehlt

Bei den meisten Datenbanken heißt „weg“ nur: neu einstellen. Bei diesen
dreien heißt es mehr:

| Datei | Ohne Volume passiert |
|---|---|
| `db/premium_trial.db` | Jeder kann sich nach jedem Deploy erneut 7 Tage Premium holen — die Regel „eine Probewoche pro Konto“ ist wirkungslos. |
| `db/cookie_consent.db` | Der Nachweis nach Art. 7 Abs. 1 DSGVO ist weg. Die Besucher sehen den Hinweis trotzdem nicht wieder (ihr Cookie liegt in ihrem Browser) — es lässt sich dann nur nicht mehr belegen, dass sie ihn gesehen haben. |
| `db/guild_history.db` | Der Verlauf beginnt bei null; die Diagramme sind nach jedem Deploy leer. |
| `db/trusted_bots.db` | Die im Dashboard eingetragenen vertrauten Bots sind weg — der Anti-Nuke bannt sie beim nächsten Mal wieder. Die drei eingebauten und alles aus `TRUSTED_BOTS` bleiben. |

### Ein Volume ist kein Backup

Es überlebt Deploys, aber nicht ein gelöschtes Volume und keinen
Bedienfehler. Unter **Admin → Backups** kannst du jederzeit eine
Sicherung herunterladen. Ein automatischer Zeitplan dafür ist noch nicht
gebaut.

### Kostet das was?

Nein. Railway gibt 1 GB Volume im kostenlosen Tarif. Aktueller
Verbrauch: unter 1 MB.

### Warum steht kein `VOLUME` im Dockerfile?

Weil Railway den Build dann komplett ablehnt:

```
dockerfile invalid: docker VOLUME at Line 76 is not supported,
use Railway Volumes
```

Railway verwaltet Volumes ausschließlich über sein eigenes Dashboard.
Im Dockerfile steht deshalb nur `ENV DATA_DIR=/data` — das Anhängen
machst du mit den fünf Klicks oben.

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
| `TRUSTED_BOTS` | Discord-IDs bekannter Bots, die der Anti-Nuke nie angreift — komma-getrennt | Optional |

### `TRUSTED_BOTS` — Bots, die der Anti-Nuke in Ruhe lässt

Bekannte Bots wie MEE6 oder Dyno legen Kanäle an, vergeben Rollen und
löschen Nachrichten — also genau das, was der Anti-Nuke als Angriff
liest. Ohne Eintrag bannt er sie beim ersten Mal.

```
TRUSTED_BOTS="159985870458322944,155149108183695360"
```

Komma-getrennt, Leerzeichen sind egal. Was keine Zahl ist, wird
übersprungen — ein Tippfehler legt den Anti-Nuke nicht lahm.

**Die Liste gilt global.** Sie lässt sich an zwei Stellen pflegen:
hier in Railway (dann gilt sie ab dem nächsten Deploy) und im
Admin-Dashboard unter **Vertraute Bots** (dann sofort). Was hier
steht, lässt sich im Dashboard nicht löschen — dafür ist es die
Variable.

Nicht im Server-Dashboard: wer die Liste pro Server pflegen dürfte,
könnte seinen eigenen Zweitbot eintragen und damit den Schutz
aushebeln. Server-Inhaber **sehen** die Liste in ihrem
Anti-Nuke-Reiter, ändern können sie sie nicht.

Hauptbot, Vorlagen-Bot und Statusbot stehen fest in der Liste und
lassen sich nirgends entfernen.

Für einzelne *Menschen* gibt es stattdessen die Whitelist im
Dashboard-Reiter „Anti-Nuke“ — dort pro Aktion einstellbar.

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
