# Eigener Lavalink-Server

Musik läuft über einen Lavalink-Server. Der Bot bringt keinen mit — er
verbindet sich zu einem.

Die öffentlichen Server, die als Rückfall eingetragen sind, sind
kostenlos und werden von vielen Bots geteilt. Gemessen: **etwa vier
Suchen, dann kommt eine Weile lang nichts mehr** (HTTP 429). Für einen
Bot auf 23 Servern reicht das nicht.

Diese Anleitung richtet einen eigenen ein. Danach gibt es keine
Ratenbegrenzung außer der eigenen.

---

## Weg 1 — Railway (empfohlen)

Der Bot läuft bereits auf Railway. Ein zweiter Dienst im selben Projekt
redet über das interne Netz mit ihm — kein öffentlicher Zugang nötig,
und der Datenverkehr zählt nicht als ausgehend.

### 1. Dienst anlegen

Im **selben Railway-Projekt** wie der Bot:

**New** → **GitHub Repo** → dasselbe Repo auswählen.

### 2. Auf diesen Ordner zeigen

**Settings** → **Build**:

| Feld | Wert |
|---|---|
| Dockerfile Path | `lavalink/Dockerfile` |

> Wichtig: ohne diesen Eintrag baut Railway das Haupt-Dockerfile und
> startet aus Versehen einen zweiten Bot. `railway.toml` gilt für alle
> Dienste im Repo, deshalb steht der Pfad dort bewusst nicht drin.

### 2b. Neustart-Regel prüfen

`railway.toml` liegt im Repo-Stammverzeichnis und gilt für **jeden**
Dienst daraus — also auch für diesen. Dort steht:

```toml
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 5
```

Heißt: Startet Lavalink fünfmal hintereinander nicht (etwa weil das
Passwort noch fehlt), gibt Railway auf und der Dienst bleibt **dauerhaft
aus** — auch nachdem du die Variable nachgetragen hast. Dann einmal von
Hand **Redeploy** drücken.

### 3. Variablen setzen

**Variables** beim **Lavalink-Dienst**:

```
LAVALINK_SERVER_PASSWORD = <ein langes zufälliges Passwort>
```

Ein Passwort erzeugen:

```bash
openssl rand -base64 32
```

### 4. Internen Namen merken

**Settings** → **Networking** → **Private Networking**. Dort steht ein
Name wie `lavalink.railway.internal`.

### 5. Den Bot darauf zeigen

**Variables** beim **Bot-Dienst** (nicht beim Lavalink-Dienst):

```
LAVALINK_HOST     = lavalink.railway.internal
LAVALINK_PORT     = 2333
LAVALINK_SECURE   = false
LAVALINK_PASSWORD = <dasselbe Passwort wie oben>
```

`LAVALINK_SECURE = false` ist richtig: das interne Netz ist nicht
öffentlich, deshalb gibt es dort kein HTTPS. Das Passwort muss auf
beiden Seiten **identisch** sein.

### 6. Neu starten und im Log nachsehen

Nach dem Neustart des Bots steht dort:

```
[music] Lavalink node connected: http://lavalink.railway.internal:2333
```

Steht dort stattdessen `did not answer in time`, siehe unten.

---

## Weg 2 — Kostenloser öffentlicher Server

Wenn Railway (noch) nicht sein soll: Es sind bereits zwei öffentliche
Server als Rückfall eingetragen. **Du musst nichts tun** — sie werden
automatisch benutzt, wenn `LAVALINK_HOST` leer ist.

Nachteil ist die Ratenbegrenzung. Für Ausprobieren reicht es, für den
Dauerbetrieb nicht.

Andere öffentliche Server findest du in der
[Lavalink-Serverliste](https://lavalink.darrennathanael.com/).
Prüfe vor dem Eintragen, ob er wirklich läuft:

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "https://DEIN-SERVER/v4/info" \
  -H "Authorization: DAS-PASSWORT"
```

`200` heißt gut. `403` heißt falsches Passwort. `404` oder `500` heißt:
Finger weg, der ist kaputt — genau daran hing der Ausfall vorher.

---

## Weg 3 — Auf einem eigenen Server

Nur wenn du schon einen Server (VPS, Root-Server) hast.

Benötigt **Java 17 oder neuer**:

```bash
java -version
```

Dann:

```bash
mkdir -p ~/lavalink && cd ~/lavalink
curl -LO https://github.com/lavalink-devs/Lavalink/releases/download/4.2.2/Lavalink.jar
# Diese application.yml aus dem Repo daneben legen
export LAVALINK_SERVER_PASSWORD="<dein Passwort>"
java -jar Lavalink.jar
```

Damit es einen Neustart überlebt, gehört das in einen systemd-Dienst.

Im Bot dann:

```
LAVALINK_HOST     = deine-server-ip-oder-domain
LAVALINK_PORT     = 2333
LAVALINK_SECURE   = false
LAVALINK_PASSWORD = <dein Passwort>
```

Bei einer Domain mit HTTPS davor: `LAVALINK_SECURE = true` und
`LAVALINK_PORT` weglassen.

---

## Spotify-Links (optional)

Ohne das hier funktionieren Spotify-Links **nicht**. YouTube und
SoundCloud gehen auch ohne.

1. Auf [developer.spotify.com](https://developer.spotify.com/dashboard)
   anmelden → **Create app**. Name und Beschreibung sind egal,
   Redirect-URI `http://localhost` reicht.
2. Client ID und Client Secret kopieren.
3. Beim **Lavalink-Dienst** setzen:
   ```
   SPOTIFY_CLIENT_ID     = ...
   SPOTIFY_CLIENT_SECRET = ...
   ```
4. In `application.yml` unter `lavasrc.sources` `spotify: false` auf
   `true` ändern und neu bereitstellen.

Spotify streamt nicht selbst. Der Titel wird erkannt und dann von
YouTube abgespielt — deshalb muss YouTube vorher funktionieren.

---

## Wenn etwas nicht geht

**`did not answer in time` im Bot-Log**

Der Bot erreicht den Server nicht. Prüfen:
- Läuft der Lavalink-Dienst? (Railway → Deployments → grün?)
- Stimmt `LAVALINK_HOST` genau mit dem internen Namen überein?
- Steht `LAVALINK_SECURE` bei internem Netz auf `false`?

**`Unauthorized` oder `403` im Lavalink-Log**

Die Passwörter stimmen nicht überein. `LAVALINK_PASSWORD` beim Bot muss
Zeichen für Zeichen gleich `LAVALINK_SERVER_PASSWORD` beim Lavalink sein
— auch keine Leerzeichen am Ende.

**Der Server läuft, aber YouTube spielt nicht**

Das youtube-source-Plugin konnte nicht laden. Im Lavalink-Log steht
dann etwas zu `youtube-plugin`. Meist ist die Version veraltet:
[aktuelle Version nachsehen](https://github.com/lavalink-devs/youtube-source/releases)
und in `application.yml` eintragen.

**„The music server is busy right now"**

Das ist die Ratenbegrenzung der öffentlichen Server — Weg 1 löst es.

---

## Was hier ungetestet ist

Ehrlich gesagt: Diese Dateien wurden **nicht laufend getestet**. In der
Umgebung, in der sie entstanden sind, gibt es weder Docker noch Java 17,
also ließ sich Lavalink nicht wirklich starten.

Was geprüft wurde:

- Das Docker-Image `ghcr.io/lavalink-devs/lavalink:4` existiert, und
  sein Arbeitsverzeichnis ist tatsächlich `/opt/Lavalink` (aus der
  Image-Konfiguration ausgelesen, nicht angenommen).
- Beide Plugin-Dateien sind unter den angegebenen Versionen wirklich
  abrufbar (HTTP 200 von `maven.lavalink.dev`).
- Die `application.yml` ist gültiges YAML.
- Lavalink 4.2.2 ist die aktuelle Fassung.

Was das nicht abdeckt: ob Lavalink mit genau dieser Konfiguration
hochkommt. Wenn beim ersten Start etwas klemmt, schick mir das Log.
