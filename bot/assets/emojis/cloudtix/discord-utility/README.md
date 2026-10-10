# CloudTIX Utility Emojis

24 neue Utility-Emojis im Stil farbiger Discord-Badges: stark gerundete
Kacheln, kräftige Farben, weicher Verlauf und große weiße Symbole. Transparent,
128 × 128 Pixel und unter Discords 256-KB-Grenze. Eigene Vektorkacheln mit
Lucide-Glyphen; die Lizenz steht in [LICENSE.lucide.txt](LICENSE.lucide.txt).

Für Bot-Nachrichten in Discord, automatisch beim Start als Application Emojis
hochgeladen. Die Dashboard-Auswahl enthält weiterhin die weißen Symbole.
Dieses Set wird zuletzt geladen und liefert die Standard-Bot-Symbole für
Bestätigung, Fehler, Tickets, Premium, Musik und weitere Aktionen.

```python
from utils.emoji import EMOJIS, TICK, CT_UTILITY_SUPPORTER

await ctx.send(f"{TICK} Verifiziert!")
await ctx.send(f"{CT_UTILITY_SUPPORTER} Danke für deinen Support!")
await ctx.send(f"{EMOJIS['utility_premium']} Premium ist aktiv.")
```

Die echten Discord-Codes entstehen beim Upload. Ohne verfügbare ID wird ein
passendes Unicode-Symbol verwendet. Vorhandene Application Emojis werden nicht
gelöscht. Vektorquellen stehen unter `sources/`, regenerierbar mit
`python scripts/export_cloudtix_utility_emojis.py`.

| Name | Farbe | Kategorie | Vorschau | Bot-Code |
| --- | --- | --- | --- | --- |
| utility_verified | green | Security | [PNG](utility_verified.png) | `EMOJIS["utility_verified"]` |
| utility_supporter | purple | Community | [PNG](utility_supporter.png) | `EMOJIS["utility_supporter"]` |
| utility_error | red | UI | [PNG](utility_error.png) | `EMOJIS["utility_error"]` |
| utility_warning | gold | UI | [PNG](utility_warning.png) | `EMOJIS["utility_warning"]` |
| utility_info | blue | UI | [PNG](utility_info.png) | `EMOJIS["utility_info"]` |
| utility_shield | cyan | Security | [PNG](utility_shield.png) | `EMOJIS["utility_shield"]` |
| utility_ticket | blue | Support | [PNG](utility_ticket.png) | `EMOJIS["utility_ticket"]` |
| utility_premium | purple | Community | [PNG](utility_premium.png) | `EMOJIS["utility_premium"]` |
| utility_staff | indigo | Security | [PNG](utility_staff.png) | `EMOJIS["utility_staff"]` |
| utility_boost | pink | Community | [PNG](utility_boost.png) | `EMOJIS["utility_boost"]` |
| utility_gift | pink | Community | [PNG](utility_gift.png) | `EMOJIS["utility_gift"]` |
| utility_trophy | gold | Community | [PNG](utility_trophy.png) | `EMOJIS["utility_trophy"]` |
| utility_star | gold | Community | [PNG](utility_star.png) | `EMOJIS["utility_star"]` |
| utility_lock | orange | Security | [PNG](utility_lock.png) | `EMOJIS["utility_lock"]` |
| utility_unlock | green | Security | [PNG](utility_unlock.png) | `EMOJIS["utility_unlock"]` |
| utility_music | blue | Music | [PNG](utility_music.png) | `EMOJIS["utility_music"]` |
| utility_play | green | Music | [PNG](utility_play.png) | `EMOJIS["utility_play"]` |
| utility_pause | gold | Music | [PNG](utility_pause.png) | `EMOJIS["utility_pause"]` |
| utility_stop | red | Music | [PNG](utility_stop.png) | `EMOJIS["utility_stop"]` |
| utility_settings | gray | UI | [PNG](utility_settings.png) | `EMOJIS["utility_settings"]` |
| utility_members | cyan | Community | [PNG](utility_members.png) | `EMOJIS["utility_members"]` |
| utility_ping | pink | UI | [PNG](utility_ping.png) | `EMOJIS["utility_ping"]` |
| utility_chat | cyan | Support | [PNG](utility_chat.png) | `EMOJIS["utility_chat"]` |
| utility_clock | orange | UI | [PNG](utility_clock.png) | `EMOJIS["utility_clock"]` |
