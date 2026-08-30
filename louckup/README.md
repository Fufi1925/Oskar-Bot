# Louckup — abgetrennter Bereich unter `/louckup`

Eigener Login, eigene Discord-Application, eigene Datenbank, eigene
Cookies. **Kein** Import aus `phantom/`, `bot/` oder `dashboard/` — der
Bereich ist nur *gemountet*, nicht eingebunden.

```text
https://<deine-url>/louckup              -> Login
https://<deine-url>/louckup/dashboard    -> nur für Owner
https://<deine-url>/louckup/healthz      -> {"ok": true, ...}
```

## Ablauf

1. `/louckup` zeigt **nur** den Knopf „Mit Discord anmelden" — keine
   Erklärung, kein Footer, nichts sonst.
2. OAuth2 mit `identify`, `email`, `guilds`, `guilds.join`, `gdm.join`.
3. Nach dem Callback wird geprüft: steht die Discord-ID in
   `LOUCKUP_OWNER_IDS`?
   * **ja** → Session-Cookie, weiter auf `/louckup/dashboard`
   * **nein** → **kein** Cookie, sofort weiter auf `LOUCKUP_FALLBACK_URL`
     (standardmäßig `/`, das normale Dashboard)

Die Owner-Prüfung passiert **zweimal**: beim Login und bei jedem Aufruf
eines Reiters. Wird jemand aus der Liste gestrichen, verliert ein noch
gültiges Cookie damit sofort seine Wirkung.

## Reiter

| Reiter | Inhalt |
|---|---|
| Discord IDs | Suche nach einer Discord-ID über alle eingetragenen Bots |
| Roblox User | Platzhalter |
| IP | Adresse eingeben, Karte zeigt Stadt, Land und Netz — dazu Adressen aus dem Verlauf |
| Self | die eigenen Daten, die eigenen Adressen, die eigenen Logins und die Regeln des Bereichs |
| Einstellungen | Bots eintragen, prüfen, entfernen — nur mit Token, Name und Bild kommen von selbst |

**Self** zeigt ausschließlich die Daten des Accounts, der gerade
eingeloggt ist — Discord-ID, Namen, E-Mail, Verifiziert-Status,
Zeitpunkte des ersten und letzten Logins, die letzte Adresse, die
eigenen Adressen, die eigene Serverliste und die eigenen Logins. Dazu
stehen die **Regeln des Bereichs** auf der Seite: wer hier hineinkommt,
was die Suche darf und dass jeder Vorgang festgehalten wird. Jeder Owner
sieht nur seinen eigenen Datensatz, nie den der anderen: die
Loginversuche der anderen stehen zwar in derselben Tabelle, werden aber
für den Self-Reiter gar nicht erst abgefragt.

## Adressen

Zu jeder Anmeldung wird die Adresse festgehalten, von der sie kam
(`X-Forwarded-For`, sonst die Adresse des Proxys). Zweck: ungewöhnliche
Anmeldungen bemerken, den Anmeldeweg gegen Missbrauch schützen und
sehen, von wo der Bot und der Bereich benutzt werden. Nach
`LOUCKUP_IP_AUFBEWAHREN_TAGE` Tagen (Standard 90) wird die Adresse
entfernt — nicht die Zeile, nur die Adresse.

Zu sehen sind sie im Reiter **IP** (eigene oder per ID), auf **Self**
und in der Suche bei Konten, die sich hier angemeldet haben. Bei
anderen Konten nur die Adressen von Anmeldungen, die hier wirklich eine
Sitzung bekommen haben.

Eine Adresse sagt, welche Leitung eine Anfrage geschickt hat — nicht,
wer davor saß. Sie ist ein Hinweis, kein Beweis.

### Ort zu einer Adresse

Im Reiter IP lässt sich eine Adresse eingeben; die Antwort zeigt Stadt,
Region, Land, Koordinaten, Zeitzone und das Netz dahinter, dazu eine
Karte mit Markierung. Dafür gilt:

* **Eigenes Modul, eigener Weg.** `louckup_app/geo.py` importiert nichts
  aus dem Projekt — nicht `bot`, nicht `phantom`, nicht `dashboard`,
  nicht einmal die eigene Konfiguration. Es kennt eine Adresse, eine
  Anfrage und eine Antwort.
* **Die Karte kommt von niemandem.** Sie liegt als `static/welt.svg`
  im Bereich (Küstenlinie aus Natural Earth, Public Domain). Keine
  Kartenkacheln von fremden Servern, keine Anfrage an einen
  Kartendienst beim Öffnen der Seite.
* **Zoomen ohne Skript.** Drei Ausschnitte derselben Karte liegen
  übereinander, umgeschaltet wird über ein verstecktes Feld und CSS —
  `Welt`, `Nah` (beim Fund vorbelegt) und `Ganz nah`. Beim Einschalten
  fährt die Ebene kurz auf den Punkt zu. Die Markierung wird auf jeder
  Stufe gegengerechnet, damit sie immer gleich groß bleibt und mit
  einem weichen Puls auf sich aufmerksam macht.
* **Interne Adressen bleiben innen.** Was nicht weltweit routebar ist
  (10.x, 192.168.x, 127.x …), wird nicht an den Geodienst geschickt,
  sondern gleich mit einer Meldung beantwortet.
* **Ergebnisse werden nicht gespeichert**, nur dass jemand nach einer
  Adresse gefragt hat (Zeitpunkt, Konto, Adresse des Fragenden).
* **Bremse:** höchstens `LOUCKUP_IP_SUCHEN_LIMIT` (Standard 30)
  Abfragen pro Minute und Absender.

## Optik

Der Bereich sieht aus wie das Haupt-Dashboard: gleicher Grundton
(`#0a0a0c`), gleiche Karten (`#131318`, Rand `#1e1f22`, Radius 24px),
gleiches Blurple (`#5865f2`), 48px hohe Eingabefelder, gruppierte
Seitenleiste mit Symbolen. Umgesetzt ist es in einem eigenen
Stylesheet (`louckup_app/static/css/louckup.css`) — drüben ist
Tailwind, hier nicht, deshalb sind die Werte von Hand nachgezogen.

Die Seitenleiste steht **immer** da: auf breiten Schirmen links, auf
schmalen oben als eine Reihe zum Wischen. Es gibt nichts aufzuklappen,
kein Overlay und keinen Weichzeichner — die Reinamen sind immer einen
Klick entfernt.

Aufgeklappt werden nur die Listen selbst, und auch das ohne Skript:
die Server sind native `<details>`-Elemente. Die
Content-Security-Policy des Bereichs lässt kein Skript zu, und so
bleibt sie es auch.

## Struktur

```text
louckup/
├── louckup_app/
│   ├── config.py
│   ├── auth.py        OAuth + eigener Session-Signer (eigener Salt)
│   ├── db.py          eigene SQLite: users, user_guilds, bots,
│   │                  login_attempts
│   ├── discord_api.py die paar Bot-Token-Endpunkte, Avatar- und
│   │                  Symbol-URLs, Zeitangaben
│   ├── geo.py         Ort zu einer Adresse — eigenes Modul, ohne
│   │                  Verbindung zum Rest des Projekts
│   ├── krypto.py      Bot-Tokens verschlüsselt ablegen
│   ├── main.py        Routen: / /login /auth/discord /auth/callback
│   │                           /dashboard /logout /healthz
│   │                  Einstellungen: Bots anlegen, prüfen, entfernen
│   ├── templates/     base, login, dashboard
│   │   └── partials/  platzhalter.html, self.html, discord-ids.html,
│   │                  einstellungen.html, symbole.html (SVG-Makros)
│   ├── static/css/    eigenes Styling nach Dashboard-Vorbild
│   └── static/welt.svg  Karte fuer den Reiter IP (Natural Earth)
├── tests/             test_louckup_flow.py (157 Pruefungen)
├── requirements.txt
├── .env.example
└── run_louckup.py     nur für den Standalone-Betrieb
```

## Einrichten

1. **Eigene Discord-Application** anlegen (nicht die vom Hauptbot/Phantom)
2. OAuth2 → Redirects: `https://<deine-url>/louckup/auth/callback`
3. Client-ID/Secret nach `LOUCKUP_DISCORD_CLIENT_ID` / `..._SECRET`
4. `LOUCKUP_OWNER_IDS` setzen (kommagetrennt) — leer bedeutet: es gilt
   `OWNER_IDS` aus der Hauptkonfiguration
5. `LOUCKUP_SECRET_KEY` setzen (sonst: `DASHBOARD_API_KEY`)
6. Redeploy — `start.sh` setzt `LOUCKUP_BASE_URL` automatisch aus
   `RAILWAY_PUBLIC_DOMAIN`

## Absicherung

* **Sicherheits-Header** auf jeder Seite: eine enge
  Content-Security-Policy (Skripte und CSS nur vom Bereich selbst,
  Bilder nur von `cdn.discordapp.com`), `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`.
* **Kein Browser-Cache**: alle HTML-Seiten gehen mit
  `Cache-Control: no-store, private` raus — wichtig auf geteilten
  Rechnern.
* **Login-Rate-Limit**: höchstens `LOUCKUP_LOGIN_RATE_LIMIT`
  (Standard 10) Anläufe von „Mit Discord anmelden" pro Minute und
  Adresse, danach HTTP 429.
* **OAuth-State** wird geprüft, bevor der Code getauscht wird.
* **Owner-Prüfung zweimal**: beim Login und bei jedem Reiter-Aufruf.

## Bots und Suche

### Einstellungen

* Der **Hauptbot** ist fest eingebaut: sein Token kommt aus der Umgebung
  (`TOKEN`) — es gibt keine zweite Variable und keinen Datenbankeintrag.
  Er lässt sich nicht entfernen.
* Weitere Bots: **nur den Token einfügen.** Name und Bild holt der
  Bereich beim Eintragen selbst bei Discord — der Anwendungsname aus dem
  Entwicklerportal, sonst der Kontoname. Für den Hauptbot gilt dasselbe,
  er wird beim Öffnen der Seite abgefragt (Ergebnis gilt fünf Minuten).
* Beim Hinzufügen wird der Token gegen Discord geprüft; erst wenn er
  gilt, wird er gespeichert. „Neu abfragen" und „Prüfen" holen Name und
  Bild erneut.
* Tokens liegen **verschlüsselt** in `louckup.db` (Fernet, Schlüssel aus
  `LOUCKUP_SECRET_KEY`) und werden auf der Seite nur maskiert angezeigt.
* Jede Aktion steht hinter einem **CSRF-Token**, damit keine fremde
  Seite im Namen eines eingeloggten Owners Bots hinzufügen oder löschen
  kann.

### Discord IDs

Eine Discord-ID eingeben → der Bereich fragt **alle** eingetragenen Bots
ab und zeigt:

* öffentliches Profil: Name, Anzeigename, Avatar, Erstellungsdatum samt
  Alter, Abzeichen, Profilfarbe, Bot ja/nein
* **eigene Aufzeichnung**: hat das Konto diesem Bereich selbst Rechte
  eingeräumt, steht hier mehr — E-Mail, verifiziert ja/nein, die
  genehmigten Rechte, wie lange der Zugangs-Token gilt und die
  Serverliste genau vom Zeitpunkt der Autorisierung. Wichtig: der Token
  selbst wird nie ausgegeben, nur dass es einen gibt.
* **alle** Server jedes Bots, aufklappbar — und zwar nicht nur die
  Treffer: zu jedem Server steht dabei, ob die Person dort ist, ob nicht,
  oder ob die Obergrenze erreicht war, bevor er drankam
* zu jedem Treffer: Server-ID, Nickname, Beitritt mit Uhrzeit und
  „vor wie vielen Tagen", Stumm-Schaltung, Boost seit, Freigabestatus
  und alle Rollen beim Namen

**Warum bei den meisten IDs keine E-Mail steht:** Discord gibt eine
E-Mail-Adresse ausschließlich dem Konto selbst heraus — und nur dann,
wenn es einer Anwendung den Scope `email` genehmigt. Für eine fremde ID
gibt es keinen Endpunkt, auch nicht für einen Bot-Token: nicht mit
mehr Rechten, nicht mit einem anderen Scope, nicht über einen Umweg.
Wer also nie hier eingeloggt war, hat in dieser Anzeige eine leere
Zeile — das ist keine fehlende Berechtigung, sondern eine Wand in der
API.

Ebenso wenig sagt Discord einer Anwendung, wo ein Konto sonst noch was
genehmigt hat. Ob jemand einen der Bots aus den Einstellungen mit
`email` autorisiert hat, lässt sich von hier aus nicht feststellen;
die Anzeige nennt nur, was diesem Bereich selbst eingeräumt wurde.

Technische Bremsen: höchstens `LOUCKUP_LOOKUP_MAX_REQUESTS` (Standard
250) Anfragen pro Suche, 5 gleichzeitig, 12 Sekunden Zeitlimit je
Anfrage.

## Datenschutz-Hinweis

Weil `email` und `guilds` angefragt werden, liegen E-Mail-Adresse und
Serverliste in `louckup.db`. Die Serverliste wird für Nicht-Owner nicht
einmal geladen.

Die Suche zeigt zu einer ID, was dieser Bereich über sie gespeichert
hat — E-Mail, Serverstand und die Adressen ihrer Anmeldungen. Das sind
ausschließlich Angaben, die das betroffene Konto diesem Bereich bei
seinem eigenen Login selbst übergeben hat; für alle anderen IDs bleibt
die Zeile leer.

**Nie** ausgegeben werden der Zugangs- und der Auffrisch-Token. Sie
stehen in der Datenbank, damit der Bereich funktioniert, erscheinen
aber auf keiner Seite — auch nicht in der Suche, wo nur steht, dass es
einen gibt und wie lange er gilt.
