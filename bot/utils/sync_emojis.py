# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 University Bot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Application Emoji Sync Utility
Reads all custom Discord emojis from utils/emoji.py, checks them against
the bot's application emojis, uploads any that are missing, and patches
emoji.py in-place with corrected IDs.

Controlled by EMOJI_SYNC in .env:
  EMOJI_SYNC="true"   → runs on every startup
  EMOJI_SYNC="false"  → skipped entirely

If emoji.py is patched (new uploads or ID fixes), the bot automatically
restarts so the fresh IDs are loaded into memory.

Call `run_sync(token)` once inside on_ready.
"""

import os
import re
import sys
import base64
import asyncio
import aiohttp
from colorama import Fore, Style, init

init(autoreset=True)

EMOJI_PY_PATH = os.path.join(os.path.dirname(__file__), "emoji.py")
ASSET_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "assets", "emojis"))

# Local application-emoji artwork. These files are uploaded directly to the
# bot application in the Developer Portal instead of being copied from an old
# Discord CDN emoji. An ID listed here is replaced once; after EmojiSync writes
# the new ID to emoji.py, normal name/ID matching takes over on later starts.
LOCAL_EMOJI_SOURCES = {
    "ArrowRed": os.path.join(ASSET_DIR, "ArrowRed.png"),
    "Disable": os.path.join(ASSET_DIR, "Disable.png"),
    "handshake": os.path.join(ASSET_DIR, "handshake.png"),
    "index": os.path.join(ASSET_DIR, "index.png"),
    "red_button": os.path.join(ASSET_DIR, "red_button.png"),
    "universitybot_time": os.path.join(ASSET_DIR, "universitybot_time.png"),
    "warning": os.path.join(ASSET_DIR, "warning.png"),
    "zmusic": os.path.join(ASSET_DIR, "zmusic.png"),
    "zpin": os.path.join(ASSET_DIR, "zpin.png"),
    "zseed": os.path.join(ASSET_DIR, "zseed.png"),
    "zumute": os.path.join(ASSET_DIR, "zumute.png"),
    "unmute": os.path.join(ASSET_DIR, "unmute.png"),
    "cast": os.path.join(ASSET_DIR, "cast.png"),
    "IMG_20261003_192525": os.path.join(ASSET_DIR, "IMG_20261003_192525.png"),
    "zmute": os.path.join(ASSET_DIR, "zmute.png"),
    "rokceet": os.path.join(ASSET_DIR, "rokceet.png"),
    "cloud": os.path.join(ASSET_DIR, "cloud.png"),
    "module": os.path.join(ASSET_DIR, "module.png"),
    "pause": os.path.join(ASSET_DIR, "pause.png"),
    "iconplus": os.path.join(ASSET_DIR, "iconplus.png"),
    "pauseee": os.path.join(ASSET_DIR, "pauseee.png"),
    "cutimer": os.path.join(ASSET_DIR, "cutimer.png"),
    "bothammer": os.path.join(ASSET_DIR, "bothammer.png"),
    "reench": os.path.join(ASSET_DIR, "reench.png"),
    "connection": os.path.join(ASSET_DIR, "connection.png"),
    "warningg": os.path.join(ASSET_DIR, "warningg.png"),
    "tadaaa": os.path.join(ASSET_DIR, "tadaaa.png"),
    "wifi": os.path.join(ASSET_DIR, "wifi.png"),
    "AI": os.path.join(ASSET_DIR, "AI.png"),
    "bothunder": os.path.join(ASSET_DIR, "bothunder.png"),
    "stur": os.path.join(ASSET_DIR, "stur.png"),
    "chat": os.path.join(ASSET_DIR, "chat.png"),
    "cirle": os.path.join(ASSET_DIR, "cirle.png"),
    "ban": os.path.join(ASSET_DIR, "ban.png"),
    "zuback": os.path.join(ASSET_DIR, "zuback.png"),
    "heart": os.path.join(ASSET_DIR, "heart.png"),
    "lupe": os.path.join(ASSET_DIR, "lupe.png"),
    "university": os.path.join(ASSET_DIR, "university.png"),
}
FORCE_REPLACE_IDS = {
    "ArrowRed": {"1530375308270899371"},
    "Disable": {"1530375483936608277"},
    "handshake": {"1530375521534214306"},
    "index": {"1530375391959580783"},
    "red_button": {"1530375507214991471"},
    "universitybot_time": {"1530375094893936800"},
    "warning": {"1530375219733201036"},
    "zmusic": {"1530375363090448404"},
    "zpin": {"1530375133791784964"},
    "zseed": {"1530375235981803573"},
    "zumute": {"1555998198202368021"},
    "unmute": {"1556002302870167603"},
    "cast": {"1555994588194410618"},
    "IMG_20261003_192525": {"1555994780071108758"},
    "zmute": {"1530375311043334145"},
    "rokceet": {"1556002064654540811"},
    "cloud": {"1556001221335187629"},
    "module": {"1556001529733840926"},
    "pause": {"1555997078025674863"},
    "iconplus": {"1555997209999450203"},
    "pauseee": {"1556001778988875906"},
    "cutimer": {"1556000324743991486"},
    "bothammer": {"1556003219858260008"},
    "reench": {"1556002535729406024"},
    "connection": {"1556003126736322613"},
    "warningg": {"1556002419383734302"},
    "tadaaa": {"1556002186964500510"},
    "wifi": {"1555999938331279451"},
    "AI": {"1556000515530293278"},
    "bothunder": {"1555999686605803590"},
    "stur": {"1555999376344883293"},
    "chat": {"1555997648891150368"},
    "cirle": {"1556001048068624494"},
    "ban": {"1556000901242822737"},
    "zuback": {"1555998730027536465"},
    "heart": {"1556001406996062258"},
    "lupe": {"1556002685407330486"},
    "university": {"1556002995852935209"},
}


def _log(level: str, color: str, symbol: str, msg: str) -> None:
    print(f"{color}{symbol} {level}:{Style.RESET_ALL} {msg}")

def info(msg):    _log("EmojiSync", Fore.CYAN,    "◈", msg)
def success(msg): _log("EmojiSync", Fore.GREEN,   "✔", msg)
def warning(msg): _log("EmojiSync", Fore.YELLOW,  "↻", msg)
def error(msg):   _log("EmojiSync", Fore.RED,     "✖", msg)
def system(msg):  _log("EmojiSync", Fore.MAGENTA, "★", msg)


def _restart() -> None:
    """Replace the current process with a fresh copy of itself."""
    system("Restarting bot to load updated emoji IDs...")
    # Flush stdout so the message is visible before the process is replaced
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def _fetch_emoji_image(session: aiohttp.ClientSession, emoji_id: str, animated: bool):
    """
    Download the source image for an emoji.

    The extension in the template is only a guess: an emoji written as
    `<a:name:id>` is not necessarily animated on Discord's side. Asking for
    the wrong one gets a 415, so try the likely extension first and then
    fall back to the others instead of giving up.

    Returns (bytes, mime) or (None, None).
    """
    order = ["gif", "png", "webp"] if animated else ["png", "webp", "gif"]
    mimes = {"gif": "image/gif", "png": "image/png", "webp": "image/webp"}

    for ext in order:
        url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
        try:
            async with session.get(url, allow_redirects=True) as r:
                if r.status == 200:
                    return await r.read(), mimes[ext]
        except Exception:
            continue
    return None, None


async def run_sync(token: str) -> None:
    """
    Async emoji sync. Pass the bot token directly.
    Respects the EMOJI_SYNC env var — set to "false" to disable.
    Triggers an automatic restart when emoji.py is patched.
    """
    # ── Toggle check ──────────────────────────────────────────────────────────
    enabled = os.getenv("EMOJI_SYNC", "true").strip().lower()
    if enabled != "true":
        info(f"Disabled via EMOJI_SYNC={enabled!r} — skipping.")
        return

    if not token:
        warning("No token provided — skipping EmojiSync.")
        return

    # ── Read emoji.py ─────────────────────────────────────────────────────────
    try:
        with open(EMOJI_PY_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as err:
        error(f"Could not read emoji.py ({err})")
        return

    matches = set(re.findall(r"<(a?):(\w+):(\d+)>", content))
    if not matches:
        info("No custom emojis found in emoji.py — nothing to sync.")
        return

    system(f"Starting Application Emoji Sync — {len(matches)} unique emojis found in emoji.py")

    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        # Fetch bot application ID
        async with session.get("https://discord.com/api/v10/users/@me") as r:
            if r.status != 200:
                error(f"Failed to fetch bot info [HTTP {r.status}]")
                return
            app_id = (await r.json()).get("id")

        # Fetch existing application emojis
        async with session.get(f"https://discord.com/api/v10/applications/{app_id}/emojis") as r:
            if r.status != 200:
                error(f"Failed to fetch application emojis [HTTP {r.status}]")
                return
            data = await r.json()
            app_emojis: list = data.get("items", []) if isinstance(data, dict) else data

        info(
            f"Found {Fore.YELLOW}{len(matches)}{Style.RESET_ALL} templates "
            f"{Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} "
            f"Application hosts {Fore.GREEN}{len(app_emojis)}{Style.RESET_ALL} emojis"
        )

        updated = False
        skipped = uploaded = fixed = failed = 0

        for animated_str, name, old_id in matches:
            animated = animated_str == "a"

            existing = (
                next((e for e in app_emojis if e["id"] == old_id), None)
                or next((e for e in app_emojis if e["name"] == name), None)
            )

            local_source = LOCAL_EMOJI_SOURCES.get(name)
            replace_existing = bool(
                existing
                and existing.get("id") == old_id
                and old_id in FORCE_REPLACE_IDS.get(name, set())
                and local_source
                and os.path.isfile(local_source)
            )

            if existing and not replace_existing:
                new_id = existing["id"]
                # The "a" prefix must match what Discord actually stores. Keeping
                # the template's own prefix leaves an animated emoji written as
                # <:name:id>, which Discord renders as plain text.
                new_prefix = "a" if existing.get("animated") else ""
                old_str = f"<{animated_str}:{name}:{old_id}>"
                new_str = f"<{new_prefix}:{existing['name']}:{new_id}>"
                if old_str != new_str:
                    content = content.replace(old_str, new_str)
                    updated = True
                    fixed += 1
                    warning(f"Auto-fixing: {name} {Fore.LIGHTBLACK_EX}-> {new_str}")
                else:
                    skipped += 1
                continue

            if replace_existing:
                info(f"Replacing: {name} {Fore.LIGHTBLACK_EX}(new local artwork)")
                async with session.delete(
                    f"https://discord.com/api/v10/applications/{app_id}/emojis/{existing['id']}"
                ) as delete_response:
                    if delete_response.status not in (200, 204):
                        error(
                            f"Could not replace {name}; deleting the old application emoji "
                            f"failed [HTTP {delete_response.status}]"
                        )
                        failed += 1
                        continue
                app_emojis.remove(existing)
            else:
                info(f"Uploading: {name} {Fore.LIGHTBLACK_EX}(not in application emojis)")

            if local_source and os.path.isfile(local_source):
                try:
                    with open(local_source, "rb") as image_file:
                        image_data = image_file.read()
                    extension = os.path.splitext(local_source)[1].lower()
                    mime = "image/gif" if extension == ".gif" else "image/png"
                except OSError as err:
                    error(f"Could not read local artwork for {name} ({err})")
                    failed += 1
                    continue
            else:
                image_data, mime = await _fetch_emoji_image(session, old_id, animated)

            if not image_data:
                error(
                    f"Could not load image for {name} [ID: {old_id}] — "
                    f"provide a local asset or point it at a live emoji in emoji.py"
                )
                failed += 1
                continue

            b64 = base64.b64encode(image_data).decode("utf-8")
            image_uri = f"data:{mime};base64,{b64}"

            async with session.post(
                f"https://discord.com/api/v10/applications/{app_id}/emojis",
                json={"name": name, "image": image_uri},
            ) as r2:
                if r2.status in (200, 201):
                    new_emoji = await r2.json()
                    new_id = new_emoji["id"]
                    old_str = f"<{animated_str}:{name}:{old_id}>"
                    # Use the flag Discord reports, not the one we guessed.
                    up_prefix = "a" if new_emoji.get("animated") else ""
                    new_str = f"<{up_prefix}:{new_emoji['name']}:{new_id}>"
                    content = content.replace(old_str, new_str)
                    app_emojis.append(new_emoji)
                    updated = True
                    uploaded += 1
                    success(f"Uploaded: {name} {Fore.LIGHTBLACK_EX}[saved as ID: {new_id}]")
                else:
                    resp_text = await r2.text()
                    error(f"Discord rejected {name} -> {resp_text}")
                    failed += 1

            # Small delay to respect Discord rate limits
            await asyncio.sleep(0.5)

    # ── Write patched emoji.py ────────────────────────────────────────────────
    if updated:
        try:
            with open(EMOJI_PY_PATH, "w", encoding="utf-8") as f:
                f.write(content)
            success("emoji.py patched in-place to reflect current API state.")
        except Exception as err:
            error(f"Could not write patched emoji.py ({err})")
            updated = False  # don't restart if we couldn't save

    # ── Summary ───────────────────────────────────────────────────────────────
    parts = []
    if skipped:  parts.append(f"{Fore.GREEN}{skipped} already matching{Style.RESET_ALL}")
    if fixed:    parts.append(f"{Fore.YELLOW}{fixed} ID mismatches fixed{Style.RESET_ALL}")
    if uploaded: parts.append(f"{Fore.CYAN}{uploaded} newly uploaded{Style.RESET_ALL}")
    if failed:   parts.append(f"{Fore.RED}{failed} failures{Style.RESET_ALL}")

    if parts:
        system("Sync complete: " + f" {Fore.LIGHTBLACK_EX}|{Style.RESET_ALL} ".join(parts))
    else:
        system("Sync complete: nothing to do.")

    # ── Auto-restart if emoji.py was changed ─────────────────────────────────
    if updated:
        _restart()
