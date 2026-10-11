"""Export gray and colorful symbols for CloudTIX bot emoji constants.

Production uses committed PNG/GIF files; Chromium is only an export dependency.
Exports both the gray and colorful versions. The older utility tiles are
not regenerated here.
"""
import ast
import argparse
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
    "transcript": "PAPER",
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
    ("rules", "book-open", "Regelwerk", "📖", "RULES REGELWERK REDRULESBOOK"),
    ("guidelines", "list-checks", "Regelwerk", "📋", "GUIDELINES"),
    ("rules_accept", "book-check", "Regelwerk", "✅", "RULES_ACCEPT"),
    ("rules_faq", "circle-help", "Regelwerk", "❓", "RULES_FAQ"),
    ("privacy_policy", "shield-check", "Regelwerk", "🛡️", "PRIVACY_POLICY"),
    ("terms", "scroll-text", "Regelwerk", "📜", "TERMS"),
    ("changelog", "history", "UI", "📝", "CHANGELOG"),
    ("server_info", "info", "UI", "ℹ️", "SERVER_INFO"),
]

LABELS = {
    "rules": "Regelwerk", "guidelines": "Verhaltensregeln",
    "rules_accept": "Regeln akzeptieren", "rules_faq": "Fragen zum Regelwerk FAQ",
    "privacy_policy": "Datenschutz", "terms": "Nutzungsbedingungen",
    "changelog": "Änderungslog", "server_info": "Server-Info",
}


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


def artwork(vector, shade, style="gray", category="UI"):
    root = ET.fromstring(vector)
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    geometry = "".join(ET.tostring(child, encoding="unicode") for child in root)
    top, bottom = {"gray": ("#d4d4d4", "#8c8c8c"),
                   "yellow": ("#ffe08a", "#e7a62b"),
                   "red": ("#ff9292", "#e35050")}[shade]
    background_top, background_bottom = "#464646", "#2d2d2d"
    if style == "color":
        background_top, background_bottom = {
            "Security": ("#3b82f6", "#1e40af"),
            "Support": ("#22d3ee", "#0e7490"),
            "Community": ("#a855f7", "#6b21a8"),
            "Music": ("#f472b6", "#be185d"),
            "Badges": ("#fbbf24", "#b45309"),
            "Status": ("#34d399", "#047857"),
            "Regelwerk": ("#818cf8", "#4338ca"),
        }.get(category, ("#60a5fa", "#1d4ed8"))
        if shade == "yellow":
            background_top, background_bottom = "#fbbf24", "#b45309"
        elif shade == "red":
            background_top, background_bottom = "#fb7185", "#be123c"
        top, bottom = "#ffffff", "#e2e8f0"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
      <stop stop-color="#ffffff" stop-opacity=".2"/><stop offset=".65" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="ink" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="24">
      <stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
    <linearGradient id="background" x1="0" y1="0" x2=".7" y2="1">
      <stop stop-color="{background_top}"/><stop offset="1" stop-color="{background_bottom}"/>
    </linearGradient>
  </defs>
  <rect x="5" y="5" width="118" height="118" rx="36" fill="url(#background)"/>
  <rect x="6" y="6" width="116" height="116" rx="35" fill="none" stroke="#666666" stroke-opacity=".3"/>
  {('<rect x="7" y="7" width="114" height="114" rx="34" fill="url(#sheen)"/>') if style == 'color' else ''}
  <g id="rotation">
    <g id="icon" transform="translate(30 30) scale(2.8333333)" fill="none" stroke="url(#ink)"
       stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">{geometry}</g>
  </g>
</svg>'''


def main(style="gray"):
    global OUT
    OUT = ASSETS / f"bot-{style}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sources").mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "LICENSE.lucide.txt", OUT / "LICENSE.lucide.txt")
    definitions = specs()
    keys = [entry[0] for entry in definitions]
    if len(keys) != len(set(keys)):
        raise ValueError("Emoji definitions must have unique keys")
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
        edited = OUT / "sources/transcript-color.png"
        for label, vector, category, fallback, names in definitions:
            shade = "yellow" if label in {"warning", "warn", "anti_nuke", "report"} else "red" if label in {"cross", "reject", "ticket_close", "lockdown", "dnd"} else "gray"
            svg = artwork(vectors[vector], shade, style, category)
            (OUT / "sources" / f"{vector}.svg").write_bytes(vectors[vector])
            key = f"{style}_{label}" if style == "gray" else f"vivid_{label}"
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
                # The edited transcript is bundled at its final Discord size.
                if style == "color" and label == "transcript" and edited.exists():
                    shutil.copyfile(edited, target)
            data = target.read_bytes()
            with Image.open(target) as image:
                if image.size != (128, 128) or image.convert("RGBA").getchannel("A").getextrema() != (0, 255):
                    raise ValueError(f"Invalid export: {key}")
            if len(data) > 256 * 1024:
                raise ValueError(f"Discord file size exceeded: {key}")
            digest = hashlib.sha256(data).hexdigest()
            entries.append({"key": key, "name": f"ct_{key}_{digest[:6]}", "category": category,
                            "file": f"bot-{style}/{target.name}", "animated": label == "loading",
                            "width": 128, "height": 128, "bytes": len(data), "sha256": digest,
                            "fallback": fallback, "constants": names.split(), "dashboard_visible": True,
                            "provider": "CloudTIX Gray" if style == "gray" else "CloudTIX Vivid",
                            "style": style, "label": LABELS.get(label, label.replace("_", " ")),
                            "color": shade if style == "gray" else background_color(category, shade), "background": style,
                            "replaces": label,
                            "source_url": f"{BASE}/icons/{vector}.svg"})
            if style == "color" and label == "transcript" and edited.exists():
                entries[-1]["artwork"] = "Generated color edit of the Lucide transcript symbol"
        browser.close()
    manifest = {"schema_version": 1, "brand": "CloudTIX", "provider": "CloudTIX Gray" if style == "gray" else "CloudTIX Vivid",
                "license_file": "LICENSE.lucide.txt", "emojis": entries}
    (OUT / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    publish()
    readme = f'''# CloudTIX Bot-Emojis: {"Grau" if style == "gray" else "Farbe"}

{len(entries)} Symbole auf abgerundeten {"grauen" if style == "gray" else "farbigen"} Kacheln.
Enthält alle ursprünglichen Bot-Symbole sowie Regelwerk, Verhaltensregeln,
Regeln akzeptieren, FAQ, Datenschutz, Nutzungsbedingungen, Änderungslog und Server-Info.
Außerhalb der Kacheln bleibt der Hintergrund transparent.
128 × 128 Pixel, maximal 256 KB. Der Ladeindikator bleibt animiert.
Lucide {VERSION}; vollständige Lizenz in [LICENSE.lucide.txt](LICENSE.lucide.txt).

Beide Sets werden beim Bot-Start automatisch als Application Emojis hochgeladen.
Die zentralen Bot-Konstanten verwenden die farbige Variante. Im Dashboard kann
zwischen Farbe und Grau gewählt werden. Alte IDs werden nicht gelöscht.

```python
from utils.emoji import TICKET, WARNING, ERROR, EMOJIS
await ctx.send(f"{{TICKET}} Dein Ticket")
await ctx.send(f"{{WARNING}} Bitte beachten")
# Direkter Zugriff auf die graue Variante:
await ctx.send(EMOJIS["gray_ticket"])
# Direkter Zugriff auf die farbige Variante:
await ctx.send(EMOJIS["vivid_ticket"])
```

Ohne verfügbare Discord-ID greift der Unicode-Fallback. Export:
`python scripts/export_cloudtix_gray_emojis.py --style all`.

| Name | Farbe | Vorschau | Bot-Konstanten |
| --- | --- | --- | --- |
'''
    for entry in entries:
        readme += f"| {entry['key']} | {entry['color']} | [Bild]({Path(entry['file']).name}) | {', '.join('`' + n + '`' for n in entry['constants'])} |\n"
    (OUT / "README.md").write_text(readme, encoding="utf-8")
    print(f"Exported {len(entries)} {style} bot icons, covering {len(original_names)} original constants; largest: {max(e['bytes'] for e in entries)} bytes.")


def background_color(category, shade):
    return shade if shade != "gray" else category.lower()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--style", choices=("gray", "color", "all"), default="all")
    args = parser.parse_args()
    for style in ("gray", "color") if args.style == "all" else (args.style,):
        main(style)
