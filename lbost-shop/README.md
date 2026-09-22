# LBoost Shop (`/lbost-shop`)

Vollständig isolierter University-Bot-Unterbereich mit eigener Discord-OAuth-Anwendung, eigenem signiertem Cookie und eigener Zugriffsliste.

## Routen

- `/lbost-shop` – kurze Einordnung als University-Bot-Unterbereich
- `/lbost-shop/Login` – Loginseite
- `/lbost-shop/auth/callback` – Discord OAuth Redirect
- `/lbost-shop/auth/success` – sichtbare Erfolgsmeldung vor der Weiterleitung
- `/lbost-shop/dashboard` – nur autorisierte IDs und University-Bot-Owner
- `/lbost-shop/healthz` – technische Statusantwort ohne Secrets

## Railway-Variablen

```text
LBOST_SHOP_DISCORD_CLIENT_ID
LBOST_SHOP_DISCORD_CLIENT_SECRET
LBOST_SHOP_SECRET_KEY
LBOST_SHOP_AUTHORIZED_IDS
LBOST_SHOP_BOT_TOKEN
```

Optional: `LBOST_SHOP_OWNER_IDS`, `LBOST_SHOP_BASE_URL`, `LBOST_SHOP_COOKIE_PATH`, `LBOST_SHOP_FALLBACK_URL`, `LBOST_SHOP_OAUTH_SCOPES`.

`LBOST_SHOP_AUTHORIZED_IDS` ist die neue, separate Freigabeliste. Zusätzlich sind alle IDs aus `LBOST_SHOP_OWNER_IDS` beziehungsweise der vorhandenen globalen `OWNER_IDS` zugelassen. Nicht autorisierte Konten erhalten niemals ein Session-Cookie und werden nach `/` weitergeleitet. Der Bot-Token ist bereits als eigene Variable reserviert; der Bot selbst bekommt erst mit den späteren Shop-Funktionen Gateway-Code.

Im Discord Developer Portal muss exakt diese Redirect-URI stehen:

```text
https://DEINE-DOMAIN/lbost-shop/auth/callback
```
