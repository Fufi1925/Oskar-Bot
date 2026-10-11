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
from cloudtix_emoji_catalog import NEW_SPECS, LABELS as CATALOG_LABELS, KEYWORDS, MARKS

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
LABELS = {**CATALOG_LABELS, **LABELS}

PALETTES = {
    "Security": ("#438de8", "#21487a"),
    "Moderation": ("#6988e8", "#354987"),
    "Support": ("#20acc7", "#116579"),
    "Community": ("#a570e6", "#5b378c"),
    "Music": ("#dc67a9", "#86305f"),
    "Badges": ("#e5b84c", "#926819"),
    "Status": ("#4aad92", "#235e50"),
    "Server": ("#5b9bdc", "#2e5684"),
    "Regelwerk": ("#8e83e8", "#4f458f"),
    "Economy": ("#e7b94a", "#8b651c"),
    "Media": ("#bd73dc", "#6b3884"),
    "UI": ("#6b9bdf", "#355583"),
}
NEGATIVE = {"cross", "reject", "ticket_close", "lockdown", "dnd", "ban", "kick",
            "softban", "tempban", "member_banned", "rules_violation", "outage"}
CAUTION = {"warning", "warn", "anti_nuke", "report", "exclamation", "warn_list",
           "ticket_priority", "age_limit", "rules_pending", "maintenance", "idle"}
POSITIVE = {"checkmark", "accept", "verification", "online", "complete", "unban",
            "member_verified", "rules_accept", "agreement", "ticket_resolved",
            "welcome", "welcome_wave", "server_join", "unmute_member", "remove_timeout", "warn_remove"}


def specs():
    result = []
    for key, vector, category, fallback, aliases in BASE_SPECS:
        if key == "warn":
            vector = "shield-alert"
        result.append((key, vector, category, fallback,
                       " ".join(dict.fromkeys((aliases + " " + EXTRA_ALIASES.get(key, "")).split()))))
    return result + EXTRA_SPECS + NEW_SPECS


def source(vector):
    bundled = OUT / "sources" / f"{vector}.svg"
    if bundled.exists():
        return vector, bundled.read_bytes()
    local = ASSETS / "sources" / f"{vector}.svg"
    if local.exists():
        return vector, local.read_bytes()
    for sibling in ("bot-gray", "bot-color"):
        cached = ASSETS / sibling / "sources" / f"{vector}.svg"
        if cached.exists():
            return vector, cached.read_bytes()
    try:
        with urlopen(f"{BASE}/icons/{vector}.svg", timeout=30) as response:
            data = response.read()
    except Exception as error:
        raise RuntimeError(f"Cannot download Lucide {VERSION} glyph: {vector}") from error
    bundled.write_bytes(data)
    return vector, data


def artwork(vector, shade, style="gray", category="UI", label=""):
    root = ET.fromstring(vector)
    for node in root.iter():
        node.tag = node.tag.split("}")[-1]
    geometry = "".join(ET.tostring(child, encoding="unicode") for child in root)
    if label == "exclamation":
        geometry = '<path d="M12 3v11"/><circle cx="12" cy="20" r="1.2" fill="url(#ink)" stroke="none"/>'
    top, bottom = {"gray": ("#f5f5f5", "#b8b8b8"),
                   "yellow": ("#ffe08a", "#e7a62b"),
                   "red": ("#ff9292", "#e35050")}[shade]
    background_top, background_bottom = "#424448", "#25272b"
    if style == "color":
        background_top, background_bottom = PALETTES.get(category, PALETTES["UI"])
        if shade == "yellow":
            background_top, background_bottom = "#efb640", "#a56714"
        elif shade == "red":
            background_top, background_bottom = "#e86b76", "#972c3b"
        elif label in POSITIVE:
            background_top, background_bottom = "#4bbb87", "#23704e"
        elif label == "offline":
            background_top, background_bottom = "#79818b", "#424a55"
        top, bottom = "#ffffff", "#e2e8f0"
    mark = MARKS.get(label)
    marks = {
        "check": '<path d="m93 100 5 5 9-10"/>',
        "cross": '<path d="m94 96 11 11m0-11-11 11"/>',
        "minus": '<path d="M93 102h14"/>',
        "plus": '<path d="M93 102h14m-7-7v14"/>',
        "clock": '<circle cx="100" cy="102" r="7"/><path d="M100 97v5l4 2"/>',
        "refresh": '<path d="M94 103a6 6 0 1 0 2-6m-2-3v5h5"/>',
        "alert": '<path d="M100 95v8m0 5v.1"/>',
        "dot": '<circle cx="100" cy="102" r="3" fill="#ffffff"/>',
    }
    badge = (f'<circle cx="100" cy="102" r="15" fill="{background_bottom}" stroke="#ffffff" stroke-opacity=".25"/>'
             f'<g fill="none" stroke="#ffffff" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round">{marks[mark]}</g>') if mark else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128">
  <defs>
    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
      <stop stop-color="#ffffff" stop-opacity=".15"/><stop offset=".5" stop-color="#ffffff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="ink" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" y2="24">
      <stop stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/>
    </linearGradient>
    <linearGradient id="background" x1="0" y1="0" x2=".7" y2="1">
      <stop stop-color="{background_top}"/><stop offset="1" stop-color="{background_bottom}"/>
    </linearGradient>
  </defs>
  <rect x="5" y="5" width="118" height="118" rx="36" fill="url(#background)"/>
  <rect x="6" y="6" width="116" height="116" rx="35" fill="none" stroke="#ffffff" stroke-opacity=".18"/>
  <rect x="7" y="7" width="114" height="114" rx="34" fill="url(#sheen)"/>
  <g id="rotation">
    <g id="icon" transform="translate(26 26) scale(3.1666667)" fill="none" stroke="url(#ink)"
       stroke-width="2.15" stroke-linecap="round" stroke-linejoin="round">{geometry}</g>
  </g>
  {badge}
</svg>'''


def main(style="gray", only=None):
    global OUT
    OUT = ASSETS / f"bot-{style}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sources").mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "LICENSE.lucide.txt", OUT / "LICENSE.lucide.txt")
    definitions = specs()
    keys = [entry[0] for entry in definitions]
    if len(keys) != len(set(keys)):
        raise ValueError("Emoji definitions must have unique keys")
    if only and only - set(keys):
        raise ValueError(f"Unknown emoji keys: {sorted(only - set(keys))}")
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
            shade = "yellow" if label in CAUTION else "red" if label in NEGATIVE else "gray"
            svg = artwork(vectors[vector], shade, style, category, label)
            edited = OUT / "sources/edited" / f"{label}.png"
            (OUT / "sources" / f"{vector}.svg").write_bytes(vectors[vector])
            key = f"{style}_{label}" if style == "gray" else f"vivid_{label}"
            target = OUT / f"{key}.{'gif' if label == 'loading' else 'png'}"
            if only is None or label in only or not target.exists():
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
                    # Generated artwork edits are bundled at their final Discord size.
                    if edited.exists():
                        shutil.copyfile(edited, target)
            data = target.read_bytes()
            with Image.open(target) as image:
                if image.size != (128, 128) or image.convert("RGBA").getchannel("A").getextrema() != (0, 255):
                    raise ValueError(f"Invalid export: {key}")
            if len(data) > 256 * 1024:
                raise ValueError(f"Discord file size exceeded: {key}")
            digest = hashlib.sha256(data).hexdigest()
            # Discord allows at most 32 characters, including the content hash.
            entries.append({"key": key, "name": f"ct_{key[:22]}_{digest[:6]}", "category": category,
                            "file": f"bot-{style}/{target.name}", "animated": label == "loading",
                            "width": 128, "height": 128, "bytes": len(data), "sha256": digest,
                            "fallback": fallback, "constants": names.split(), "dashboard_visible": True,
                            "provider": "CloudTIX Gray" if style == "gray" else "CloudTIX Vivid",
                            "style": style, "label": LABELS.get(label, label.replace("_", " ")),
                            "keywords": list(dict.fromkeys([label, *KEYWORDS.get(label, [])])),
                            "color": shade if style == "gray" else background_color(category, shade), "background": style,
                            "replaces": label,
                            "source_url": f"{BASE}/icons/{vector}.svg"})
            if edited.exists():
                entries[-1]["artwork"] = "Generated edit of the Lucide symbol"
        browser.close()
    manifest = {"schema_version": 1, "brand": "CloudTIX", "provider": "CloudTIX Gray" if style == "gray" else "CloudTIX Vivid",
                "license_file": "LICENSE.lucide.txt", "emojis": entries}
    (OUT / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    publish()
    readme = f'''# CloudTIX Bot-Emojis: {"Grau" if style == "gray" else "Farbe"}

{len(entries)} Symbole auf abgerundeten {"grauen" if style == "gray" else "farbigen"} Kacheln.
Enthält alle ursprünglichen Bot-Symbole sowie Moderation, Server, Tickets,
Regelwerk, Medien, Wirtschaft und Statusmeldungen. Deutsche Namen und Suchbegriffe
stehen im Manifest. Verwandte Aktionen werden durch kleine Statuszeichen unterschieden.
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
    parser.add_argument("--only", help="Comma-separated keys to re-render; other existing assets are reused")
    args = parser.parse_args()
    for style in ("gray", "color") if args.style == "all" else (args.style,):
        main(style, set(args.only.split(",")) if args.only else None)
