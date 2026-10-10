"""Create Discord utility tiles from SVG geometry, then export transparent PNGs.

The tile artwork is defined here as vectors; Lucide supplies licensed glyphs.
Generated visual concepts are not raster-edited or used as oversized uploads.
"""
import hashlib
import json
from pathlib import Path
import shutil
from xml.etree import ElementTree as ET

from PIL import Image
from playwright.sync_api import sync_playwright
from publish_cloudtix_dashboard_emojis import publish

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "bot/assets/emojis/cloudtix"
OUT = ASSETS / "discord-utility"
COLORS = {
    "green": ("#69ff09", "#16db00"),
    "purple": ("#ae26ff", "#7600e8"),
    "red": ("#ff5a77", "#e41940"),
    "gold": ("#ffdf48", "#f5a800"),
    "blue": ("#28c0ff", "#1670ed"),
    "cyan": ("#28f7df", "#00b1c9"),
    "pink": ("#ff5cce", "#dc1686"),
    "orange": ("#ffac47", "#f26316"),
    "indigo": ("#9770ff", "#5540df"),
    "gray": ("#8391ad", "#46516c"),
}
# key, Lucide geometry, color, category, fallback, native bot aliases
SPECS = [
    ("verified", "check", "green", "Security", "✅", "TICK TICK_ALT ZTICK SUCCESS ENABLE VERIFICATION ZSAFE CHECKMARK CHECK OK"),
    ("supporter", "heart", "purple", "Community", "💜", "ZDIL HEART_EM HEART3 REDHEART"),
    ("error", "x", "red", "UI", "❌", "CROSS CROSS_ALT ML_CROSS ZCROSS ERROR DENIED DISABLE CROSS_MARK FAIL NOT_OK"),
    ("warning", "triangle-alert", "gold", "UI", "⚠️", "WARNING WARNING_ALT ZWARNING ICONS_WARNING ICONS_WARNING_ALT1"),
    ("info", "info", "blue", "UI", "ℹ️", "INFO"),
    ("shield", "shield-check", "cyan", "Security", "🛡️", "SHIELD AUTOMOD"),
    ("ticket", "ticket", "blue", "Support", "🎫", "TICKET"),
    ("premium", "gem", "purple", "Community", "💎", "PREMIUM"),
    ("staff", "badge-check", "indigo", "Security", "🛡️", "HEADMOD U_ADMIN"),
    ("boost", "rocket", "pink", "Community", "🚀", "ZROCKET"),
    ("gift", "gift", "pink", "Community", "🎁", "GIVEAWAY ZTADA TADAA CELEBRATE"),
    ("trophy", "trophy", "gold", "Community", "🏆", "RANK"),
    ("star", "star", "gold", "Community", "⭐", "STAR STAR_ALT1 STAR_ALT2"),
    ("lock", "lock-keyhole", "orange", "Security", "🔒", "LOCK"),
    ("unlock", "lock-keyhole-open", "green", "Security", "🔓", "UNLOCK"),
    ("music", "headphones", "blue", "Music", "🎧", "MUSIC ICONS_MUSIC MUSIC_ALT1"),
    ("play", "play", "green", "Music", "▶️", "ZPLAY"),
    ("pause", "pause", "gold", "Music", "⏸️", "ICONS_PAUSE ZMUSICPAUSE ZPAUSE"),
    ("stop", "square", "red", "Music", "⏹️", "MUSICSTOP_ICONS STOP_BUTTON"),
    ("settings", "settings", "gray", "UI", "⚙️", "ZSETTINGS"),
    ("members", "users", "cyan", "Community", "👥", "ZPEOPLE HUMAN ZHUMAN"),
    ("ping", "bell", "pink", "UI", "🔔", "NOTIFICATION"),
    ("chat", "messages-square", "cyan", "Support", "💬", "MESSAGE"),
    ("clock", "clock", "orange", "UI", "🕒", "TIME CLOCK"),
    ("anti_nuke", "shield-alert", "red", "Security", "🛡️", ""),
    ("ban", "gavel", "red", "Security", "🔨", ""),
    ("jail", "brick-wall", "orange", "Security", "⛓️", ""),
    ("protection", "shield-plus", "green", "Security", "🛡️", ""),
    ("blocked", "shield-x", "red", "Security", "⛔", ""),
    ("unprotected", "shield-off", "gray", "Security", "⚠️", ""),
    ("identity", "fingerprint", "indigo", "Security", "🪪", ""),
    ("key", "key-round", "gold", "Security", "🔑", ""),
    ("permissions", "key-square", "purple", "Security", "🔐", ""),
    ("hidden", "eye-off", "gray", "Security", "🙈", ""),
    ("ticket_open", "ticket-plus", "green", "Support", "🎫", ""),
    ("ticket_resolved", "ticket-check", "cyan", "Support", "✅", ""),
    ("ticket_close", "ticket-x", "red", "Support", "❌", ""),
    ("application", "notebook-pen", "indigo", "Support", "📝", ""),
    ("transcript", "scroll-text", "gray", "Support", "📜", ""),
    ("support", "life-buoy", "orange", "Support", "🛟", ""),
    ("inbox", "inbox", "blue", "Support", "📥", ""),
    ("mail", "mail", "pink", "Support", "✉️", ""),
    ("help", "circle-help", "purple", "Support", "❓", ""),
    ("feedback", "message-square-heart", "pink", "Support", "💌", ""),
    ("level", "chart-no-axes-column-increasing", "green", "Community", "📈", ""),
    ("stats", "chart-pie", "cyan", "Community", "📊", ""),
    ("leaderboard", "medal", "gold", "Community", "🏅", ""),
    ("crown", "crown", "gold", "Community", "👑", ""),
    ("birthday", "cake", "pink", "Community", "🎂", ""),
    ("event", "calendar-days", "purple", "Community", "📅", ""),
    ("welcome", "user-round-plus", "green", "Community", "👋", ""),
    ("goodbye", "user-round-minus", "orange", "Community", "👋", ""),
    ("announcement", "megaphone", "blue", "Community", "📣", ""),
    ("gaming", "gamepad-2", "indigo", "Community", "🎮", ""),
    ("microphone", "mic", "cyan", "Music", "🎤", ""),
    ("muted", "mic-off", "red", "Music", "🔇", ""),
    ("volume", "volume-2", "blue", "Music", "🔊", ""),
    ("silent", "volume-x", "gray", "Music", "🔇", ""),
    ("shuffle", "shuffle", "purple", "Music", "🔀", ""),
    ("repeat", "repeat", "green", "Music", "🔁", ""),
    ("repeat_one", "repeat-1", "pink", "Music", "🔂", ""),
    ("next_track", "skip-forward", "blue", "Music", "⏭️", ""),
    ("previous_track", "skip-back", "blue", "Music", "⏮️", ""),
    ("playlist", "list-music", "indigo", "Music", "🎶", ""),
    ("arrow_up", "arrow-up", "green", "UI", "⬆️", ""),
    ("arrow_down", "arrow-down", "orange", "UI", "⬇️", ""),
    ("arrow_left", "arrow-left", "blue", "UI", "⬅️", ""),
    ("arrow_right", "arrow-right", "blue", "UI", "➡️", ""),
    ("add", "plus", "green", "UI", "➕", ""),
    ("delete", "trash-2", "red", "UI", "🗑️", ""),
    ("edit", "pencil", "gold", "UI", "✏️", ""),
    ("save", "save", "green", "UI", "💾", ""),
    ("refresh", "rotate-cw", "cyan", "UI", "🔄", ""),
    ("search", "search", "purple", "UI", "🔍", ""),
    ("download", "download", "blue", "UI", "📥", ""),
    ("upload", "upload", "indigo", "UI", "📤", ""),
    ("copy", "copy", "gray", "UI", "📋", ""),
    ("link", "link", "cyan", "UI", "🔗", ""),
    ("pin", "pin", "pink", "UI", "📌", ""),
    ("home", "house", "blue", "UI", "🏠", ""),
    ("bot", "bot", "indigo", "UI", "🤖", ""),
    ("cloud", "cloud", "gray", "UI", "☁️", ""),
    ("tools", "wrench", "orange", "UI", "🔧", ""),
    ("sparkles", "sparkles", "purple", "UI", "✨", ""),
]


def svg_tile(vector, color):
    source = ET.parse(ASSETS / "sources" / f"{vector}.svg").getroot()
    # Keep the glyph readable at Discord size; highlights live on the tile.
    for child in source.iter():
        child.tag = child.tag.split("}")[-1]
    glyph = "".join(ET.tostring(child, encoding="unicode") for child in source)
    top, bottom = COLORS[color]
    fill = "url(#symbol)" if vector in {"heart", "star", "play", "square"} else "none"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="tile" x1="0" y1="0" x2=".7" y2="1">
      <stop stop-color="{top}"/><stop offset=".45" stop-color="{bottom}"/>
      <stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
    <radialGradient id="light" cx=".25" cy=".05" r=".9">
      <stop stop-color="white" stop-opacity=".4"/><stop offset=".6" stop-color="white" stop-opacity=".08"/>
      <stop offset="1" stop-color="white" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="shade" x1="0" y1="0" x2="0" y2="1">
      <stop offset=".4" stop-opacity="0"/><stop offset="1" stop-opacity=".3"/>
    </linearGradient>
    <linearGradient id="gloss" x1="0" y1="0" x2=".2" y2="1">
      <stop stop-color="white" stop-opacity=".6"/><stop offset="1" stop-color="white" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="rim" x1="0" y1="0" x2=".7" y2="1">
      <stop stop-color="white" stop-opacity=".65"/><stop offset=".5" stop-color="white" stop-opacity=".1"/>
      <stop offset="1" stop-color="white" stop-opacity=".25"/>
    </linearGradient>
    <linearGradient id="symbol" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="24">
      <stop stop-color="white"/><stop offset=".6" stop-color="#ffffff"/>
      <stop offset="1" stop-color="#e5eaff"/>
    </linearGradient>
    <filter id="glow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur in="SourceGraphic" stdDeviation="1.5" result="bloom"/>
      <feMerge><feMergeNode in="bloom"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="tileClip"><rect x="5" y="5" width="118" height="118" rx="36"/></clipPath>
  </defs>
  <g clip-path="url(#tileClip)">
    <rect x="5" y="5" width="118" height="118" rx="36" fill="url(#tile)"/>
    <rect x="5" y="5" width="118" height="118" rx="36" fill="url(#light)"/>
    <rect x="5" y="5" width="118" height="118" rx="36" fill="url(#shade)"/>
    <path d="M13 42C13 21 25 12 44 12H86C99 12 107 17 112 26C81 19 43 29 16 48Z" fill="url(#gloss)"/>
    <rect x="9" y="9" width="110" height="110" rx="32" fill="none" stroke="url(#rim)" stroke-width="1.5"/>
    <g transform="translate(30 32) scale(2.8333333)" fill="{fill}" stroke="url(#symbol)" stroke-width="2.8"
       stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)">{glyph}</g>
    <path d="M105 20Q105 27 111 27Q105 27 105 34Q105 27 99 27Q105 27 105 20Z" fill="white" opacity=".9"/>
  </g>
</svg>'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sources").mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "LICENSE.lucide.txt", OUT / "LICENSE.lucide.txt")
    entries = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 128, "height": 128})
        for label, vector, color, category, fallback, aliases in SPECS:
            key = f"utility_{label}"
            svg = svg_tile(vector, color)
            (OUT / "sources" / f"{key}.svg").write_text(svg, encoding="utf-8")
            target = OUT / f"{key}.png"
            page.set_content('<style>body{margin:0;background:transparent}svg{display:block}</style>' + svg)
            page.locator("svg").screenshot(path=str(target), omit_background=True)
            data = target.read_bytes()
            with Image.open(target) as image:
                if image.size != (128, 128) or image.convert("RGBA").getchannel("A").getextrema() != (0, 255):
                    raise ValueError(f"Invalid utility emoji export: {key}")
            if len(data) > 256 * 1024:
                raise ValueError(f"Discord size limit exceeded: {key}")
            digest = hashlib.sha256(data).hexdigest()
            entries.append({
                "key": key, "name": f"ct_{key}_{digest[:6]}", "category": category,
                "file": f"discord-utility/{target.name}", "animated": False,
                "width": 128, "height": 128, "bytes": len(data), "sha256": digest,
                "fallback": fallback, "constants": aliases.split(), "dashboard_visible": True,
                "provider": "CloudTIX Utility", "glyph_provider": "Lucide 0.468.0",
                "color": color, "style": "shiny",
                "source_url": f"https://raw.githubusercontent.com/lucide-icons/lucide/0.468.0/icons/{vector}.svg",
            })
        browser.close()
    manifest = {
        "schema_version": 1, "brand": "CloudTIX", "provider": "CloudTIX Utility",
        "license_file": "LICENSE.lucide.txt", "emojis": entries,
    }
    manifest_text = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    (OUT / "emojis.json").write_text(manifest_text, encoding="utf-8")
    publish()
    readme = f'''# CloudTIX Utility Emojis

{len(entries)} neue Utility-Emojis im Stil farbiger Discord-Badges: stark gerundete
Kacheln, kräftige Farben, glänzende Lichtreflexe, dezenter Glow und große weiße
Symbole. Transparent,
128 × 128 Pixel und unter Discords 256-KB-Grenze. Eigene Vektorkacheln mit
Lucide-Glyphen; die Lizenz steht in [LICENSE.lucide.txt](LICENSE.lucide.txt).

Für Bot-Nachrichten in Discord, automatisch beim Start als Application Emojis
hochgeladen. Die Dashboard-Auswahl bietet dieses farbige Set und die grauen Kacheln.
Die Kacheln werden über `utility_*` ausdrücklich gewählt. Die ursprünglichen
Bot-Konstanten verwenden das separate graue Set mit Hinweisfarben.

```python
from utils.emoji import EMOJIS, CT_UTILITY_VERIFIED, CT_UTILITY_SUPPORTER

await ctx.send(f"{{CT_UTILITY_VERIFIED}} Verifiziert!")
await ctx.send(f"{{CT_UTILITY_SUPPORTER}} Danke für deinen Support!")
await ctx.send(f"{{EMOJIS['utility_premium']}} Premium ist aktiv.")
```

Die echten Discord-Codes entstehen beim Upload. Ohne verfügbare ID wird ein
passendes Unicode-Symbol verwendet. Vorhandene Application Emojis werden nicht
gelöscht. Vektorquellen stehen unter `sources/`, regenerierbar mit
`python scripts/export_cloudtix_utility_emojis.py`.

| Name | Farbe | Kategorie | Vorschau | Bot-Code |
| --- | --- | --- | --- | --- |
'''
    for entry in entries:
        readme += f"| {entry['key']} | {entry['color']} | {entry['category']} | [PNG]({Path(entry['file']).name}) | `EMOJIS[\"{entry['key']}\"]` |\n"
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Exported {len(entries)} transparent 128×128 utility tiles; largest: {max(e['bytes'] for e in entries)} bytes. Bot and dashboard.")


if __name__ == "__main__":
    main()
