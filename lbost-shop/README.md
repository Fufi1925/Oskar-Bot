# LBoost Shop (`/lbost-shop`)

Isolierter University-Bot-Unterbereich mit eigener Discord-App, verschlüsselten OAuth-Sitzungen, eigenem Bot-Prozess und vollständig serverbezogener Modulkonfiguration.

## Zugriff

Ein Server wird nur angezeigt, wenn alle Bedingungen stimmen:

1. Seine ID steht in `LBOST_SHOP_ALLOWED_GUILD_IDS`.
2. Der separate Shop-Bot ist aktuell auf dem Server.
3. Der Nutzer ist Serverinhaber oder besitzt `Administrator` beziehungsweise `Server verwalten`.

Diese Bedingungen werden bei jedem geschützten Aufruf erneut mit Discord abgeglichen. Nur globale `OWNER_IDS` und zusätzliche `LBOST_SHOP_OWNER_IDS` sehen `/lbost-shop/admin`.

## Dashboard-Oberfläche

Nach dem Login verwendet der komplette geschützte Bereich dieselbe University-Bot-Dashboard-Struktur: echtes University-Bot-Logo und festes Branding, Glass-Sidebar, gruppierte Servernavigation, mobile Navigation mit Overlay, Sticky-Topbar, globale Modulsuche, Benachrichtigungs-Popover, DE/EN-Sprachwahl und Profilmenü. Dashboard, Serverübersicht, sämtliche Modulformulare und das Owner-Admin-Panel teilen sich diese Shell.

`/servers` entspricht der University-Serverauswahl mit Kennzahlen, Namens-/ID-Suche, Sortierung nach Mitgliedern oder Namen, Serverkarten, Besitzerstatus und Mitgliederzahlen. Die Detailübersicht eines Servers übernimmt den Aufbau der University-Übersicht mit Übersicht-/Sicherung-Reitern, Tarifzeile, dynamischem Einrichtungsfortschritt, einfarbigen Lucide-artigen SVG-Symbolen, Mitglieder-/Kanal-/Rollen-/Bot-Kennzahlen, Präfix, Boost- und Sicherheitsstatus, 14-Tage-Konfigurationsverlauf, „Als Nächstes“, „Eingerichtet“ und „Noch offen“. Unicode-Emoji-Modulsymbole werden im Dashboard nicht verwendet. Über „Sicherung“ lassen sich alle Servermodule exportieren und sicher wieder einspielen. Nicht freigegebene Server bleiben vollständig verborgen.

## Dashboard-Module

- **Advanced Tickets:** mehrere Panel-Konfigurationen und Kategorien, eigene Rollen, Berechtigungen, Button-Texte und Custom Emojis, Claim/Close/Delete, HTML-Transkripte, Log-Kanal, Components-V2-Layouts, Farben, Bilder, Thumbnail und Footer.
- **Moderation:** Warn, Timeout, Kick und Ban als Slash Commands; Anti-Spam, Anti-Link, Ausnahmen und Moderationslogs.
- **Welcome & Leave:** eigene Kanäle, Texte, Platzhalter und Bilder für Join und Leave.
- **Reaction Roles:** beliebig konfigurierte Rollenbuttons und mehrere Panels.
- **Automation:** Auto-Antworten, eigene `!`-Commands und intervallbasierte Ankündigungen.
- **Logging:** Member-, Nachrichten-, Moderations-, Rollen-, Kanal- und Ticketlogs.
- **Giveaways:** persistente Teilnehmer, automatische Gewinner, Dauer, Gewinneranzahl und Reroll.

Der Serverbereich ist unter `/lbost-shop/guild/{SERVER_ID}` erreichbar. Änderungen landen in SQLite/WAL und werden vom Bot ohne Neustart gelesen. JSON-Felder im Dashboard enthalten direkt sichtbare Beispiele für mehrere Panels und Einträge.

## Discord-Befehle

```text
/ticket-panel
/reaction-panel
/warn
/mute
/kick
/ban
/giveaway
/giveaway-reroll
/announce
```

Interaktive Discord-Nachrichten werden als Components V2 erzeugt. Standardbuttons verwenden keine Unicode-Emojis; Custom Emojis können im Dashboard hinterlegt werden. Ticket-, Rollen- und Giveaway-Buttons funktionieren nach Deployments weiter, da ihre IDs global verarbeitet und alle Zustände persistent gespeichert werden.

## Hintergrund-Bot

`start.sh` startet `/app/lbost-shop/run_bot.py` als getrennten Hintergrundprozess, sobald `LBOST_SHOP_BOT_TOKEN` gesetzt ist. Discord.py übernimmt Reconnects; beim Container-Stopp wird der Prozess sauber beendet. Der Bot teilt weder Cogs noch Sessions mit University Bot, Phantom oder Louckup.

Im Discord Developer Portal müssen für Welcome/Leave, AutoMod und Auto-Antworten aktiviert sein:

- Server Members Intent
- Message Content Intent

Der Bot benötigt abhängig von aktivierten Modulen unter anderem `Manage Channels`, `Manage Roles`, `Moderate Members`, `Kick Members`, `Ban Members`, `Manage Messages`, `View Channel`, `Send Messages`, `Read Message History` und `Attach Files`.

## OAuth

```text
identify email guilds guilds.join
```

Gruppen-DM-Scopes sind nicht enthalten. Private Direktnachrichten werden nicht gelesen.

Redirect-URI:

```text
https://DEINE-DOMAIN/lbost-shop/auth/callback
```

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

Optional: `LBOST_SHOP_OWNER_IDS`, `LBOST_SHOP_BASE_URL`, `LBOST_SHOP_COOKIE_PATH`, `LBOST_SHOP_FALLBACK_URL`, `LBOST_SHOP_OAUTH_SCOPES`, `LBOST_SHOP_DB_PATH`, `LBOST_SHOP_BOT_LOG_LEVEL`.

Access- und Refresh-Tokens werden mit einem getrennten Schlüssel verschlüsselt in der serverseitigen Datenbank gespeichert und nie in den Browser-Cookie geschrieben. Nicht autorisierte Konten erhalten keine Sitzung.
