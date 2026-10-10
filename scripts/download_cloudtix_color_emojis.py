"""Download original, licensed Twemoji PNGs for CloudTIX's Discord messages.

No image conversion or dashboard export: these files are application emojis
for the bot. Pillow is used only to check the downloaded PNG metadata.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bot/assets/emojis/cloudtix/discord-color"
VERSION = "15.1.0"
BASE = f"https://raw.githubusercontent.com/jdecked/twemoji/v{VERSION}"
SPECS = [
    ("shield", "1f6e1", "Security"),
    ("lock", "1f512", "Security"),
    ("unlock", "1f513", "Security"),
    ("key", "1f511", "Security"),
    ("police", "1f46e", "Security"),
    ("alarm", "1f6a8", "Security"),
    ("stop_sign", "1f6d1", "Security"),
    ("hammer", "1f528", "Security"),
    ("chains", "26d3", "Security"),
    ("eye", "1f441", "Security"),
    ("ticket", "1f3ab", "Support"),
    ("mail", "2709", "Support"),
    ("inbox", "1f4e5", "Support"),
    ("outbox", "1f4e4", "Support"),
    ("memo", "1f4dd", "Support"),
    ("clipboard", "1f4cb", "Support"),
    ("chat", "1f4ac", "Support"),
    ("question", "2753", "Support"),
    ("lifebuoy", "1f6df", "Support"),
    ("phone", "1f4de", "Support"),
    ("gift", "1f381", "Community"),
    ("party", "1f389", "Community"),
    ("trophy", "1f3c6", "Community"),
    ("medal", "1f3c5", "Community"),
    ("crown", "1f451", "Community"),
    ("star", "2b50", "Community"),
    ("sparkles", "2728", "Community"),
    ("rocket", "1f680", "Community"),
    ("fire", "1f525", "Community"),
    ("heart", "2764", "Community"),
    ("gem", "1f48e", "Community"),
    ("cake", "1f382", "Community"),
    ("wave", "1f44b", "Community"),
    ("members", "1f465", "Community"),
    ("smile", "1f604", "Community"),
    ("laugh", "1f602", "Community"),
    ("love", "1f60d", "Community"),
    ("cool", "1f60e", "Community"),
    ("thinking", "1f914", "Community"),
    ("party_face", "1f973", "Community"),
    ("headphones", "1f3a7", "Music"),
    ("note", "1f3b5", "Music"),
    ("notes", "1f3b6", "Music"),
    ("microphone", "1f3a4", "Music"),
    ("speaker", "1f50a", "Music"),
    ("mute", "1f507", "Music"),
    ("radio", "1f4fb", "Music"),
    ("guitar", "1f3b8", "Music"),
    ("drums", "1f941", "Music"),
    ("piano", "1f3b9", "Music"),
    ("check", "2705", "UI"),
    ("cross", "274c", "UI"),
    ("warning", "26a0", "UI"),
    ("info", "2139", "UI"),
    ("success", "1f7e2", "UI"),
    ("error", "1f534", "UI"),
    ("pending", "1f7e1", "UI"),
    ("settings", "2699", "UI"),
    ("tools", "1f527", "UI"),
    ("calendar", "1f4c5", "UI"),
    ("clock", "1f552", "UI"),
    ("hourglass", "231b", "UI"),
    ("bell", "1f514", "UI"),
    ("pin", "1f4cc", "UI"),
    ("link", "1f517", "UI"),
    ("search", "1f50d", "UI"),
    ("save", "1f4be", "UI"),
    ("folder", "1f4c1", "UI"),
    ("document", "1f4c4", "UI"),
    ("cloud", "2601", "UI"),
    ("computer", "1f4bb", "UI"),
    ("mobile", "1f4f1", "UI"),
    ("up", "2b06", "UI"),
    ("down", "2b07", "UI"),
    ("refresh", "1f504", "UI"),
]

# Native bot replies/buttons use color; the dashboard keeps its white pack.
# Loaded after the white manifest, these aliases deliberately take precedence.
BOT_ALIASES = {
    "check": "TICK TICK_ALT ZTICK SUCCESS ENABLE",
    "cross": "CROSS CROSS_ALT ML_CROSS ZCROSS ERROR DENIED DISABLE",
    "warning": "WARNING WARNING_ALT ZWARNING ICONS_WARNING ICONS_WARNING_ALT1",
    "info": "INFO",
    "ticket": "TICKET",
    "party": "ZTADA TADAA CELEBRATE",
    "headphones": "MUSIC ICONS_MUSIC MUSIC_ALT1",
    "lock": "LOCK",
    "unlock": "UNLOCK",
    "crown": "KING KING_ALT1 BLACKCROWN",
    "star": "STAR STAR_ALT1 STAR_ALT2",
    "heart": "ZDIL HEART_EM HEART3 REDHEART",
    "rocket": "ZROCKET",
    "settings": "ZSETTINGS",
    "tools": "ZWRENCH",
}


def download(relative):
    with urlopen(f"{BASE}/{relative}", timeout=30) as response:
        return response.read()


def main():
    with ThreadPoolExecutor(max_workers=8) as pool:
        images = list(pool.map(download, [f"assets/72x72/{code}.png" for _, code, _ in SPECS]))
    license_text = download("LICENSE-GRAPHICS")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "LICENSE-GRAPHICS.txt").write_bytes(license_text)
    entries = []
    for (label, code, category), data in zip(SPECS, images):
        key = f"color_{label}"
        file = OUT / f"{key}.png"
        file.write_bytes(data)
        with Image.open(file) as image:
            if image.format != "PNG" or image.size != (72, 72):
                raise ValueError(f"Unexpected Twemoji PNG: {key}")
            if image.convert("RGBA").getchannel("A").getextrema() != (0, 255):
                raise ValueError(f"Missing transparency: {key}")
        if len(data) > 256 * 1024:
            raise ValueError(f"Discord size limit exceeded: {key}")
        digest = hashlib.sha256(data).hexdigest()
        fallback = chr(int(code, 16))
        if code in {"26d3", "2709", "2764", "26a0", "2139", "2699", "2601", "2b06", "2b07", "1f6e1", "1f441"}:
            fallback += "\ufe0f"
        entries.append({
            "key": key, "name": f"ct_{key}_{digest[:6]}", "category": category,
            "file": f"discord-color/{file.name}", "animated": False,
            "width": 72, "height": 72, "bytes": len(data), "sha256": digest,
            "fallback": fallback, "constants": BOT_ALIASES.get(label, "").split(), "dashboard_visible": False,
            "provider": "Twemoji", "provider_version": VERSION,
            "license": "CC-BY-4.0", "source_url": f"{BASE}/assets/72x72/{code}.png",
        })
    manifest = {
        "schema_version": 1, "brand": "CloudTIX", "provider": "Twemoji",
        "provider_version": VERSION, "license_file": "LICENSE-GRAPHICS.txt",
        "attribution": "Twemoji graphics by Twitter, Inc. and contributors; maintained by jdecked/twemoji. CC BY 4.0. Original, unmodified PNG files.",
        "emojis": entries,
    }
    (OUT / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    readme = f"""# CloudTIX – farbige Discord-Emojis

{len(entries)} zusätzliche Twemoji-Grafiken für **Bot-Nachrichten in Discord**.
Originale transparente PNGs, 72 × 72 Pixel, unverändert und unter 256 KB.
Diese Sammlung wird beim Bot-Start mit den Application Emojis synchronisiert.
Sie wird weder in die Dashboard-Auswahl noch in deren öffentliche Galerie übernommen.
Die bestehenden Bot-Konstanten für Erfolg, Fehler, Warnungen, Tickets, Musik und
einige Community-Symbole verwenden die farbigen Varianten automatisch. Die
zugeordneten Konstanten stehen je Eintrag unter `constants` in `emojis.json`.

```python
from utils.emoji import EMOJIS, CT_COLOR_GIFT

await ctx.send(f"{{EMOJIS['color_party']}} Herzlichen Glückwunsch!")
await ctx.send(f"{{CT_COLOR_GIFT}} Ein Geschenk für deine Community.")
```

Nach dem Upload enthalten die Werte echte `<:ct_color_name_hash:emoji_id>`-Codes.
Wenn Discord nicht erreichbar ist, gibt es für jeden Eintrag ein Unicode-Fallback.
Application Emojis gehören zum Bot und erscheinen nicht als Server-Emojis im
normalen Emoji-Menü von Mitgliedern.

## Lizenz und Quelle

Twemoji {VERSION}: Grafiken von Twitter, Inc. und weiteren Mitwirkenden;
gepflegt von jdecked/twemoji. **CC BY 4.0**, vollständiger Lizenztext in
[LICENSE-GRAPHICS.txt](LICENSE-GRAPHICS.txt). Die PNGs sind unverändert.
Die jeweilige Original-URL steht in `emojis.json`.

## Übersicht

| Name | Kategorie | Vorschau | Bot-Code |
| --- | --- | --- | --- |
"""
    for entry in entries:
        readme += f"| {entry['key']} | {entry['category']} | [PNG]({Path(entry['file']).name}) | `EMOJIS[\"{entry['key']}\"]` |\n"
    readme += "\nReproduzierbar mit `python scripts/download_cloudtix_color_emojis.py`.\n"
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Downloaded {len(entries)} original transparent Twemoji PNGs; largest: {max(e['bytes'] for e in entries)} bytes. No dashboard files exported.")


if __name__ == "__main__":
    main()
