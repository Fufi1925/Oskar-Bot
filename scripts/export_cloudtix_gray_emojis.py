"""Export neutral vector symbols for original CloudTIX bot emoji constants.

Production uses committed PNG/GIF files; Chromium is only an export dependency.
The colorful utility tiles are not regenerated here.
"""
import ast
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from PIL import Image
from playwright.sync_api import sync_playwright

from export_cloudtix_emojis import SPECS as BASE_SPECS, VERSION, BASE
from publish_cloudtix_dashboard_emojis import publish

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "bot/assets/emojis/cloudtix"
OUT = ASSETS / "bot-gray"
# Supplement the base feature glyphs with all original badge, status and fun names.
EXTRA_ALIASES = {
    "boost": "BOOST BOOSTS NITRO_BOOST",
    "verification": "CERTIFIED_MODERATOR",
    "heart": "EARLY_SUPPORTER HEARTS",
    "support": "HANDSHAKE MINGLE",
    "role": "HEADMOD MANAGER U_ADMIN STAFF",
    "premium": "PARTNER_BADGE",
    "star": "SYSTEM STAR_UNICODE",
    "game": "MAX__A",
    "ban": "SWORD",
    "warning": "_37496ALERT WARNING_UNICODE",
    "cross": "ERROR_UNICODE BLOCK CHECK FAIL NOT_OK CROSS_MARK",
    "checkmark": "CHECKMARK OK",
    "lockdown": "LOCK_UNICODE",
    "note": "NOTE",
    "transcript": "PAPER REDRULESBOOK",
    "search": "universitybot_SEARCH universitybot_CODE universitybot_COMMAND",
    "bot": "universitybotSYS",
    "link": "universitybotLINKS",
    "members": "ZHUMAN",
}
# key, Lucide glyph, category, fallback, original aliases
EXTRA_SPECS = [
    ("bug_hunter", "bug", "Badges", "🪲", "BUG_HUNTER BUG_HUNTER_LVL2"),
    ("developer", "code-xml", "Badges", "💻", "CODEBASE CODED ACTIVE_DEVELOPER Developer EARLY_VERIFIED_BOT_DEV"),
    ("hypesquad", "badge", "Badges", "🎖️", "HYPESQUAD_BRILLIANCE HYPESQUAD_BALANCE HYPESQUAD_BRAVERY HYPESQUAD_EVENTS"),
    ("browser", "globe", "UI", "🌐", "ICON_BROWSER universitybot_GLOBAL"),
    ("owner", "crown", "Badges", "👑", "universitybot_OWNER"),
    ("mention", "at-sign", "UI", "@", "MENTION MENTION_ALT1"),
    ("new", "badge-plus", "UI", "🆕", "NEW"),
    ("pc", "monitor", "UI", "🖥️", "PC"),
    ("mobile", "smartphone", "UI", "📱", "MOBILE"),
    ("connection", "wifi", "UI", "📶", "WIFI UPTIME universitybotCONNECTION"),
    ("ai", "brain-circuit", "UI", "🤖", "ZAI"),
    ("module", "blocks", "UI", "⚙️", "ZMODULE"),
    ("seed", "sprout", "Community", "🌱", "SEED"),
    ("thunder", "zap", "Community", "⚡", "THUNDER"),
    ("circle", "circle", "UI", "⚪", "ZCIRCLE ZCIRCLE_ALT1 RED_BUTTON REDDOT"),
    ("online", "circle-dot", "Status", "●", "ONLINE"),
    ("offline", "circle-dashed", "Status", "○", "OFFLINE"),
    ("idle", "moon", "Status", "◐", "IDLE"),
    ("dnd", "circle-minus", "Status", "⛔", "DND"),
    ("cast", "cast", "Music", "📡", "CAST"),
    ("cute", "smile", "Community", "🙂", "CUTE_CUTE_CUTE BLOBPART LAUGH1 LAUGH2 LAUGH3 UPSIDE_DOWN TONGUE_OUT"),
    ("panda", "paw-print", "Community", "🐼", "HAPPY_PANDA"),
    ("dance", "music", "Community", "🎵", "HEERIYE SG_RD"),
    ("sticker", "sticker", "Community", "🖼️", "EMOTE GIFD GIFN"),
    ("racecar", "car", "Community", "🏎️", "RACECAR64"),
    ("tea", "cup-soda", "Community", "🧋", "BUBBLE_TEA"),
    ("cherries", "cherry", "Community", "🍒", "CHERRIES"),
    ("cookie", "cookie", "Community", "🍪", "COOKIE"),
    ("cursor", "mouse-pointer-2", "UI", "🖱️", "CURSOR"),
    ("dizzy", "annoyed", "Community", "😵", "DIZZY"),
    ("coffee", "coffee", "Community", "☕", "JAVA_COFFEE"),
    ("money", "banknote", "Community", "💸", "MONEY"),
    ("moon", "moon", "Community", "🌙", "MOON"),
    ("peach", "apple", "Community", "🍑", "PEACH"),
    ("rock", "mountain", "Community", "🪨", "ROCK"),
    ("scissors", "scissors", "Community", "✂️", "SCISSORS"),
    ("shocked", "circle-alert", "Community", "😳", "SHOCKED"),
    ("target", "target", "Community", "🎯", "TARGET"),
]


def specs():
    result = []
    for key, vector, category, fallback, aliases in BASE_SPECS:
        result.append((key, vector, category, fallback,
                       " ".join(dict.fromkeys((aliases + " " + EXTRA_ALIASES.get(key, "")).split()))))
    return result + EXTRA_SPECS


def source(vector):
    bundled = OUT / "sources" / f"{vector}.svg"
    if bundled.exists():
        return vector, bundled.read_bytes()
    local = ASSETS / "sources" / f"{vector}.svg"
    if local.exists():
        return vector, local.read_bytes()
    try:
        with urlopen(f"{BASE}/icons/{vector}.svg", timeout=30) as response:
            data = response.read()
    except Exception as error:
        raise RuntimeError(f"Cannot download Lucide {VERSION} glyph: {vector}") from error
    bundled.write_bytes(data)
    return vector, data


def artwork(vector, shade):
    root = ET.fromstring(vector)
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    geometry = "".join(ET.tostring(child, encoding="unicode") for child in root)
    top, bottom = {"gray": ("#d4d4d4", "#8c8c8c"),
                   "yellow": ("#ffe08a", "#e7a62b"),
                   "red": ("#ff9292", "#e35050")}[shade]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="ink" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="24">
      <stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
    <linearGradient id="background" x1="0" y1="0" x2=".7" y2="1">
      <stop stop-color="#464646"/><stop offset="1" stop-color="#2d2d2d"/>
    </linearGradient>
  </defs>
  <rect x="5" y="5" width="118" height="118" rx="36" fill="url(#background)"/>
  <rect x="6" y="6" width="116" height="116" rx="35" fill="none" stroke="#666666" stroke-opacity=".3"/>
  <g id="rotation">
    <g id="icon" transform="translate(30 30) scale(2.8333333)" fill="none" stroke="url(#ink)"
       stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">{geometry}</g>
  </g>
</svg>'''


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sources").mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "LICENSE.lucide.txt", OUT / "LICENSE.lucide.txt")
    definitions = specs()
    aliases = {name for *_, names in definitions for name in names.split()}
    # Fail the export rather than quietly leaving an original constant unstyled.
    original = ast.parse((ROOT / "bot/utils/emoji.py").read_text(encoding="utf-8"))
    original_names = {node.targets[0].id for node in original.body
                      if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                      and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
                      and node.lineno < next(n.lineno for n in original.body
                                            if isinstance(n, ast.ImportFrom)
                                            and n.module == "utils.application_emojis")}
    if original_names - aliases:
        raise ValueError(f"Unmapped original emojis: {sorted(original_names - aliases)}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        vectors = dict(pool.map(source, sorted({entry[1] for entry in definitions})))
    entries = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=shutil.which("chromium"), args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 128, "height": 128})
        for label, vector, category, fallback, names in definitions:
            shade = "yellow" if label in {"warning", "warn", "anti_nuke", "report"} else "red" if label in {"cross", "reject", "ticket_close", "lockdown", "dnd"} else "gray"
            svg = artwork(vectors[vector], shade)
            (OUT / "sources" / f"{vector}.svg").write_bytes(vectors[vector])
            key = f"gray_{label}"
            target = OUT / f"{key}.{'gif' if label == 'loading' else 'png'}"
            page.set_content('<style>body{margin:0;background:transparent}svg{display:block}</style>' + svg)
            if label == "loading":
                with tempfile.TemporaryDirectory(prefix="cloudtix-gray-") as directory:
                    frames = []
                    for frame in range(16):
                        page.locator("#rotation").evaluate("(group, angle) => group.setAttribute('transform', `rotate(${angle} 64 64)`)", frame * 22.5)
                        path = Path(directory) / f"{frame:02d}.png"
                        page.screenshot(path=str(path), omit_background=True)
                        frames.append(str(path))
                    subprocess.run(["convert", "-delay", "6", "-dispose", "Background", *frames,
                                    "-alpha", "on", "-channel", "A", "-threshold", "50%", "+channel",
                                    "-loop", "0", str(target)], check=True)
            else:
                page.locator("svg").screenshot(path=str(target), omit_background=True)
            data = target.read_bytes()
            with Image.open(target) as image:
                if image.size != (128, 128) or image.convert("RGBA").getchannel("A").getextrema() != (0, 255):
                    raise ValueError(f"Invalid export: {key}")
            if len(data) > 256 * 1024:
                raise ValueError(f"Discord file size exceeded: {key}")
            digest = hashlib.sha256(data).hexdigest()
            entries.append({"key": key, "name": f"ct_{key}_{digest[:6]}", "category": category,
                            "file": f"bot-gray/{target.name}", "animated": label == "loading",
                            "width": 128, "height": 128, "bytes": len(data), "sha256": digest,
                            "fallback": fallback, "constants": names.split(), "dashboard_visible": True,
                            "provider": "CloudTIX Gray", "color": shade, "background": "gray",
                            "replaces": label if label in {item[0] for item in BASE_SPECS} else None,
                            "source_url": f"{BASE}/icons/{vector}.svg"})
        browser.close()
    manifest = {"schema_version": 1, "brand": "CloudTIX", "provider": "CloudTIX Gray",
                "license_file": "LICENSE.lucide.txt", "emojis": entries}
    (OUT / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    publish()
    readme = f'''# Graue CloudTIX Bot-Emojis

{len(entries)} Symbole auf abgerundeten grauen Kacheln für die ursprünglichen
Bot-Konstanten: silbergrauer Verlauf, gelbe Warnungen und rote Fehler/Sperren.
Außerhalb der Kacheln bleibt der Hintergrund transparent.
128 × 128 Pixel, maximal 256 KB. Der Ladeindikator bleibt animiert.
Lucide {VERSION}; vollständige Lizenz in [LICENSE.lucide.txt](LICENSE.lucide.txt).

Das Set wird beim Bot-Start automatisch als Application Emojis hochgeladen
und zuletzt auf die zentralen Bot-Konstanten angewendet. Auch Badge-Mappings,
Kompatibilitätsnamen und Kategorien verwenden diese Werte. Im Dashboard stehen
ausschließlich diese grauen Symbole. Alte IDs werden nicht gelöscht.

```python
from utils.emoji import TICKET, WARNING, ERROR, EMOJIS
await ctx.send(f"{{TICKET}} Dein Ticket")
await ctx.send(f"{{WARNING}} Bitte beachten")
# Direkter Zugriff auf das graue Bot-Symbol:
await ctx.send(EMOJIS["gray_ticket"])
# Das farbige Utility-Symbol bleibt separat nutzbar:
await ctx.send(EMOJIS["utility_ticket"])
```

Ohne verfügbare Discord-ID greift der Unicode-Fallback. Export:
`python scripts/export_cloudtix_gray_emojis.py`.

| Name | Farbe | Vorschau | Bot-Konstanten |
| --- | --- | --- | --- |
'''
    for entry in entries:
        readme += f"| {entry['key']} | {entry['color']} | [Bild]({Path(entry['file']).name}) | {', '.join('`' + n + '`' for n in entry['constants'])} |\n"
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Exported {len(entries)} neutral/accent bot icons, covering {len(original_names)} original constants; largest: {max(e['bytes'] for e in entries)} bytes.")


if __name__ == "__main__":
    main()
