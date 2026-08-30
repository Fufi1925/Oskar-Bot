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
| Discord IDs | Platzhalter |
| Roblox User | Platzhalter |
| IP | Platzhalter |
| Self | die eigenen Daten des eingeloggten Kontos |

**Self** zeigt ausschließlich die Daten des Accounts, der gerade
eingeloggt ist — Discord-ID, Namen, E-Mail, Verifiziert-Status,
genehmigte Scopes, Zeitpunkte des ersten und letzten Logins und die
eigene Serverliste. Jeder Owner sieht nur seinen eigenen Datensatz, nie
den der anderen.

## Struktur

```text
louckup/
├── louckup_app/
│   ├── config.py
│   ├── auth.py        OAuth + eigener Session-Signer (eigener Salt)
│   ├── db.py          eigene SQLite: users, login_attempts
│   ├── main.py        Routen: / /login /auth/discord /auth/callback
│   │                           /dashboard /logout /healthz
│   ├── templates/     base, login, dashboard
│   │   └── partials/  platzhalter.html, self.html
│   └── static/css/    eigenes Styling
├── tests/             test_louckup_flow.py (53 Pruefungen)
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

## Datenschutz-Hinweis

Weil `email` und `guilds` angefragt werden, liegen E-Mail-Adresse und
Serverliste in `louckup.db`. Aktuell wird die E-Mail nur angezeigt; die
Serverliste wird für Nicht-Owner **nicht einmal geladen**.
