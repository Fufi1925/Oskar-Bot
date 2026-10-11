# CloudTIX · Grauer Hintergrund

80 einmalige Motive aus den hochgeladenen emoji.gg-Packs, einschließlich der
nachgereichten Mitglieder-, Welt-, WWW- und Bewertungsdateien.

- Graue, abgerundete Hintergründe; neutrale Symbolteile in Hellgrau.
- Vorhandene Farbfamilien bleiben erhalten: Grün, Gelb/Orange, Rot und Blau.
- Verbindung gut/mittel/schlecht, Stummschaltung, rote/gelbe Warnung und die
  fünf Bewertungsstufen bleiben unterschiedliche Motive.
- Doppelte Varianten für Mikrofon, Link, Krone, Mitglieder usw. sind einer
  gemeinsamen Datei zugeordnet. `design.json` dokumentiert jede Zuordnung.
- 128 × 128 Pixel, transparente Außenbereiche, unter Discords 256-KB-Grenze.
- Der gelieferte Discord-GIF hatte nur ein Bild und wird als PNG angeboten.

## Quellen und Gestaltung

`originals/` enthält die 107 verschiedenen ursprünglichen Dateinamen aus den
vom Nutzer gelieferten ZIPs. Die Originalmotive stammen aus emoji.gg-Packs;
die Bereitstellung hier macht keine Aussage über deren Lizenzbedingungen.
`sheets/` enthält die mit imagegen bearbeiteten Motive vor dem Dateiexport.
Die Bildbearbeitung erfolgte mit imagegen; der Export zerlegt die Bögen in
einzelne Dateien und erzeugt die Discord-Thumbnails.

```bash
python scripts/package_cloudtix_neutral_emojis.py
```

Der Export erzeugt Manifest, Hash-Namen, Dashboard-Vorschauen und Download-ZIP.
Er erfordert Pillow und ImageMagick; zur Bot-Laufzeit werden nur die fertigen
Dateien benötigt.

## Discord-Upload

Der Bot lädt die neue Sammlung beim Start mit seinem `TOKEN` hoch, sofern
`CLOUDTIX_EMOJI_SYNC=true` gesetzt ist (Standard). Frühere deaktivierte Packs
bleiben durch `retirement.json` gesperrt. Die neuen `neutral_*`-Schlüssel und
Hash-Namen sind davon unabhängig.

Für einen direkten Upload aus dieser Umgebung, nachdem `TOKEN` sicher in den
Umgebungseinstellungen hinterlegt wurde:

```bash
/workspace/.toolchains/oskar-bot/bot-venv/bin/python scripts/sync_cloudtix_application_emojis.py
```

Der Uploader prüft zuerst die zum Token gehörende Application und bestätigt
die fertigen Uploads mit einer neuen Discord-Abfrage. Zugangsdaten werden weder
als Argumente übergeben noch ausgegeben. IDs stammen ausschließlich von Discord;
bis zum Upload benutzen Bot-Nachrichten Unicode-Fallbacks und das Dashboard
zeigt die Vorschauen mit dem Hinweis auf den noch fehlenden Upload.
