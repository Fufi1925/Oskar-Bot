# LBoost Shop (`/lbost-shop`)

Vollständig isolierter University-Bot-Unterbereich mit eigener Discord-OAuth-Anwendung, verschlüsselten serverseitigen OAuth-Sitzungen, eigener Zugriffsliste und eigener Server-Freigabeliste.

## Routen

- `/lbost-shop` – kurze Einordnung als University-Bot-Unterbereich
- `/lbost-shop/Login` – Loginseite
- `/lbost-shop/auth/callback` – Discord OAuth Redirect
- `/lbost-shop/auth/success` – sichtbare Erfolgsmeldung vor der Weiterleitung
- `/lbost-shop/dashboard` – streng gefilterte Serverliste
- `/lbost-shop/admin` – leerer Platzhalter ausschließlich für bestehende Owner-IDs
- `/lbost-shop/healthz` – technische Statusantwort ohne Secrets

## Railway-Variablen

```text
LBOST_SHOP_DISCORD_CLIENT_ID
LBOST_SHOP_DISCORD_CLIENT_SECRET
LBOST_SHOP_SECRET_KEY
LBOST_SHOP_TOKEN_ENCRYPTION_KEY
LBOST_SHOP_AUTHORIZED_IDS
LBOST_SHOP_ALLOWED_GUILD_IDS
LBOST_SHOP_BOT_TOKEN
```

Optional: `LBOST_SHOP_OWNER_IDS`, `LBOST_SHOP_BASE_URL`, `LBOST_SHOP_COOKIE_PATH`, `LBOST_SHOP_FALLBACK_URL`, `LBOST_SHOP_OAUTH_SCOPES`, `LBOST_SHOP_DB_PATH`.

- `LBOST_SHOP_AUTHORIZED_IDS`: Nutzer, die sich zusätzlich zu den globalen Ownern anmelden dürfen.
- `LBOST_SHOP_ALLOWED_GUILD_IDS`: einzige Server-IDs, die grundsätzlich im Shop-Dashboard erscheinen dürfen.
- `LBOST_SHOP_OWNER_IDS`: optionale zusätzliche Shop-Owner. Sie werden mit allen vorhandenen globalen `OWNER_IDS` vereinigt. Nur diese Owner-Gesamtmenge sieht und erreicht `/admin`.
- `LBOST_SHOP_TOKEN_ENCRYPTION_KEY`: getrenner Schlüssel für verschlüsselte Discord Access- und Refresh-Tokens.
- `LBOST_SHOP_BOT_TOKEN`: Token des separaten Shop-Bots; seine aktuellen Server werden bei jedem Dashboard-Aufruf mit Discord abgeglichen.

Ein Server wird nur angezeigt, wenn **alle** Bedingungen stimmen:

1. Seine ID steht in `LBOST_SHOP_ALLOWED_GUILD_IDS`.
2. Der separate Shop-Bot ist aktuell auf dem Server.
3. Der angemeldete Nutzer ist Serverinhaber oder besitzt `Administrator` beziehungsweise `Server verwalten`.

Wenn eine Discord-Prüfung fehlschlägt, wird sicherheitshalber kein Server aus veralteten Daten angezeigt.

## OAuth

Standard-Scopes:

```text
identify email guilds guilds.join gdm.join
```

Damit fragt Discord Identität, E-Mail, Serverliste, Serverbeitritt und den Beitritt zu verwalteten Gruppen-DMs ab. Das Lesen oder Schreiben privater Benutzer-DMs ist für gewöhnliche Discord-Anwendungen nicht verfügbar und wird bewusst nicht vorgetäuscht. Der Bot kann später eigene DMs an Nutzer senden.

Im Discord Developer Portal muss exakt diese Redirect-URI stehen:

```text
https://DEINE-DOMAIN/lbost-shop/auth/callback
```

Nicht autorisierte Konten erhalten niemals ein Session-Cookie und werden nach `/` weitergeleitet. OAuth-Tokens liegen ausschließlich verschlüsselt in der serverseitigen SQLite-Datenbank, niemals im Browser-Cookie.
