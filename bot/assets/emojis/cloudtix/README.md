# CloudTIX Application Emojis

Das neueste Bot-Set enthält [84 kräftig farbige Utility-Emojis mit abgerundeten
Kacheln](discord-utility/README.md), darunter eine grüne Bestätigung und ein
violettes Unterstützer-Herz. Es liefert die aktuellen Standard-Bot-Symbole.

Zusätzlich gibt es [75 farbige Twemoji-Symbole für Bot-Nachrichten](discord-color/README.md).
Diese werden ebenfalls automatisch hochgeladen und stehen als `EMOJIS["color_gift"]`
bzw. `CT_COLOR_GIFT` im Bot bereit. Einige Standardkonstanten wie `TICK`, `ERROR`,
`WARNING` und `TICKET` nutzen dort die farbigen Varianten. Die Dashboard-Auswahl
enthält die 84 neuen Utility-Kacheln.

110 weiße Lucide-Symbole, 128 × 128 Pixel, transparent. Alle Dateien sind deutlich
unter Discords 256-KB-Grenze; `loading.gif` hat 16 Frames und läuft in einer Schleife.
Quelle: Lucide **0.468.0**, mit vollständiger ISC-/MIT-Lizenz in
[LICENSE.lucide.txt](LICENSE.lucide.txt). Die unveränderten SVG-Quellen stehen in `sources/`.

## Sofort im Bot verwenden

```python
import discord
from utils.emoji import EMOJIS, TICK, CROSS, TICKET, ZPLAY

await ctx.send(f"{EMOJIS['shield']} CloudTIX schützt deinen Server.")
button = discord.ui.Button(label="Ticket öffnen", emoji=EMOJIS["ticket"])
```

Der Bot lädt beim Start seinen bestehenden `TOKEN`, ruft seine Application-Emojis
ab und lädt fehlende Dateien direkt bei Discord hoch. Das passiert **vor** dem
Import der Cogs, damit bestehende `from utils.emoji import ...`-Imports bereits die
richtigen Werte bekommen. Bestehende zentrale Konstanten werden entsprechend den
`constants`-Listen in `emojis.json` automatisch auf das neue Set umgestellt.
Discord-Abzeichen und andere nicht zugeordnete Symbole bleiben eigene Emojis.
Im Dashboard werden ausschließlich die 84 Utility-Emojis angeboten.

Echte IDs werden atomar unter `$DATA_DIR/jsondb/cloudtix-emojis.json` gespeichert;
ohne `DATA_DIR` unter `bot/jsondb/cloudtix-emojis.json`. Der Cache ist nicht im Git.
Die Namen enthalten den Datei-Hash und werden beim nächsten Start wiederverwendet.
Es werden keine vorhandenen Emojis gelöscht. `CLOUDTIX_EMOJI_SYNC=true` ist der
Standard und unabhängig vom alten `EMOJI_SYNC`-Schalter. Mit `false` werden nur
bereits vorhandene IDs aufgelöst.

Bei fehlendem Token, Discord-Ausfall, fehlender Berechtigung oder erreichtem Limit
bleibt der Bot mit passenden Unicode-Symbolen benutzbar. Der Start wartet maximal
180 Sekunden auf die Synchronisierung und respektiert Discords `retry_after`.
Der nächste Start versucht fehlende Uploads erneut. Ein erfolgreicher Upload wird
sofort gespeichert; ein späterer Fehler verwirft diese IDs nicht.

## Echte Discord-Codes und Vorschauen

[Vorschauseite mit kopierbaren Discord-Codes](https://cloudtix.up.railway.app/emojis/cloudtix/index.html)

Der öffentliche Katalog `/api/cloudtix-emojis` liefert für jedes Emoji
`discord_code`: `<:ct_name_hash:echte_id>` bzw. beim GIF
`<a:ct_loading_hash:echte_id>`. Ohne erfolgreichen Upload ist das Feld **null**;
es werden keine IDs erfunden. Der Katalog enthält nur dieses öffentliche Set,
keine Guild-, Benutzer- oder Zugangsdaten.

| Name | Kategorie | Vorschau | Im Bot verwendbarer Code |
| --- | --- | --- | --- |
| shield | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/shield.png) | `EMOJIS["shield"]` |
| anti_nuke | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/anti_nuke.png) | `EMOJIS["anti_nuke"]` |
| automod | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/automod.png) | `EMOJIS["automod"]` |
| jail | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/jail.png) | `EMOJIS["jail"]` |
| ticket | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/ticket.png) | `EMOJIS["ticket"]` |
| verification | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/verification.png) | `EMOJIS["verification"]` |
| applications | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/applications.png) | `EMOJIS["applications"]` |
| level | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/level.png) | `EMOJIS["level"]` |
| rank | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/rank.png) | `EMOJIS["rank"]` |
| giveaway | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/giveaway.png) | `EMOJIS["giveaway"]` |
| welcome | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/welcome.png) | `EMOJIS["welcome"]` |
| play | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/play.png) | `EMOJIS["play"]` |
| pause | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/pause.png) | `EMOJIS["pause"]` |
| headphones | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/headphones.png) | `EMOJIS["headphones"]` |
| volume | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/volume.png) | `EMOJIS["volume"]` |
| checkmark | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/checkmark.png) | `EMOJIS["checkmark"]` |
| cross | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/cross.png) | `EMOJIS["cross"]` |
| arrow | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/arrow.png) | `EMOJIS["arrow"]` |
| info | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/info.png) | `EMOJIS["info"]` |
| warning | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/warning.png) | `EMOJIS["warning"]` |
| loading | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/loading.gif) | `EMOJIS["loading"]` |
| back | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/back.png) | `EMOJIS["back"]` |
| stop | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/stop.png) | `EMOJIS["stop"]` |
| skip | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/skip.png) | `EMOJIS["skip"]` |
| previous | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/previous.png) | `EMOJIS["previous"]` |
| settings | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/settings.png) | `EMOJIS["settings"]` |
| members | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/members.png) | `EMOJIS["members"]` |
| message | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/message.png) | `EMOJIS["message"]` |
| refresh | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/refresh.png) | `EMOJIS["refresh"]` |
| plus | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/plus.png) | `EMOJIS["plus"]` |
| delete | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/delete.png) | `EMOJIS["delete"]` |
| mute | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/mute.png) | `EMOJIS["mute"]` |
| unlock | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/unlock.png) | `EMOJIS["unlock"]` |
| star | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/star.png) | `EMOJIS["star"]` |
| cloud | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/cloud.png) | `EMOJIS["cloud"]` |
| ban | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/ban.png) | `EMOJIS["ban"]` |
| kick | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/kick.png) | `EMOJIS["kick"]` |
| timeout | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/timeout.png) | `EMOJIS["timeout"]` |
| warn | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/warn.png) | `EMOJIS["warn"]` |
| audit_log | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/audit_log.png) | `EMOJIS["audit_log"]` |
| permissions | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/permissions.png) | `EMOJIS["permissions"]` |
| firewall | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/firewall.png) | `EMOJIS["firewall"]` |
| quarantine | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/quarantine.png) | `EMOJIS["quarantine"]` |
| scan | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/scan.png) | `EMOJIS["scan"]` |
| fingerprint | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/fingerprint.png) | `EMOJIS["fingerprint"]` |
| password | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/password.png) | `EMOJIS["password"]` |
| incognito | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/incognito.png) | `EMOJIS["incognito"]` |
| lockdown | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/lockdown.png) | `EMOJIS["lockdown"]` |
| protection | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/protection.png) | `EMOJIS["protection"]` |
| report | Security | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/report.png) | `EMOJIS["report"]` |
| ticket_open | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/ticket_open.png) | `EMOJIS["ticket_open"]` |
| ticket_close | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/ticket_close.png) | `EMOJIS["ticket_close"]` |
| ticket_claim | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/ticket_claim.png) | `EMOJIS["ticket_claim"]` |
| transcript | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/transcript.png) | `EMOJIS["transcript"]` |
| support | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/support.png) | `EMOJIS["support"]` |
| faq | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/faq.png) | `EMOJIS["faq"]` |
| mail | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/mail.png) | `EMOJIS["mail"]` |
| inbox | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/inbox.png) | `EMOJIS["inbox"]` |
| form | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/form.png) | `EMOJIS["form"]` |
| accept | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/accept.png) | `EMOJIS["accept"]` |
| reject | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/reject.png) | `EMOJIS["reject"]` |
| feedback | Support | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/feedback.png) | `EMOJIS["feedback"]` |
| boost | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/boost.png) | `EMOJIS["boost"]` |
| birthday | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/birthday.png) | `EMOJIS["birthday"]` |
| event | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/event.png) | `EMOJIS["event"]` |
| announcement | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/announcement.png) | `EMOJIS["announcement"]` |
| invite | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/invite.png) | `EMOJIS["invite"]` |
| leave | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/leave.png) | `EMOJIS["leave"]` |
| role | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/role.png) | `EMOJIS["role"]` |
| leaderboard | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/leaderboard.png) | `EMOJIS["leaderboard"]` |
| xp | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/xp.png) | `EMOJIS["xp"]` |
| poll | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/poll.png) | `EMOJIS["poll"]` |
| counting | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/counting.png) | `EMOJIS["counting"]` |
| heart | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/heart.png) | `EMOJIS["heart"]` |
| game | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/game.png) | `EMOJIS["game"]` |
| crown | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/crown.png) | `EMOJIS["crown"]` |
| premium | Community | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/premium.png) | `EMOJIS["premium"]` |
| shuffle | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/shuffle.png) | `EMOJIS["shuffle"]` |
| repeat | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/repeat.png) | `EMOJIS["repeat"]` |
| repeat_one | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/repeat_one.png) | `EMOJIS["repeat_one"]` |
| queue | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/queue.png) | `EMOJIS["queue"]` |
| playlist | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/playlist.png) | `EMOJIS["playlist"]` |
| note | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/note.png) | `EMOJIS["note"]` |
| microphone | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/microphone.png) | `EMOJIS["microphone"]` |
| microphone_off | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/microphone_off.png) | `EMOJIS["microphone_off"]` |
| voice | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/voice.png) | `EMOJIS["voice"]` |
| equalizer | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/equalizer.png) | `EMOJIS["equalizer"]` |
| seek_forward | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/seek_forward.png) | `EMOJIS["seek_forward"]` |
| rewind | Music | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/rewind.png) | `EMOJIS["rewind"]` |
| home | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/home.png) | `EMOJIS["home"]` |
| dashboard | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/dashboard.png) | `EMOJIS["dashboard"]` |
| channel | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/channel.png) | `EMOJIS["channel"]` |
| search | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/search.png) | `EMOJIS["search"]` |
| edit | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/edit.png) | `EMOJIS["edit"]` |
| save | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/save.png) | `EMOJIS["save"]` |
| copy | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/copy.png) | `EMOJIS["copy"]` |
| download | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/download.png) | `EMOJIS["download"]` |
| upload | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/upload.png) | `EMOJIS["upload"]` |
| link | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/link.png) | `EMOJIS["link"]` |
| external_link | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/external_link.png) | `EMOJIS["external_link"]` |
| arrow_up | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/arrow_up.png) | `EMOJIS["arrow_up"]` |
| arrow_down | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/arrow_down.png) | `EMOJIS["arrow_down"]` |
| menu | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/menu.png) | `EMOJIS["menu"]` |
| close_panel | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/close_panel.png) | `EMOJIS["close_panel"]` |
| open_panel | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/open_panel.png) | `EMOJIS["open_panel"]` |
| notification | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/notification.png) | `EMOJIS["notification"]` |
| pin | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/pin.png) | `EMOJIS["pin"]` |
| clock | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/clock.png) | `EMOJIS["clock"]` |
| bot | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/bot.png) | `EMOJIS["bot"]` |
| tools | UI | [Bild](https://cloudtix.up.railway.app/emojis/cloudtix/tools.png) | `EMOJIS["tools"]` |

## Exporte reproduzieren

`scripts/export_cloudtix_emojis.py` lädt die angegebene Lucide-Version herunter,
exportiert die unveränderten Vektoren mit weißer CSS-Farbe auf transparenten
Hintergrund und schreibt PNGs, das GIF und beide Manifest-Kopien. Benötigt werden
nur dafür Playwright/Chromium, Pillow und ImageMagick; der Produktions-Bot braucht
keine zusätzliche Abhängigkeit. Änderungen an Assets erzeugen neue Hash-Namen.
