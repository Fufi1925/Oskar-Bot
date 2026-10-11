"""Export filled, glowing reference-style CloudTIX emoji tiles.

Production uses committed PNG/GIF files; Chromium is only an export dependency.
Exports both the gray and colorful versions. The older utility tiles are
not regenerated here.
"""
import ast
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image
from playwright.sync_api import sync_playwright

from export_cloudtix_emojis import SPECS as BASE_SPECS
from publish_cloudtix_dashboard_emojis import publish
from cloudtix_emoji_catalog import NEW_SPECS, LABELS as CATALOG_LABELS, KEYWORDS, MARKS
from cloudtix_solid_artwork import artwork, source as filled_source, glyph_url, install_license

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
    return filled_source(vector, ASSETS)


def main(style="gray", only=None):
    global OUT
    OUT = ASSETS / f"bot-{style}"
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "sources").mkdir(exist_ok=True)
    shutil.copyfile(ASSETS / "LICENSE.lucide.txt", OUT / "LICENSE.lucide.txt")
    shutil.copyfile(install_license(ASSETS), OUT / "LICENSE.fontawesome.txt")
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
            svg = artwork(vectors[vector], shade, style, category, label, MARKS, POSITIVE)
            edited = OUT / "sources/edited" / f"{label}.png"
            (OUT / "sources" / f"filled_{vector}.svg").write_bytes(vectors[vector])
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
                    page.locator("body > svg").screenshot(path=str(target), omit_background=True)
                    # Generated artwork edits are bundled at their final Discord size.
                    if edited.exists():
                        encoded = base64.b64encode(edited.read_bytes()).decode("ascii")
                        page.set_content('<style>body{margin:0;background:transparent}</style>'
                            '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128">'
                            '<defs><clipPath id="tile"><rect x="4" y="4" width="120" height="120" rx="36"/></clipPath></defs>'
                            f'<image width="128" height="128" href="data:image/png;base64,{encoded}" clip-path="url(#tile)"/></svg>')
                        page.locator("body > svg").screenshot(path=str(target), omit_background=True)
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
                            "glyph_provider": "Font Awesome Free 6.7.2", "glyph_license_file": "LICENSE.fontawesome.txt",
                            "visual_style": "filled-glow", "source_url": glyph_url(vector)})
            if edited.exists():
                entries[-1]["artwork"] = "Generated reference-style motif"
        browser.close()
    manifest = {"schema_version": 1, "brand": "CloudTIX", "provider": "CloudTIX Gray" if style == "gray" else "CloudTIX Vivid",
                "license_file": "LICENSE.fontawesome.txt", "license_files": ["LICENSE.fontawesome.txt", "LICENSE.lucide.txt"], "emojis": entries}
    (OUT / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    publish()
    readme = f'''# CloudTIX Bot-Emojis: {"Grau" if style == "gray" else "Farbe"}

{len(entries)} Symbole auf abgerundeten {"grauen" if style == "gray" else "farbigen"} Kacheln.
Enthält alle ursprünglichen Bot-Symbole sowie Moderation, Server, Tickets,
Regelwerk, Medien, Wirtschaft und Statusmeldungen. Deutsche Namen und Suchbegriffe
stehen im Manifest. Verwandte Aktionen werden durch kleine Statuszeichen unterschieden.
Außerhalb der Kacheln bleibt der Hintergrund transparent.
128 × 128 Pixel, maximal 256 KB. Der Ladeindikator bleibt animiert.
Ausgefüllte Motive: Font Awesome Free 6.7.2 (CC BY 4.0),
[Lizenz](LICENSE.fontawesome.txt). Statuszeichen und ältere Quellen:
[Lucide-Lizenz](LICENSE.lucide.txt). Leuchtende Kacheln im Stil der Referenzbilder.

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
