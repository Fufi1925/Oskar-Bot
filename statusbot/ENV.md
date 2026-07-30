# Variablen für den Status-Service

Der Status-Bot ist ein **eigener Railway-Service** und hat deshalb seine
eigenen Variablen. Er erbt nichts vom Hauptbot — Railway trennt das pro
Service.

## Die Liste zum Kopieren

Beim **Status-Service** eintragen (Variables → Raw Editor):

```
STATUS_BOT_TOKEN="<Token der ZWEITEN Discord-Application>"
MAIN_BOT_URL="https://universtiy-bot.up.railway.app"
STATUS_CHANNEL_ID="<ID des Status-Kanals>"
HOME_GUILD_ID="1530378233579704370"
DASHBOARD_API_KEY="<derselbe wie beim Hauptbot>"
NEXT_PUBLIC_BRAND_NAME="University Bot"

# Knöpfe unter dem Panel. Jeder erscheint nur, wenn gesetzt.
# Kein Support-Link: das Panel steht bereits im Support-Server.
WEBSITE_URL="https://universtiy-bot.up.railway.app"
BOT_INVITE_URL="<Einladungslink des Hauptbots>"

# Für das Profilbild des Hauptbots im Panel. Meist schon gesetzt.
MAIN_BOT_CLIENT_ID="1530349205372145715"

# Der Template-Bot braucht KEINE Variable mehr - seine ID steht fest
# im Code. Genau daran ist der Abschnitt vorher gescheitert: die
# Variable war hier nie gesetzt, und der Block verschwand kommentarlos.
# Nur falls sein Einladungslink abweicht:
# PARTNER_BOT_INVITE_URL="<Einladungslink des Template-Bots>"
STATUS_POLL_SECONDS="30"
STATUS_FAILURES_BEFORE_DOWN="3"

# Nur wenn du !status willst — vorher im Developer Portal den
# "Message Content Intent" einschalten, sonst startet der Bot nicht.
# STATUS_PREFIX="!"
PORT="8080"
```

### Was jede Variable macht

| Variable | Pflicht | Erklärung |
|---|---|---|
| `STATUS_BOT_TOKEN` | **ja** | Token der zweiten Application. **Nicht** der des Hauptbots — sonst loggen sich zwei Prozesse mit demselben Token ein und werfen sich gegenseitig raus. |
| `MAIN_BOT_URL` | **ja** | Öffentliche URL des **Hauptbots**. Zeigt sie auf den Status-Service selbst, prüft er sich selbst und meldet nie eine Störung. |
| `STATUS_CHANNEL_ID` | **ja** | Kanal für die Live-Statusnachricht. Rechtsklick auf den Kanal → ID kopieren (Entwicklermodus muss an sein). |
| `HOME_GUILD_ID` | nein | Support-Server. Standard ist bereits `1530378233579704370`. |
| `DASHBOARD_API_KEY` | nur fürs Senden | Muss **derselbe** sein wie beim Hauptbot, sonst weist der Sende-Endpunkt das Dashboard ab. |
| `NEXT_PUBLIC_BRAND_NAME` | nein | Name in der Statusnachricht. Standard: `University Bot`. |
| `STATUS_POLL_SECONDS` | nein | Prüfabstand, Standard `30`. |
| `STATUS_FAILURES_BEFORE_DOWN` | nein | Fehlversuche bis „Störung", Standard `3`. Mit 30 Sekunden Abstand also nach ca. 1,5 Minuten. |
| `MAIN_BOT_CLIENT_ID` | nein | Nur fürs Profilbild des Hauptbots im Panel. Ersatzweise wird `DISCORD_CLIENT_ID` genommen. |
| `BOT_INVITE_URL` | nein | Knopf „Einladen" beim Hauptbot. |
| `WEBSITE_URL` | nein | Knopf „Dashboard" beim Hauptbot. |
| `PARTNER_BOT_INVITE_URL` | nein | Einladungslink des Template-Bots. Ohne die Variable wird er aus seiner ID gebaut. |
| `PORT` | nein | Railway setzt das meist selbst. |

### Was der Status-Service **nicht** braucht

Diese bewusst **nicht** eintragen — er benutzt sie nicht:

`TOKEN` · `DISCORD_CLIENT_ID` · `DISCORD_CLIENT_SECRET` ·
`NEXTAUTH_SECRET` · `NEXTAUTH_URL` · `LAVALINK_*` · `DATA_DIR` ·
`OWNER_IDS` · alle `NEXT_PUBLIC_IMPRINT_*` · `SUPPORT_INVITE_URL`
(wird nicht mehr gelesen — der Support-Knopf ist entfallen)

Er hat keine Datenbank, kein Dashboard und keine Musik. Je weniger
Zugangsdaten in dem Dienst liegen, dessen einzige Aufgabe das
Weiterlaufen ist, desto besser.

---

## Beim Hauptbot ergänzen

Eine einzige Variable, damit das Dashboard weiß, wohin es zum Senden
greifen soll:

```
STATUS_BOT_URL="https://<url-des-status-service>.up.railway.app"
```

Fehlt sie, funktioniert alles wie bisher — nur die Auswahl „mit welchem
Bot senden" erscheint dann nicht.

---

## ⚠️ Zwei Sachen, die beim Hauptbot nicht stimmen

### `NEXT_PUBLIC_DASHBOARD_API_KEY` löschen

Alles mit `NEXT_PUBLIC_` wird von Next.js **in die Webseite eingebacken**
und ist für jeden Besucher im Quelltext lesbar. Der API-Schlüssel darf
dort nicht stehen.

`start.sh` entfernt die Variable beim Start automatisch (im Deploy-Log
steht dann „🛡️ … has been removed"), aber sie gehört trotzdem gelöscht:
Verlässt man sich auf die Notbremse, reicht ein Umbau am Startskript und
der Schlüssel steht plötzlich öffentlich.

Richtig ist nur `DASHBOARD_API_KEY` (ohne Präfix). Browser-Anfragen
laufen über den Proxy unter `/api/bot`, der den Schlüssel serverseitig
anhängt.

### Impressum

`NEXT_PUBLIC_IMPRINT_ADDRESS="."` — ein Impressum mit einem Punkt als
Adresse erfüllt die Anforderungen in Deutschland nicht. Bei einer
öffentlich erreichbaren Seite ist das ein echtes Risiko, kein
Schönheitsfehler.

---

## Impressum, Datenschutz, Nutzungsbedingungen

Diese Angaben liest die Website **beim Aufruf**, nicht beim Bauen.
Deshalb **ohne** `NEXT_PUBLIC_`-Präfix eintragen — beim **Hauptbot**:

```
IMPRINT_NAME="<Vor- und Nachname oder Firma>"
IMPRINT_ADDRESS="<Straße Nr.
PLZ Ort>"
IMPRINT_EMAIL="<E-Mail, die auch gelesen wird>"

# Optional:
# PRIVACY_EMAIL="<eigene Adresse für Datenschutz-Anfragen>"
# IMPRINT_VAT_ID="<USt-IdNr., nur falls vorhanden>"
```

**Warum ohne Präfix:** Alles mit `NEXT_PUBLIC_` wird von Next.js beim
**Bauen** des Images fest eingebacken. Das Dockerfile übergibt aber nur
drei solche Variablen — die Impressum-Angaben waren nie dabei. In
Railway gesetzt hatten sie deshalb **keine Wirkung**, und das Impressum
blieb leer, egal was eingetragen war.

Die alte Schreibweise mit `NEXT_PUBLIC_` funktioniert weiterhin, falls
sie schon gesetzt ist — die ohne Präfix hat Vorrang.

⚠️ **`IMPRINT_ADDRESS="."` zählt als nicht gesetzt.** Ein Punkt ist
keine ladungsfähige Anschrift. Die Seite zeigt dann oben eine Warnung.


---

## Dashboard-Knöpfe im Bot

Der Bot setzt an drei Stellen einen **Dashboard**-Knopf: in die
Willkommens-DM nach dem Hinzufügen, unter `>help` und in die
Anti-Nuke-Warnung.

**Du musst dafür nichts einstellen.** Die Adresse wird in dieser
Reihenfolge gesucht:

1. `DASHBOARD_URL` — falls du sie ausdrücklich setzen willst
2. `NEXTAUTH_URL` — **hast du bereits gesetzt**, wird genommen
3. `WEBSITE_URL`
4. `CORS_ORIGINS` (erster Eintrag)

Findet er keine gültige Adresse, erscheint **kein** Knopf — statt eines
Links, der ins Leere führt.

> Vorher hing der Anti-Nuke-Knopf allein an `DASHBOARD_URL`. Die ist bei
> dir nicht gesetzt, also ist dieser Knopf **nie** erschienen — ohne
> jede Meldung. Und in der Willkommens-DM stand fest
> `https://.vercel.app`, eine Adresse ohne Server-Namen.


---

## Neu: Ausfallmeldung, Verlauf, Wartung, Status-Seite

### Beim **Status-Service** eintragen

```
# Wer bei einer Störung gepingt wird. Rollen-ID, oder "everyone".
# Leer = Meldung ohne Ping.
STATUS_ALERT_ROLE_ID="<Rollen-ID>"

# Wird im Dockerfile schon gesetzt. Nur ändern, wenn dein Volume
# woanders hängt.
STATUS_DATA_DIR="/data"

# Optional:
STATUS_HISTORY_DAYS="7"        # Zeitraum im Panel
STATUS_HISTORY_KEEP_DAYS="90"  # wie lange aufbewahrt wird
```

### ⚠️ Volume nicht vergessen

Der Verlauf braucht ein **Railway-Volume**, gemountet auf `/data`.
Railway löscht das Dateisystem bei jedem Deploy — ohne Volume fängt die
Aufzeichnung jedes Mal von vorn an.

Ohne Volume stürzt nichts ab: das Panel lässt die Uptime-Zeile dann
einfach weg, statt eine Zahl aus zwanzig Minuten Daten zu zeigen.

### Beim **Hauptbot** eintragen

```
STATUS_BOT_URL="https://<url-des-status-service>.up.railway.app"
```

Die brauchst du für die Seite **/status** auf der Website. Fehlt sie,
zeigt die Seite „Status nicht abrufbar" statt zu raten.

### Was jetzt passiert

| | |
|---|---|
| **Ausfall** | Eigene Nachricht im Status-Kanal + Ping. Bei Rückkehr eine Entwarnung mit Ausfalldauer. |
| **Verlauf** | Panel zeigt „99,4 % erreichbar in 7 Tagen · letzte Störung vor 2 Tagen". |
| **Wartung** | `/wartung an grund:Datenbank-Umzug` → Panel meldet Wartung statt Störung, keine Pings. `/wartung an:false` beendet es. |
| **Website** | `/status` zeigt dieselben Daten — auch für Leute ohne Discord-Zugang. |

Gemeldet wird **nur** der Wechsel in eine Störung und die Rückkehr.
Ein normaler Deploy („startet gerade") löst nichts aus — sonst gewöhnt
sich jeder daran, den Kanal zu ignorieren.
