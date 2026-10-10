# CloudTIX Application Emojis

35 weiße Lucide-Symbole, 128 × 128 Pixel, transparent. Alle Dateien sind deutlich
unter Discords 256-KB-Grenze; `loading.gif` hat 16 Frames und läuft in einer Schleife.
Quelle: Lucide **0.468.0**, mit vollständiger ISC-/MIT-Lizenz in
[LICENSE.lucide.txt](LICENSE.lucide.txt). Die unveränderten SVG-Quellen stehen in `sources/`.

## Sofort im Bot verwenden

```python
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

## Exporte reproduzieren

`scripts/export_cloudtix_emojis.py` lädt die angegebene Lucide-Version herunter,
exportiert die unveränderten Vektoren mit weißer CSS-Farbe auf transparenten
Hintergrund und schreibt PNGs, das GIF und beide Manifest-Kopien. Benötigt werden
nur dafür Playwright/Chromium, Pillow und ImageMagick; der Produktions-Bot braucht
keine zusätzliche Abhängigkeit. Änderungen an Assets erzeugen neue Hash-Namen.
