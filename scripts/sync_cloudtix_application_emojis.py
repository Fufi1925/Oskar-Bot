"""Upload the active bundled pack using TOKEN, never a token CLI argument.

Run from the repository with the bot's Python environment. Real Discord IDs
and upload readiness are only reported after a fresh authenticated GET.
"""
import asyncio
import importlib.util
import logging
import os
from pathlib import Path
import sys
import time


async def main():
    token = os.getenv("TOKEN")
    if not token:
        print("Upload blocked: set TOKEN securely in the environment settings.")
        return 2
    source = Path(__file__).resolve().parents[1] / "bot/utils/application_emojis.py"
    spec = importlib.util.spec_from_file_location("cloudtix_application_emojis", source)
    emojis = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(emojis)
    os.environ["CLOUDTIX_EMOJI_SYNC"] = "true"
    await emojis.sync_from_token(token)
    app_id = os.getenv(emojis._VERIFIED_APP_ENV)
    if not app_id:
        print("Upload unconfirmed: Discord application identity unavailable.")
        return 1
    import aiohttp

    async with aiohttp.ClientSession(headers={"Authorization": f"Bot {token}"},
                                     timeout=aiohttp.ClientTimeout(total=20)) as session:
        remote = await emojis._request(session, "GET", f"/applications/{app_id}/emojis", time.monotonic() + 30)
    actual = {item["name"]: str(item["id"]) for item in remote["items"]}
    active = [entry for entry in emojis.catalog(app_id)["emojis"] if not entry["retired"]]
    cache = emojis._cache(app_id)
    ready = sum(actual.get(entry["name"]) == str(cache.get(entry["key"], {}).get("id", ""))
                for entry in active)
    print(f"Discord confirmed: {ready}/{len(active)} active emojis uploaded.")
    return 0 if ready == len(active) and active else 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        sys.exit(asyncio.run(main()))
    except Exception as error:
        # Do not print request headers, environment values or exception bodies.
        print(f"Discord upload interrupted ({type(error).__name__}); completion unconfirmed.")
        sys.exit(1)
