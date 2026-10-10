# LBoost Shop (`/lbost-shop`)

Isolierter Unterbereich von CloudTIX mit eigener Discord-App, verschlüsselten OAuth-Sitzungen, eigenem Bot-Prozess und vollständig serverbezogener Modulkonfiguration.

## Zugriff

Ein Server wird nur angezeigt, wenn alle Bedingungen stimmen:

1. Seine ID steht in `LBOST_SHOP_ALLOWED_GUILD_IDS`.
2. Der separate Shop-Bot ist aktuell auf dem Server.
3. Der Nutzer ist Serverinhaber oder besitzt `Administrator` beziehungsweise `Server verwalten`.

Diese Bedingungen werden bei jedem geschützten Aufruf erneut mit Discord abgeglichen — kurz gecacht (20 Sekunden für die Serverliste, 45 Sekunden für Kanäle, Rollen und Serverzahlen), damit ein Klick nicht fünf Anfragen an Discord kostet. Wenn Discord nicht antwortet, bleibt die Liste leer; es wird nichts aus einem alten Zustand ergänzt. Nur globale `OWNER_IDS` und zusätzliche `LBOST_SHOP_OWNER_IDS` sehen `/lbost-shop/admin`.

## Dashboard-Oberfläche

Nach dem Login verwendet der komplette geschützte Bereich dieselbe Dashboard-Struktur wie CloudTIX: echtes Logo und festes Branding, Glass-Sidebar, gruppierte Servernavigation, mobile Navigation mit Overlay, Sticky-Topbar, globale Modulsuche, Benachrichtigungs-Popover und Profilmenü. Dashboard, Serverübersicht, sämtliche Modulformulare und das Owner-Admin-Panel teilen sich diese Shell.

Oben rechts sitzt der **Bot-Status**, keine Sprachumschaltung: Der Bot-Prozess schreibt alle 20 Sekunden einen Herzschlag in die Datenbank, die Seite zeigt „Bot online · N Server" oder den Abstand der letzten Meldung. „Online" steht also nicht mehr da, wenn der Prozess tot ist — und `/healthz` meldet dasselbe.

`/servers` entspricht der CloudTIX-Serverauswahl mit Kennzahlen, Namens-/ID-Suche, Sortierung nach Mitgliedern oder Namen, Serverkarten, Besitzerstatus und Mitgliederzahlen. Die Detailübersicht eines Servers übernimmt den Aufbau der CloudTIX-Übersicht mit Übersicht-/Sicherung-Reitern, Tarifzeile (aktive Module, Ticket- und Verwarnungszahl), dynamischem Einrichtungsfortschritt, einfarbigen Lucide-artigen SVG-Symbolen, Mitglieder-/Kanal-/Rollen-/Ticket-Kennzahlen, Boost- und Sicherheitsstatus, 14-Tage-Konfigurationsverlauf, „Als Nächstes", „Eingerichtet" und „Noch offen". Unicode-Emoji-Modulsymbole werden im Dashboard nicht verwendet. Über „Sicherung" lassen sich alle Servermodule exportieren und sicher wieder einspielen. Nicht freigegebene Server bleiben vollständig verborgen.

Füllgrade und Diagrammbalken laufen über generierte CSS-Klassen (`.ub-fill-0` … `.ub-fill-100`, `.ub-h-6` … `.ub-h-100`), nicht über `style`-Attribute: Die Content-Security-Policy des Shops hält `style-src 'self'` ohne `unsafe-inline`, und ein einzelnes Inline-Style hätte sonst stillschweigend alles auf 0 px Höhe rendern lassen.

## Dashboard-Module

- **Advanced Tickets:** mehrere Panels und Kategorien pro Server, eigene Rollen und Rechte je Panel, Knopftexte mit eigenen Emojis, Übernehmen/Schließen/Löschen, HTML-Transkript in den Log-Kanal (vollständig paginiert, mit Nachrichtenanzahl), Slowmode, Kanalname mit Nummer, Überschrift/Begrüßung/Bestätigung mit Platzhaltern `{ticket_number}`, `{user}`, `{category}`, `{server}`, `{channel}` und bis zu fünf Formularfragen (kurz, Absatz, Bild) vor dem Öffnen. Unter dem Formular zeigt eine **Vorschau**, was der Bot sendet — gerechnet im Bot über dieselbe Funktion (`lbost_shop_app/regeln.py`), nicht nachgebaut im Browser.
- **Moderation:** Warn, Timeout, Kick und Ban als Slash Commands mit Rollenprüfung, Fallnummern und Bot-Rechtecheck vor der Tat. Anti-Spam (Eimer pro Nutzer und Kanal, Löschen der ganzen Serie) und Anti-Link mit Domainausnahmen; Ausnahmen über Rollen. Die Verwarnungen des Servers stehen im Dashboard und lassen sich einzeln wieder entfernen.
- **Welcome & Leave:** eigene Kanäle, Texte, Bilder und Platzhalter (`{user}`, `{server}`, `{member_count}`, `{channel}`) für Join und Leave.
- **Reaction Roles:** beliebig viele Panels mit Rollenknöpfen; der Bot lehnt sauber ab, wenn eine Rolle zu hoch sitzt, verwaltet wird oder nicht mehr existiert.
- **Automation:** Auto-Antworten mit Abkühlzeit, eigene `!`-Befehle und Intervall-Ankündigungen. Der nächste Sendelauf liegt in einer eigenen Zustandstabelle — vorher schrieb der Worker die komplette Benutzerkonfiguration zurück und konnte ein parallel gespeichertes Formular überschreiben.
- **Logging:** Member-, Nachrichten-, Moderations-, Rollen-, Kanal- und Ticketlogs.
- **Giveaways:** persistente Teilnehmer, Pflichtrolle optional, automatische Ziehung, Reroll. Gewinnen kann nur, wer noch auf dem Server ist; ein Wettbewerb lässt sich genau einmal auflösen.

## Eingabeprüfung

Formulare und Importdateien laufen durch dieselbe Prüfung: Zahlen nur im erlaubten Bereich (`spam_limit` 3–100, `slowmode_seconds` 0–30, `default_winners` 1–20, `spam_timeout_minuten` 1–1440), IDs nur Ziffern, Farben als `#rrggbb`, Bild-URLs nur `http(s)` mit maximal 600 Zeichen, JSON maximal 50 Einträge und 32 KB, Fragen auf fünf begrenzt (Labels 45, Hinweise 100 Zeichen), Panels nur mit gültigem, eindeutigem `key`. Bei einem Fehler bleibt der alte Stand komplett stehen — es wird kein halbes Formular gespeichert. Importe schreiben ausschließlich bekannte Felder bekannter Module.

## Admin-Panel (nur Owner)

Freigegebene Konten und Server, alle aktiven Sitzungen mit Anmeldezeitpunkt und „Alle abmelden" (danach ist auch die eigene Sitzung weg, der Hinweis erscheint auf der Login-Seite), der Änderungsverlauf der letzten Einträge und die Zahl der Konfigurationen. Tokens werden nirgends angezeigt. Der Verlaufsgraph zählt nur echte Speicherung: Laufzeitschreiben des Bots landen nicht mehr im Protokoll, und der Aufräumlauf beim Start hält die Tabelle bei 45 Tagen.

## Discord-Befehle

```text
/ticket-panel   /reaction-panel
/warn           /warnings       /clearwarnings
/mute           /kick           /ban
/giveaway       /giveaway-reroll
/announce
```

Interaktive Discord-Nachrichten werden als Components V2 erzeugt. Standardbuttons verwenden keine Unicode-Emojis; Custom Emojis können im Dashboard hinterlegt werden. Ticket-, Rollen- und Giveaway-Knöpfe funktionieren nach Neustarts weiter, weil ihre IDs global verarbeitet und alle Zustände persistent gespeichert werden. Ein Modal wird immer vor `defer()` gesendet — nach einer Deferred-Antwort lehnt Discord ein Modal ab.

## Hintergrund-Bot

`start.sh` startet `/app/lbost-shop/run_bot.py` als getrennten Hintergrundprozess, sobald `LBOST_SHOP_BOT_TOKEN` gesetzt ist. Discord.py übernimmt Reconnects; beim Container-Stopp wird der Prozess sauber beendet. Der Bot teilt weder Cogs noch Sessions mit CloudTIX, Phantom oder Louckup.

Damit die Datenbank unter Last nicht vollläuft, hält der Shop eine SQLite-Verbindung pro Thread offen und schließt sie über einen Kontextmanager, der garantiert committet (`with connection:` allein committet, schließt aber nicht — 150 Lesungen waren 150 offene Datei-Deskriptoren).

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

## Tests

```bash
cd lbost-shop
PYTHONPATH=$PWD python3 tests/run_all.py
```

Sieben Dateien, ohne Netzwerk: Regelmodul (Vorschau == Bot), Datenbankschicht (Verbindungen, Verläufe, Fallnummern, Giveaway-Zyklen), Formular- und Endpunktprüfung, OAuth-Ablauf mit Serverfilter, Dashboard-Aufbau als Textprüfung und ein Bot-Lauf gegen gefälschte Discord-Objekte. Alle Prüfungen sind so gebaut, dass sie rot werden, wenn die zugehörige Sicherung fehlt — nachgeprüft mit 32 Mutationen (32 gefangen).
