# CloudTIX – farbige Discord-Emojis

75 zusätzliche Twemoji-Grafiken für **Bot-Nachrichten in Discord**.
Originale transparente PNGs, 72 × 72 Pixel, unverändert und unter 256 KB.
Diese Sammlung wird beim Bot-Start mit den Application Emojis synchronisiert.
Sie wird weder in die Dashboard-Auswahl noch in deren öffentliche Galerie übernommen.
Die bestehenden Bot-Konstanten für Erfolg, Fehler, Warnungen, Tickets, Musik und
einige Community-Symbole verwenden die farbigen Varianten automatisch. Die
zugeordneten Konstanten stehen je Eintrag unter `constants` in `emojis.json`.

```python
from utils.emoji import EMOJIS, CT_COLOR_GIFT

await ctx.send(f"{EMOJIS['color_party']} Herzlichen Glückwunsch!")
await ctx.send(f"{CT_COLOR_GIFT} Ein Geschenk für deine Community.")
```

Nach dem Upload enthalten die Werte echte `<:ct_color_name_hash:emoji_id>`-Codes.
Wenn Discord nicht erreichbar ist, gibt es für jeden Eintrag ein Unicode-Fallback.
Application Emojis gehören zum Bot und erscheinen nicht als Server-Emojis im
normalen Emoji-Menü von Mitgliedern.

## Lizenz und Quelle

Twemoji 15.1.0: Grafiken von Twitter, Inc. und weiteren Mitwirkenden;
gepflegt von jdecked/twemoji. **CC BY 4.0**, vollständiger Lizenztext in
[LICENSE-GRAPHICS.txt](LICENSE-GRAPHICS.txt). Die PNGs sind unverändert.
Die jeweilige Original-URL steht in `emojis.json`.

## Übersicht

| Name | Kategorie | Vorschau | Bot-Code |
| --- | --- | --- | --- |
| color_shield | Security | [PNG](color_shield.png) | `EMOJIS["color_shield"]` |
| color_lock | Security | [PNG](color_lock.png) | `EMOJIS["color_lock"]` |
| color_unlock | Security | [PNG](color_unlock.png) | `EMOJIS["color_unlock"]` |
| color_key | Security | [PNG](color_key.png) | `EMOJIS["color_key"]` |
| color_police | Security | [PNG](color_police.png) | `EMOJIS["color_police"]` |
| color_alarm | Security | [PNG](color_alarm.png) | `EMOJIS["color_alarm"]` |
| color_stop_sign | Security | [PNG](color_stop_sign.png) | `EMOJIS["color_stop_sign"]` |
| color_hammer | Security | [PNG](color_hammer.png) | `EMOJIS["color_hammer"]` |
| color_chains | Security | [PNG](color_chains.png) | `EMOJIS["color_chains"]` |
| color_eye | Security | [PNG](color_eye.png) | `EMOJIS["color_eye"]` |
| color_ticket | Support | [PNG](color_ticket.png) | `EMOJIS["color_ticket"]` |
| color_mail | Support | [PNG](color_mail.png) | `EMOJIS["color_mail"]` |
| color_inbox | Support | [PNG](color_inbox.png) | `EMOJIS["color_inbox"]` |
| color_outbox | Support | [PNG](color_outbox.png) | `EMOJIS["color_outbox"]` |
| color_memo | Support | [PNG](color_memo.png) | `EMOJIS["color_memo"]` |
| color_clipboard | Support | [PNG](color_clipboard.png) | `EMOJIS["color_clipboard"]` |
| color_chat | Support | [PNG](color_chat.png) | `EMOJIS["color_chat"]` |
| color_question | Support | [PNG](color_question.png) | `EMOJIS["color_question"]` |
| color_lifebuoy | Support | [PNG](color_lifebuoy.png) | `EMOJIS["color_lifebuoy"]` |
| color_phone | Support | [PNG](color_phone.png) | `EMOJIS["color_phone"]` |
| color_gift | Community | [PNG](color_gift.png) | `EMOJIS["color_gift"]` |
| color_party | Community | [PNG](color_party.png) | `EMOJIS["color_party"]` |
| color_trophy | Community | [PNG](color_trophy.png) | `EMOJIS["color_trophy"]` |
| color_medal | Community | [PNG](color_medal.png) | `EMOJIS["color_medal"]` |
| color_crown | Community | [PNG](color_crown.png) | `EMOJIS["color_crown"]` |
| color_star | Community | [PNG](color_star.png) | `EMOJIS["color_star"]` |
| color_sparkles | Community | [PNG](color_sparkles.png) | `EMOJIS["color_sparkles"]` |
| color_rocket | Community | [PNG](color_rocket.png) | `EMOJIS["color_rocket"]` |
| color_fire | Community | [PNG](color_fire.png) | `EMOJIS["color_fire"]` |
| color_heart | Community | [PNG](color_heart.png) | `EMOJIS["color_heart"]` |
| color_gem | Community | [PNG](color_gem.png) | `EMOJIS["color_gem"]` |
| color_cake | Community | [PNG](color_cake.png) | `EMOJIS["color_cake"]` |
| color_wave | Community | [PNG](color_wave.png) | `EMOJIS["color_wave"]` |
| color_members | Community | [PNG](color_members.png) | `EMOJIS["color_members"]` |
| color_smile | Community | [PNG](color_smile.png) | `EMOJIS["color_smile"]` |
| color_laugh | Community | [PNG](color_laugh.png) | `EMOJIS["color_laugh"]` |
| color_love | Community | [PNG](color_love.png) | `EMOJIS["color_love"]` |
| color_cool | Community | [PNG](color_cool.png) | `EMOJIS["color_cool"]` |
| color_thinking | Community | [PNG](color_thinking.png) | `EMOJIS["color_thinking"]` |
| color_party_face | Community | [PNG](color_party_face.png) | `EMOJIS["color_party_face"]` |
| color_headphones | Music | [PNG](color_headphones.png) | `EMOJIS["color_headphones"]` |
| color_note | Music | [PNG](color_note.png) | `EMOJIS["color_note"]` |
| color_notes | Music | [PNG](color_notes.png) | `EMOJIS["color_notes"]` |
| color_microphone | Music | [PNG](color_microphone.png) | `EMOJIS["color_microphone"]` |
| color_speaker | Music | [PNG](color_speaker.png) | `EMOJIS["color_speaker"]` |
| color_mute | Music | [PNG](color_mute.png) | `EMOJIS["color_mute"]` |
| color_radio | Music | [PNG](color_radio.png) | `EMOJIS["color_radio"]` |
| color_guitar | Music | [PNG](color_guitar.png) | `EMOJIS["color_guitar"]` |
| color_drums | Music | [PNG](color_drums.png) | `EMOJIS["color_drums"]` |
| color_piano | Music | [PNG](color_piano.png) | `EMOJIS["color_piano"]` |
| color_check | UI | [PNG](color_check.png) | `EMOJIS["color_check"]` |
| color_cross | UI | [PNG](color_cross.png) | `EMOJIS["color_cross"]` |
| color_warning | UI | [PNG](color_warning.png) | `EMOJIS["color_warning"]` |
| color_info | UI | [PNG](color_info.png) | `EMOJIS["color_info"]` |
| color_success | UI | [PNG](color_success.png) | `EMOJIS["color_success"]` |
| color_error | UI | [PNG](color_error.png) | `EMOJIS["color_error"]` |
| color_pending | UI | [PNG](color_pending.png) | `EMOJIS["color_pending"]` |
| color_settings | UI | [PNG](color_settings.png) | `EMOJIS["color_settings"]` |
| color_tools | UI | [PNG](color_tools.png) | `EMOJIS["color_tools"]` |
| color_calendar | UI | [PNG](color_calendar.png) | `EMOJIS["color_calendar"]` |
| color_clock | UI | [PNG](color_clock.png) | `EMOJIS["color_clock"]` |
| color_hourglass | UI | [PNG](color_hourglass.png) | `EMOJIS["color_hourglass"]` |
| color_bell | UI | [PNG](color_bell.png) | `EMOJIS["color_bell"]` |
| color_pin | UI | [PNG](color_pin.png) | `EMOJIS["color_pin"]` |
| color_link | UI | [PNG](color_link.png) | `EMOJIS["color_link"]` |
| color_search | UI | [PNG](color_search.png) | `EMOJIS["color_search"]` |
| color_save | UI | [PNG](color_save.png) | `EMOJIS["color_save"]` |
| color_folder | UI | [PNG](color_folder.png) | `EMOJIS["color_folder"]` |
| color_document | UI | [PNG](color_document.png) | `EMOJIS["color_document"]` |
| color_cloud | UI | [PNG](color_cloud.png) | `EMOJIS["color_cloud"]` |
| color_computer | UI | [PNG](color_computer.png) | `EMOJIS["color_computer"]` |
| color_mobile | UI | [PNG](color_mobile.png) | `EMOJIS["color_mobile"]` |
| color_up | UI | [PNG](color_up.png) | `EMOJIS["color_up"]` |
| color_down | UI | [PNG](color_down.png) | `EMOJIS["color_down"]` |
| color_refresh | UI | [PNG](color_refresh.png) | `EMOJIS["color_refresh"]` |

Reproduzierbar mit `python scripts/download_cloudtix_color_emojis.py`.
