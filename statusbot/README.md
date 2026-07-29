# University Status

Ein zweiter, sehr kleiner Bot. Er überwacht den Hauptbot und postet
Changelogs — auch dann, wenn der Hauptbot nicht mehr läuft.

## Warum ein eigener Railway-Service

Das ist der Kern und kein Detail: **Ein Wächter im selben Container
kann nicht melden, dass der Container tot ist.**

Wenn Railway den Container neu startet, ein Deploy scheitert oder
`restartPolicyMaxRetries = 5` aufgebraucht ist, sterben *alle* Prozesse
darin — auch der Wächter, genau in dem Moment, in dem er melden soll.
Zwei Container sterben getrennt. Nur deshalb ist das ein eigener
Service und kein Cog im Hauptbot.

Gleiches Repo, gleiches Railway-Projekt, eigener Container.

## Einrichten

### 1. Service in Railway anlegen

1. Im Projekt → **New** → **GitHub Repo** → dasselbe Repo wählen
2. Beim neuen Service: **Settings** → **Build**
3. **Dockerfile Path** auf `statusbot/Dockerfile` setzen
4. Speichern

### 2. Variablen setzen

Beim **Status-Service** (nicht beim Hauptbot):

| Variable | Wert | Pflicht |
|---|---|---|
| `STATUS_BOT_TOKEN` | Token der zweiten Discord-Application | ja |
| `MAIN_BOT_URL` | Öffentliche URL des **Hauptbots**, z.B. `https://xyz.up.railway.app` | ja |
| `STATUS_CHANNEL_ID` | Kanal für die Live-Statusnachricht | ja |
| `HOME_GUILD_ID` | `1530378233579704370` (Standard) | nein |
| `DASHBOARD_API_KEY` | **derselbe** wie beim Hauptbot | nur fürs Senden |
| `STATUS_POLL_SECONDS` | Standard `30` | nein |
| `STATUS_FAILURES_BEFORE_DOWN` | Standard `3` | nein |

> `MAIN_BOT_URL` muss die URL des **anderen** Service sein. Zeigt sie auf
> den Status-Bot selbst, prüft er sich selbst — und meldet nie eine
> Störung.

### 3. Bot einladen

Die zweite Application braucht auf dem Support-Server nur:
**Nachrichten senden**, **Links einbetten**, **Nachrichtenverlauf lesen**.

Mehr nicht — er liest nichts und verwaltet nichts.

## Was er tut

**Live-Statusnachricht.** Eine Components-V2-Nachricht im Status-Kanal,
die sich selbst aktualisiert. Sie wird *bearbeitet*, nicht neu gepostet,
damit der Kanal nicht zuläuft. Nach einem Neustart sucht er die alte
Nachricht und übernimmt sie.

**Drei Zustände:**

- 🟢 **Alle Systeme laufen** — erreichbar, mit Discord verbunden, Dashboard oben
- 🟡 **Startet gerade** — antwortet mit 503, wie während eines Updates
- 🔴 **Störung** — nach 3 Fehlversuchen in Folge (also ca. 1,5 Minuten)

Ein einzelner Fehlversuch ist keine Störung. Sonst gäbe es bei jedem
Update des Hauptbots einen Fehlalarm.

**Changelogs senden.** Über den Endpunkt `POST /send`, mit demselben
`DASHBOARD_API_KEY`. Nur in den Support-Server — der Endpunkt hat keine
Rechteprüfung pro Server hinter sich und darf deshalb nicht zum
Universalwerkzeug werden.

## Was er bewusst nicht tut

**Keine Datenbank, kein Volume, keine Befehle.** Je weniger drin ist,
desto weniger kann kaputtgehen an dem Ding, dessen einzige Aufgabe es
ist, noch zu laufen.

**Er behauptet nicht, der Bot sei offline.** Er sagt „nicht erreichbar".
Das ist ein Unterschied: Vielleicht ist das Problem die Leitung, oder
Discord — und wenn der Prüfer selbst das Problem sein könnte, ist die
zweite Formulierung die ehrliche.

## Wenn nichts passiert

- **Kein Token** → Der Service beendet sich ruhig statt in einer
  Neustart-Schleife zu landen. Steht so im Log.
- **`MAIN_BOT_URL` fehlt** → steht im Log, die Statusnachricht bleibt
  auf „Wird geprüft".
- **Kanal nicht sichtbar** → steht im Log. Meist ist der Bot nicht auf
  dem Server oder darf den Kanal nicht sehen.
