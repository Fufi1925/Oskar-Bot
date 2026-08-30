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
| IP | Platzhalter |
| Self | die eigenen Daten des eingeloggten Kontos |
| Einstellungen | Bots eintragen, prüfen, entfernen — nur mit Token, Name und Bild kommen von selbst |

**Self** zeigt ausschließlich die Daten des Accounts, der gerade
eingeloggt ist — Discord-ID, Namen, E-Mail, Verifiziert-Status,
genehmigte Scopes, Zeitpunkte des ersten und letzten Logins, die eigene
Serverliste und die eigenen Logins. Jeder Owner sieht nur seinen eigenen
Datensatz, nie den der anderen: die Loginversuche der anderen stehen
zwar in derselben Tabelle, werden aber für den Self-Reiter gar nicht
erst abgefragt.

## Optik

Der Bereich sieht aus wie das Haupt-Dashboard: gleicher Grundton
(`#0a0a0c`), gleiche Karten (`#131318`, Rand `#1e1f22`, Radius 24px),
gleiches Blurple (`#5865f2`), 48px hohe Eingabefelder, gruppierte
Seitenleiste mit Symbolen. Umgesetzt ist es in einem eigenen
Stylesheet (`louckup_app/static/css/louckup.css`) — drüben ist
Tailwind, hier nicht, deshalb sind die Werte von Hand nachgezogen.

Aufgeklappt wird ohne Skript: die Serverlisten sind native
`<details>`-Elemente, die Seitenleiste auf dem Handy ein verstecktes
Feld mit CSS dahinter. Die Content-Security-Policy des Bereichs lässt
kein Skript zu, und so bleibt sie es auch.

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
│   ├── krypto.py      Bot-Tokens verschlüsselt ablegen
│   ├── main.py        Routen: / /login /auth/discord /auth/callback
│   │                           /dashboard /logout /healthz
│   │                  Einstellungen: Bots anlegen, prüfen, entfernen
│   ├── templates/     base, login, dashboard
│   │   └── partials/  platzhalter.html, self.html, discord-ids.html,
│   │                  einstellungen.html, symbole.html (SVG-Makros)
│   └── static/css/    eigenes Styling nach Dashboard-Vorbild
├── tests/             test_louckup_flow.py (106 Pruefungen)
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
* **alle** Server jedes Bots, aufklappbar — und zwar nicht nur die
  Treffer: zu jedem Server steht dabei, ob die Person dort ist, ob nicht,
  oder ob die Obergrenze erreicht war, bevor er drankam
* zu jedem Treffer: Server-ID, Nickname, Beitritt mit Uhrzeit und
  „vor wie vielen Tagen", Stumm-Schaltung, Boost seit, Freigabestatus
  und alle Rollen beim Namen

**Was die Suche nicht kann, und warum:** E-Mail-Adressen und die Frage,
wo der User einem Bot den Scope `guilds` bestätigt hat, sind über
Bot-Tokens technisch nicht erreichbar — dafür bräuchte es das
OAuth-Token der betroffenen Person. Solche Daten für fremde Zwecke
auszulesen verstößt gegen die DSGVO und gegen Discords
Entwicklerrichtlinien. E-Mail-Adressen bleiben deshalb auf den
Self-Reiter beschränkt: dort sieht jede Person ausschließlich ihre
eigene.

Technische Bremsen: höchstens `LOUCKUP_LOOKUP_MAX_REQUESTS` (Standard
250) Anfragen pro Suche, 5 gleichzeitig, 12 Sekunden Zeitlimit je
Anfrage.

## Datenschutz-Hinweis

Weil `email` und `guilds` angefragt werden, liegen E-Mail-Adresse und
Serverliste in `louckup.db`. Die E-Mail wird nur angezeigt; die
Serverliste wird für Nicht-Owner nicht einmal geladen.
