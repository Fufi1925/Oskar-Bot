"""Export pinned Lucide vectors as transparent Discord application assets.

Developer tool only: needs Playwright/Chromium, Pillow and ImageMagick.
The bot uses the committed exports, so production needs none of these tools.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "bot/assets/emojis/cloudtix"
PUBLIC = ROOT / "dashboard/public/emojis/cloudtix"
VERSION = "0.468.0"
BASE = f"https://raw.githubusercontent.com/lucide-icons/lucide/{VERSION}"
# key, Lucide vector, category, Unicode fallback, existing bot constants
SPECS = [
    ("shield", "shield", "Security", "🛡️", "SHIELD"),
    ("anti_nuke", "shield-alert", "Security", "🛡️", "ANTI_NUKE"),
    ("automod", "shield-check", "Security", "🛡️", "AUTOMOD"),
    ("jail", "lock-keyhole", "Security", "🔒", "JAIL LOCK"),
    ("ticket", "ticket", "Support", "🎫", "TICKET"),
    ("verification", "badge-check", "Support", "✅", "VERIFICATION ZSAFE"),
    ("applications", "clipboard-list", "Support", "📋", "APPLICATIONS"),
    ("level", "chart-no-axes-column-increasing", "Community", "📈", "LEVEL_UP"),
    ("rank", "trophy", "Community", "🏆", "RANK"),
    ("giveaway", "gift", "Community", "🎉", "GIVEAWAY ZTADA TADAA CELEBRATE"),
    ("welcome", "hand", "Community", "👋", "WELCOME"),
    ("play", "play", "Music", "▶️", "ZPLAY"),
    ("pause", "pause", "Music", "⏸️", "ICONS_PAUSE ZMUSICPAUSE ZPAUSE"),
    ("headphones", "headphones", "Music", "🎧", "MUSIC ICONS_MUSIC MUSIC_ALT1"),
    ("volume", "volume-2", "Music", "🔊", "VOLUME ZUNMUTE"),
    ("checkmark", "check", "UI", "✅", "TICK TICK_ALT ZTICK SUCCESS ENABLE"),
    ("cross", "x", "UI", "❌", "CROSS CROSS_ALT ML_CROSS ZCROSS ERROR DENIED DISABLE"),
    ("arrow", "arrow-right", "UI", "➡️", "ZARROW ARROWRED ARROW_RIGHT"),
    ("info", "info", "UI", "ℹ️", "INFO"),
    ("warning", "triangle-alert", "UI", "⚠️", "WARNING WARNING_ALT ZWARNING ICONS_WARNING ICONS_WARNING_ALT1"),
    ("loading", "loader-circle", "UI", "⏳", "LOADING LOADING_ALT1 LOADINGRED"),
    ("back", "arrow-left", "UI", "⬅️", "ZBACK ARROW_LEFT"),
    ("stop", "square", "Music", "⏹️", "MUSICSTOP_ICONS STOP_BUTTON"),
    ("skip", "skip-forward", "Music", "⏭️", "NEXT NEXT_ALT1 SKIP FORWARD"),
    ("previous", "skip-back", "Music", "⏮️", "PREVIOUS"),
    ("settings", "settings", "UI", "⚙️", "ZSETTINGS"),
    ("members", "users", "Community", "👥", "ZPEOPLE HUMAN ZHUMAN"),
    ("message", "messages-square", "Support", "💬", "MESSAGE"),
    ("refresh", "rotate-cw", "UI", "🔄", "REFRESH ICONLOAD"),
    ("plus", "plus", "UI", "➕", "ZPLUS ICONS_PLUS"),
    ("delete", "trash-2", "UI", "🗑️", "DELETE DELETE_ALT1"),
    ("mute", "volume-x", "Music", "🔇", "MUTE ZMUTE"),
    ("unlock", "lock-keyhole-open", "Security", "🔓", "UNLOCK"),
    ("star", "star", "Community", "⭐", "STAR STAR_ALT1 STAR_ALT2"),
    ("cloud", "cloud", "UI", "☁️", "ZCLOUD"),
]


def download(relative):
    with urlopen(f"{BASE}/{relative}", timeout=30) as response:
        return response.read()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    source_dir = OUT / "sources"
    source_dir.mkdir(exist_ok=True)
    vectors = list(ThreadPoolExecutor(max_workers=8).map(
        download, [f"icons/{spec[1]}.svg" for spec in SPECS]
    ))
    license_text = download("LICENSE")
    (OUT / "LICENSE.lucide.txt").write_bytes(license_text)
    (PUBLIC / "LICENSE.lucide.txt").write_bytes(license_text)
    options = {"executable_path": shutil.which("chromium"), "args": ["--no-sandbox"]}
    proxy_url = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
    if proxy_url:
        proxy = urlsplit(proxy_url)
        options["proxy"] = {"server": f"{proxy.scheme}://{proxy.hostname}:{proxy.port or 80}"}
        if proxy.username:
            options["proxy"].update(username=unquote(proxy.username), password=unquote(proxy.password or ""))
    entries = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page(viewport={"width": 128, "height": 128})
        for (key, vector, category, fallback, constants), svg in zip(SPECS, vectors):
            (source_dir / f"{vector}.svg").write_bytes(svg)
            page.set_content('<style>body{margin:0;background:transparent;color:white}'
                             '#icon{width:128px;height:128px;display:grid;place-items:center}'
                             'svg{width:104px;height:104px}</style><div id="icon">'
                             + svg.decode() + '</div>')
            extension = "gif" if key == "loading" else "png"
            target = OUT / f"{key}.{extension}"
            if key == "loading":
                with tempfile.TemporaryDirectory(prefix="cloudtix-emoji-") as directory:
                    frames = []
                    for frame in range(16):
                        page.locator("svg").evaluate("(svg, angle) => svg.style.transform = `rotate(${angle}deg)`", frame * 22.5)
                        path = Path(directory) / f"frame-{frame:02d}.png"
                        page.locator("#icon").screenshot(path=str(path), omit_background=True)
                        frames.append(str(path))
                    subprocess.run(["convert", "-delay", "6", "-dispose", "Background", *frames,
                                    "-alpha", "on", "-channel", "A", "-threshold", "50%", "+channel",
                                    "-loop", "0", str(target)], check=True)
            else:
                page.locator("#icon").screenshot(path=str(target), omit_background=True)
            data = target.read_bytes()
            with Image.open(target) as image:
                assert image.size == (128, 128)
                assert image.convert("RGBA").getchannel("A").getextrema() == (0, 255)
                animated = bool(getattr(image, "is_animated", False))
                assert animated == (key == "loading")
            assert len(data) <= 256 * 1024
            digest = hashlib.sha256(data).hexdigest()
            entries.append({"key": key, "name": f"ct_{key}_{digest[:6]}", "category": category,
                            "file": target.name, "animated": animated, "width": 128, "height": 128,
                            "bytes": len(data), "sha256": digest, "fallback": fallback,
                            "constants": constants.split(), "source_url": f"{BASE}/icons/{vector}.svg",
                            "preview_url": f"https://cloudtix.up.railway.app/emojis/cloudtix/{target.name}"})
            shutil.copyfile(target, PUBLIC / target.name)
        browser.close()
    manifest = {"schema_version": 1, "brand": "CloudTIX", "provider": "Lucide",
                "provider_version": VERSION, "license_file": "LICENSE.lucide.txt", "emojis": entries}
    for directory in (OUT, PUBLIC):
        (directory / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"Exported {len(entries)} transparent 128×128 assets; largest: {max(e['bytes'] for e in entries)} bytes.")


if __name__ == "__main__":
    main()
