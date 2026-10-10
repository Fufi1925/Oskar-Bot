# CloudTIX Utility Emojis

84 neue Utility-Emojis im Stil farbiger Discord-Badges: stark gerundete
Kacheln, kräftige Farben, glänzende Lichtreflexe, dezenter Glow und große weiße
Symbole. Transparent,
128 × 128 Pixel und unter Discords 256-KB-Grenze. Eigene Vektorkacheln mit
Lucide-Glyphen; die Lizenz steht in [LICENSE.lucide.txt](LICENSE.lucide.txt).

Für Bot-Nachrichten in Discord, automatisch beim Start als Application Emojis
hochgeladen. Die Dashboard-Auswahl verwendet dieses farbige Set.
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
| utility_anti_nuke | red | Security | [PNG](utility_anti_nuke.png) | `EMOJIS["utility_anti_nuke"]` |
| utility_ban | red | Security | [PNG](utility_ban.png) | `EMOJIS["utility_ban"]` |
| utility_jail | orange | Security | [PNG](utility_jail.png) | `EMOJIS["utility_jail"]` |
| utility_protection | green | Security | [PNG](utility_protection.png) | `EMOJIS["utility_protection"]` |
| utility_blocked | red | Security | [PNG](utility_blocked.png) | `EMOJIS["utility_blocked"]` |
| utility_unprotected | gray | Security | [PNG](utility_unprotected.png) | `EMOJIS["utility_unprotected"]` |
| utility_identity | indigo | Security | [PNG](utility_identity.png) | `EMOJIS["utility_identity"]` |
| utility_key | gold | Security | [PNG](utility_key.png) | `EMOJIS["utility_key"]` |
| utility_permissions | purple | Security | [PNG](utility_permissions.png) | `EMOJIS["utility_permissions"]` |
| utility_hidden | gray | Security | [PNG](utility_hidden.png) | `EMOJIS["utility_hidden"]` |
| utility_ticket_open | green | Support | [PNG](utility_ticket_open.png) | `EMOJIS["utility_ticket_open"]` |
| utility_ticket_resolved | cyan | Support | [PNG](utility_ticket_resolved.png) | `EMOJIS["utility_ticket_resolved"]` |
| utility_ticket_close | red | Support | [PNG](utility_ticket_close.png) | `EMOJIS["utility_ticket_close"]` |
| utility_application | indigo | Support | [PNG](utility_application.png) | `EMOJIS["utility_application"]` |
| utility_transcript | gray | Support | [PNG](utility_transcript.png) | `EMOJIS["utility_transcript"]` |
| utility_support | orange | Support | [PNG](utility_support.png) | `EMOJIS["utility_support"]` |
| utility_inbox | blue | Support | [PNG](utility_inbox.png) | `EMOJIS["utility_inbox"]` |
| utility_mail | pink | Support | [PNG](utility_mail.png) | `EMOJIS["utility_mail"]` |
| utility_help | purple | Support | [PNG](utility_help.png) | `EMOJIS["utility_help"]` |
| utility_feedback | pink | Support | [PNG](utility_feedback.png) | `EMOJIS["utility_feedback"]` |
| utility_level | green | Community | [PNG](utility_level.png) | `EMOJIS["utility_level"]` |
| utility_stats | cyan | Community | [PNG](utility_stats.png) | `EMOJIS["utility_stats"]` |
| utility_leaderboard | gold | Community | [PNG](utility_leaderboard.png) | `EMOJIS["utility_leaderboard"]` |
| utility_crown | gold | Community | [PNG](utility_crown.png) | `EMOJIS["utility_crown"]` |
| utility_birthday | pink | Community | [PNG](utility_birthday.png) | `EMOJIS["utility_birthday"]` |
| utility_event | purple | Community | [PNG](utility_event.png) | `EMOJIS["utility_event"]` |
| utility_welcome | green | Community | [PNG](utility_welcome.png) | `EMOJIS["utility_welcome"]` |
| utility_goodbye | orange | Community | [PNG](utility_goodbye.png) | `EMOJIS["utility_goodbye"]` |
| utility_announcement | blue | Community | [PNG](utility_announcement.png) | `EMOJIS["utility_announcement"]` |
| utility_gaming | indigo | Community | [PNG](utility_gaming.png) | `EMOJIS["utility_gaming"]` |
| utility_microphone | cyan | Music | [PNG](utility_microphone.png) | `EMOJIS["utility_microphone"]` |
| utility_muted | red | Music | [PNG](utility_muted.png) | `EMOJIS["utility_muted"]` |
| utility_volume | blue | Music | [PNG](utility_volume.png) | `EMOJIS["utility_volume"]` |
| utility_silent | gray | Music | [PNG](utility_silent.png) | `EMOJIS["utility_silent"]` |
| utility_shuffle | purple | Music | [PNG](utility_shuffle.png) | `EMOJIS["utility_shuffle"]` |
| utility_repeat | green | Music | [PNG](utility_repeat.png) | `EMOJIS["utility_repeat"]` |
| utility_repeat_one | pink | Music | [PNG](utility_repeat_one.png) | `EMOJIS["utility_repeat_one"]` |
| utility_next_track | blue | Music | [PNG](utility_next_track.png) | `EMOJIS["utility_next_track"]` |
| utility_previous_track | blue | Music | [PNG](utility_previous_track.png) | `EMOJIS["utility_previous_track"]` |
| utility_playlist | indigo | Music | [PNG](utility_playlist.png) | `EMOJIS["utility_playlist"]` |
| utility_arrow_up | green | UI | [PNG](utility_arrow_up.png) | `EMOJIS["utility_arrow_up"]` |
| utility_arrow_down | orange | UI | [PNG](utility_arrow_down.png) | `EMOJIS["utility_arrow_down"]` |
| utility_arrow_left | blue | UI | [PNG](utility_arrow_left.png) | `EMOJIS["utility_arrow_left"]` |
| utility_arrow_right | blue | UI | [PNG](utility_arrow_right.png) | `EMOJIS["utility_arrow_right"]` |
| utility_add | green | UI | [PNG](utility_add.png) | `EMOJIS["utility_add"]` |
| utility_delete | red | UI | [PNG](utility_delete.png) | `EMOJIS["utility_delete"]` |
| utility_edit | gold | UI | [PNG](utility_edit.png) | `EMOJIS["utility_edit"]` |
| utility_save | green | UI | [PNG](utility_save.png) | `EMOJIS["utility_save"]` |
| utility_refresh | cyan | UI | [PNG](utility_refresh.png) | `EMOJIS["utility_refresh"]` |
| utility_search | purple | UI | [PNG](utility_search.png) | `EMOJIS["utility_search"]` |
| utility_download | blue | UI | [PNG](utility_download.png) | `EMOJIS["utility_download"]` |
| utility_upload | indigo | UI | [PNG](utility_upload.png) | `EMOJIS["utility_upload"]` |
| utility_copy | gray | UI | [PNG](utility_copy.png) | `EMOJIS["utility_copy"]` |
| utility_link | cyan | UI | [PNG](utility_link.png) | `EMOJIS["utility_link"]` |
| utility_pin | pink | UI | [PNG](utility_pin.png) | `EMOJIS["utility_pin"]` |
| utility_home | blue | UI | [PNG](utility_home.png) | `EMOJIS["utility_home"]` |
| utility_bot | indigo | UI | [PNG](utility_bot.png) | `EMOJIS["utility_bot"]` |
| utility_cloud | gray | UI | [PNG](utility_cloud.png) | `EMOJIS["utility_cloud"]` |
| utility_tools | orange | UI | [PNG](utility_tools.png) | `EMOJIS["utility_tools"]` |
| utility_sparkles | purple | UI | [PNG](utility_sparkles.png) | `EMOJIS["utility_sparkles"]` |
