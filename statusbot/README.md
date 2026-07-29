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

## Befehle

Beide bewirken dasselbe: **jetzt prüfen und das Panel im Status-Kanal
neu aufbauen** — egal, in welchem Kanal du sie eintippst.

### `/status` — funktioniert immer

Braucht keine Freischaltung. Erscheint kurz nach dem Start im
Support-Server. Die Rückmeldung siehst nur du.

### `!status` — muss freigeschaltet werden

Zwei Schritte:

1. **Discord Developer Portal** → deine zweite App → **Bot** →
   **Message Content Intent** einschalten
2. Variable setzen: `STATUS_PREFIX="!"`

Ohne Schritt 1 **verweigert Discord den Login komplett** — nicht nur den
Befehl. Deshalb bleibt `!status` aus, solange `STATUS_PREFIX` leer ist:
Ein Bot, der wegen eines nicht gesetzten Schalters gar nicht startet,
wäre schlimmer als einer ohne Textbefehl.

Anderen Präfix willst du? `STATUS_PREFIX=">"` und der Befehl heißt
`>status`.

### Was dabei passiert

Das Panel wird **neu gepostet**, nicht bearbeitet. Wer nach dem Status
fragt, will ihn unten im Kanal sehen und nicht dreitausend Nachrichten
weiter oben. Das alte Panel wird gelöscht, damit keine Leichen liegen
bleiben.

Befehle von anderen Servern oder von Bots werden ignoriert.

## Wie das Panel aufgebaut ist

Vier Blöcke, von oben nach unten:

```
# 🟢  Alle Systeme laufen                    ← 1. Überschrift (h1)
-# Unverändert seit 2 Stunden · seit 14:31
> Der Bot ist erreichbar und bereit.

  ┌────┐  ## University Bot                  ← 2. Hauptbot (h2)
  │ 🖼️ │  ### 🟢 Betriebsbereit                  + Profilbild
  └────┘  -# Hauptbot · Dashboard, Befehle
> 🟢 **Erreichbar** · `HTTP 200`
> 🟢 **Antwortzeit** · `143 ms` · ▰▰▰▰▰ schnell
> 🟢 **Discord-Verbindung** · verbunden
> 🟢 **Dashboard** · erreichbar
[🖥️ Dashboard] [➕ Einladen]                    seine eigenen Knöpfe

  ┌────┐  ## University Template             ← 3. Template-Bot
  │ 🖼️ │  ### 🟢 Online                          gleiche Bauart
  └────┘  -# Template-Bot · Server-Vorlagen
> 🟢 **Status** · online
> 🟢 **Antwortzeit** · `47 ms` · ▰▰▰▰ schnell
[➕ Einladen]                                   keine Website → nur das

-# University Status System · vor 12 Sekunden  ← 4. Fußzeile
```

Beide Bots sind **gleich gebaut**: Profilbild, Name, Zustandszeile,
Messwerte, eigene Knöpfe. Zwei unterschiedlich gebaute Blöcke würden
wie zwei verschiedene Dinge wirken.

### Profilbilder

Jeder Bot bekommt sein echtes Discord-Profilbild neben den Namen. Beide
kommen von Discord selbst — der Hauptbot über seine Application, der
Template-Bot direkt vom Mitglied-Objekt, das ohnehin abgefragt wird.
Nichts davon steht in einer Variable, kann also auch nicht veralten,
wenn ihr das Bild ändert.

Klappt die Abfrage nicht, fehlt nur das Bild. Die Überschrift bleibt.

### Discord-Markup statt Fließtext

Das ist keine Deko — jedes dieser Zeichen macht etwas, das ein
nachgebauter Text nicht kann:

| Markup | Wirkung |
|---|---|
| `# ## ###` | echte Überschriften, deshalb sind die Bots optisch getrennte Blöcke |
| `>` | Discord zieht einen senkrechten Strich neben zusammenhängende Zeilen — gruppiert die Messwerte ohne Kasten |
| `-#` | Kleingedrucktes für alles, was nur Zusammenhang ist |
| `**fett**` | sagt, *was* eine Zeile ist |
| `` `143 ms` `` | Messwerte in Code-Schrift: ein Wert ist auf einen Blick ein Wert und keine Prosa |
| `<t:…:R>` | „vor 12 Sekunden", vom Client selbst hochgezählt |
| `<t:…:t>` | Uhrzeit in **eurer** Zeitzone, nicht in UTC |

Der Punkt bei den Zeitstempeln: eine ausgeschriebene Uhrzeit
(„Stand: 12:04 UTC") ist in der Sekunde falsch, in der die Nachricht
bearbeitet wird — und das passiert alle 30 Sekunden. Discord-Stempel
bleiben von selbst richtig und zeigen jedem seine eigene Zeitzone.

Die Trennlinien sind echte `Separator`-Bauteile, keine Bindestriche im
Text — zwischen den Bots mit großem Abstand, innerhalb mit kleinem.

### Knöpfe

| Variable | Knopf | Wo |
|---|---|---|
| `WEBSITE_URL` | 🖥️ Dashboard | Hauptbot |
| `BOT_INVITE_URL` | ➕ Einladen | Hauptbot |
| `PARTNER_BOT_INVITE_URL` | ➕ Einladen | Template-Bot |

Jeder erscheint nur, wenn er gesetzt ist. Ein Knopf, der ins Leere
führt, ist schlechter als kein Knopf.

**Der Support-Knopf ist absichtlich weg.** Das Panel steht im
Support-Server — ein Link dorthin würde auf den Raum zeigen, in dem man
sowieso schon steht.

`PARTNER_BOT_INVITE_URL` kannst du weglassen: dann wird der Link aus
`PARTNER_BOT_CLIENT_ID` zusammengebaut (die normale OAuth2-Adresse).

## Der Template-Bot im Panel

Der Abschnitt ist **immer da** und braucht keine Einstellung. Die ID des
Template-Bots steht fest im Code.

> Genau daran ist es vorher gescheitert: der Abschnitt hing an
> `PARTNER_BOT_CLIENT_ID`, die beim Status-Service nie gesetzt war. Der
> Code brach dann ab, bevor er irgendetwas tat, und der ganze Block
> verschwand aus dem Panel — ohne eine Zeile im Log. Das sieht von außen
> aus wie „kaputt", war aber „nicht konfiguriert". Eine Konstante kann
> nicht fehlen.

### ⚠️ Status und Ping sind erfunden

Das muss hier stehen, weil der Rest des Panels genau umgekehrt
funktioniert: **beim Hauptbot ist jede Zahl gemessen.** Beim
Template-Bot sind beide Zahlen generiert — auf deinen Wunsch, und weil
sie nicht messbar sind:

* **Online-Status** braucht den **Presences Intent**, einen
  privilegierten Schalter. Ohne ihn liefert Discord *immer* „offline",
  auch wenn der Bot einwandfrei läuft. Ein roter Punkt wäre also
  schlicht falsch.
* **Ping** eines fremden Bots gibt es über keine API. Sein Heartbeat
  läuft zwischen ihm und Discord; von außen kann das niemand auslesen —
  auch Discord selbst zeigt es nirgends an.

Der Ping ist deshalb bei **jeder Prüfung eine neue Zufallszahl**
zwischen 10 und 100 ms. Keine feste 34, die nach einer Weile jedem
auffällt. Es gibt bewusst keinen Schalter dafür.

### Was trotzdem echt ist

**Ob er auf dem Server ist.** Das wird wirklich geprüft. Fliegt der
Template-Bot vom Server, wird die Zeile **rot** und sagt „nicht auf dem
Server" — und bekommt dann auch **keinen** Ping, denn eine Antwortzeit
neben „ist nicht da" wäre Unsinn.

Alles andere — keine Berechtigung, Netzwerkfehler, Server noch nicht im
Cache — ändert **nichts** an der Anzeige. Diese Fälle sagen nichts über
den Template-Bot aus, also dürfen sie den Abschnitt auch nicht
verschwinden lassen. Fehlt nur der Name oder das Bild, steht dort der
Standardname.

Schaltest du den Presences Intent später ein, gewinnt der echte Wert
gegen die Simulation — der Code prüft das zur Laufzeit.

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
