"""Export pinned Lucide vectors as transparent Discord application assets.

Developer tool only: needs Playwright/Chromium, Pillow and ImageMagick.
The bot uses the committed exports, so production needs none of these tools.
"""
import hashlib
import json
import os
from pathlib import Path
import re
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
    # Security and moderation
    ("ban", "gavel", "Security", "🔨", "ZBAN universitybotHAMMER"),
    ("kick", "user-round-minus", "Security", "🚪", "KICK"),
    ("timeout", "timer", "Security", "⏱️", "TIMER TIMER_ALT1"),
    ("warn", "shield-x", "Security", "⚠️", "WARN"),
    ("audit_log", "scroll-text", "Security", "📜", "AUDIT_LOG"),
    ("permissions", "key-round", "Security", "🔑", "PERMISSIONS"),
    ("firewall", "brick-wall", "Security", "🧱", "FIREWALL"),
    ("quarantine", "shield-off", "Security", "🚫", "QUARANTINE"),
    ("scan", "scan-line", "Security", "🔍", "SCAN"),
    ("fingerprint", "fingerprint", "Security", "🔐", "FINGERPRINT"),
    ("password", "key-square", "Security", "🔑", "PASSWORD"),
    ("incognito", "eye-off", "Security", "🙈", "INCOGNITO"),
    ("lockdown", "door-closed", "Security", "🔒", "LOCKDOWN"),
    ("protection", "shield-plus", "Security", "🛡️", "PROTECTION"),
    ("report", "flag", "Security", "🚩", "REPORT"),
    # Ticket workflows and support
    ("ticket_open", "ticket-plus", "Support", "🎫", "TICKET_OPEN"),
    ("ticket_close", "ticket-x", "Support", "🎫", "TICKET_CLOSE"),
    ("ticket_claim", "ticket-check", "Support", "🎫", "TICKET_CLAIM"),
    ("transcript", "file-text", "Support", "📄", "TRANSCRIPT"),
    ("support", "life-buoy", "Support", "🛟", "SUPPORT"),
    ("faq", "circle-help", "Support", "❓", "FAQ"),
    ("mail", "mail", "Support", "✉️", "MAIL"),
    ("inbox", "inbox", "Support", "📥", "INBOX"),
    ("form", "notebook-pen", "Support", "📝", "FORM"),
    ("accept", "circle-check", "Support", "✅", "ACCEPT"),
    ("reject", "circle-x", "Support", "❌", "REJECT"),
    ("feedback", "message-square-heart", "Support", "💬", "FEEDBACK"),
    # Community, events and premium
    ("boost", "rocket", "Community", "🚀", "ZROCKET"),
    ("birthday", "cake", "Community", "🎂", "BIRTHDAY"),
    ("event", "calendar-days", "Community", "📅", "EVENT"),
    ("announcement", "megaphone", "Community", "📣", "ANNOUNCEMENT"),
    ("invite", "user-round-plus", "Community", "👋", "INVITE"),
    ("leave", "log-out", "Community", "🚪", "LEAVE"),
    ("role", "contact-round", "Community", "👤", "ROLE"),
    ("leaderboard", "medal", "Community", "🏅", "LEADERBOARD"),
    ("xp", "sparkles", "Community", "✨", "XP SPARKLE"),
    ("poll", "chart-pie", "Community", "📊", "POLL"),
    ("counting", "binary", "Community", "🔢", "ZCOUNTING"),
    ("heart", "heart", "Community", "❤️", "ZDIL HEART_EM HEART3 REDHEART"),
    ("game", "gamepad-2", "Community", "🎮", "GAMES GAME_CONTROLLER MINECRAFT"),
    ("crown", "crown", "Community", "👑", "KING KING_ALT1 BLACKCROWN"),
    ("premium", "gem", "Community", "💎", "PREMIUM"),
    # Music and voice controls
    ("shuffle", "shuffle", "Music", "🔀", "SHUFFLE"),
    ("repeat", "repeat", "Music", "🔁", "REPEAT"),
    ("repeat_one", "repeat-1", "Music", "🔂", "REPEAT_ONE"),
    ("queue", "list-music", "Music", "🎶", "QUEUE"),
    ("playlist", "library-big", "Music", "🎵", "PLAYLIST"),
    ("note", "music", "Music", "🎵", "MUSIC_NOTE"),
    ("microphone", "mic", "Music", "🎤", "MICROPHONE"),
    ("microphone_off", "mic-off", "Music", "🔇", "MICROPHONE_OFF"),
    ("voice", "radio", "Music", "📻", "VOICE"),
    ("equalizer", "audio-lines", "Music", "🎚️", "EQUALIZER"),
    ("seek_forward", "fast-forward", "Music", "⏩", "SEEK_FORWARD"),
    ("rewind", "rewind", "Music", "⏪", "REWIND REWIND_ALT1"),
    # General interface and navigation
    ("home", "house", "UI", "🏠", "HOME"),
    ("dashboard", "panels-top-left", "UI", "🖥️", "DASHBOARD"),
    ("channel", "hash", "UI", "#️⃣", "CHANNEL ICONS_CHANNEL"),
    ("search", "search", "UI", "🔍", "universitybot_SEARCH"),
    ("edit", "pencil", "UI", "✏️", "EDIT"),
    ("save", "save", "UI", "💾", "SAVE"),
    ("copy", "copy", "UI", "📋", "COPY"),
    ("download", "download", "UI", "📥", "DOWNLOAD"),
    ("upload", "upload", "UI", "📤", "UPLOAD"),
    ("link", "link", "UI", "🔗", "links universitybotLINKS"),
    ("external_link", "external-link", "UI", "↗️", "EXTERNAL_LINK"),
    ("arrow_up", "arrow-up", "UI", "⬆️", "ARROW_UP"),
    ("arrow_down", "arrow-down", "UI", "⬇️", "ARROW_DOWN"),
    ("menu", "menu", "UI", "☰", "MENU INDEX"),
    ("close_panel", "panel-left-close", "UI", "◀️", "CLOSE_PANEL"),
    ("open_panel", "panel-left-open", "UI", "▶️", "OPEN_PANEL"),
    ("notification", "bell", "UI", "🔔", "NOTIFICATION"),
    ("pin", "pin", "UI", "📌", "PIN RED_PIN"),
    ("clock", "clock", "UI", "🕒", "TIME CLOCK"),
    ("bot", "bot", "UI", "🤖", "ZBOT"),
    ("tools", "wrench", "UI", "🔧", "ZWRENCH TOOLS"),
]


def download(relative):
    with urlopen(f"{BASE}/{relative}", timeout=30) as response:
        return response.read()


def update_overview(entries):
    """Keep the documented names and preview links aligned with the pack."""
    readme_path = OUT / "README.md"
    if not readme_path.exists():
        return
    original = readme_path.read_text(encoding="utf-8")
    header, remainder = original.split("| Name | Kategorie | Vorschau |", 1)
    _, footer = remainder.split("\n## Exporte reproduzieren", 1)
    header = re.sub(r"(?m)^\d+ weiße Lucide-Symbole", f"{len(entries)} weiße Lucide-Symbole", header)
    table = ["| Name | Kategorie | Vorschau | Im Bot verwendbarer Code |",
             "| --- | --- | --- | --- |"]
    for entry in entries:
        table.append(f"| {entry['key']} | {entry['category']} | [Bild]({entry['preview_url']}) "
                     f"| `EMOJIS[\"{entry['key']}\"]` |")
    readme_path.write_text(header + "\n".join(table) + "\n\n## Exporte reproduzieren" + footer,
                           encoding="utf-8")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    PUBLIC.mkdir(parents=True, exist_ok=True)
    source_dir = OUT / "sources"
    source_dir.mkdir(exist_ok=True)
    previous_path = OUT / "emojis.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    previous_entries = {entry["key"]: entry for entry in previous.get("emojis", [])}

    def vector_source(spec):
        existing_source = source_dir / f"{spec[1]}.svg"
        if previous.get("provider_version") == VERSION and existing_source.exists():
            return existing_source.read_bytes()
        return download(f"icons/{spec[1]}.svg")

    with ThreadPoolExecutor(max_workers=8) as pool:
        vectors = list(pool.map(vector_source, SPECS))
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
            source_path = source_dir / f"{vector}.svg"
            previous_entry = previous_entries.get(key, {})
            extension = "gif" if key == "loading" else "png"
            target = OUT / f"{key}.{extension}"
            reusable = (
                previous_entry.get("source_url") == f"{BASE}/icons/{vector}.svg"
                and source_path.exists() and source_path.read_bytes() == svg
                and target.exists()
                and hashlib.sha256(target.read_bytes()).hexdigest() == previous_entry.get("sha256")
            )
            source_path.write_bytes(svg)
            page.set_content('<style>body{margin:0;background:transparent;color:white}'
                             '#icon{width:128px;height:128px;display:grid;place-items:center}'
                             'svg{width:104px;height:104px}</style><div id="icon">'
                             + svg.decode() + '</div>')
            if reusable:
                # Preserve published assets and their Discord names exactly.
                pass
            elif key == "loading":
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
                            "dashboard_visible": False,
                            "constants": constants.split(), "source_url": f"{BASE}/icons/{vector}.svg",
                            "preview_url": f"https://cloudtix.up.railway.app/emojis/cloudtix/{target.name}"})
            shutil.copyfile(target, PUBLIC / target.name)
        browser.close()
    manifest = {"schema_version": 1, "brand": "CloudTIX", "provider": "Lucide",
                "provider_version": VERSION, "license_file": "LICENSE.lucide.txt", "emojis": entries}
    (OUT / "emojis.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    update_overview(entries)
    print(f"Exported {len(entries)} transparent 128×128 assets; largest: {max(e['bytes'] for e in entries)} bytes.")


if __name__ == "__main__":
    main()
