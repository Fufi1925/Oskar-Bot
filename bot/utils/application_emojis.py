"""CloudTIX's bundled application emojis, synchronized before cog imports.

Standalone-safe: do not import utils/core here. Discord remains the authority
for IDs and animated flags. Missing uploads always have a Unicode fallback.
"""
import asyncio
import base64
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import time

LOG = logging.getLogger("cloudtix.emojis")
BOT_DIR = Path(__file__).resolve().parents[1]
ASSETS = BOT_DIR / "assets/emojis/cloudtix"
MANIFEST = json.loads((ASSETS / "emojis.json").read_text(encoding="utf-8"))
# Later packs take precedence for native bot aliases. Only the utility pack
# is offered in the dashboard; other collections remain available to the bot.
for relative_manifest in ("discord-color/emojis.json", "discord-utility/emojis.json"):
    pack_path = ASSETS / relative_manifest
    if pack_path.exists():
        MANIFEST["emojis"].extend(json.loads(pack_path.read_text(encoding="utf-8"))["emojis"])
API = "https://discord.com/api/v10"
_VERIFIED_APP_ENV = "CLOUDTIX_VERIFIED_EMOJI_APPLICATION_ID"


def _cache_path():
    return Path(os.getenv("DATA_DIR") or BOT_DIR).expanduser() / "jsondb/cloudtix-emojis.json"


def _cache(application_id=None):
    # Explicit IDs are used by the bot API; imports use the ID verified at boot.
    app_id = str(application_id or os.getenv(_VERIFIED_APP_ENV) or "")
    if not app_id:
        return {}
    try:
        data = json.loads(_cache_path().read_text(encoding="utf-8"))
        if data.get("application_id") == app_id and isinstance(data.get("emojis"), dict):
            return data["emojis"]
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {}


def _code(entry, cached):
    record = cached.get(entry["key"], {})
    if not isinstance(record, dict):
        return None
    name, emoji_id = record.get("name"), str(record.get("id", ""))
    if (name != entry["name"] or record.get("sha256") != entry["sha256"]
            or not re.fullmatch(r"[1-9][0-9]{16,19}", emoji_id)
            or not isinstance(record.get("animated"), bool)):
        return None
    prefix = "a" if record["animated"] else ""
    return f"<{prefix}:{name}:{emoji_id}>"


def load_collection(application_id=None):
    cached = _cache(application_id)
    return {entry["key"]: _code(entry, cached) or entry["fallback"]
            for entry in MANIFEST["emojis"]}


def apply_constants(namespace, collection):
    for entry in MANIFEST["emojis"]:
        value = collection[entry["key"]]
        namespace[f"CT_{entry['key'].upper()}"] = value
        for constant in entry["constants"]:
            namespace[constant] = value


def catalog(application_id=None, *, dashboard_only=True):
    cached = _cache(application_id)
    entries = [{**entry, "discord_code": _code(entry, cached)}
               for entry in MANIFEST["emojis"]
               if not dashboard_only or entry.get("dashboard_visible", True)]
    providers = list(dict.fromkeys(entry.get("provider", MANIFEST["provider"]) for entry in entries))
    return {"brand": "CloudTIX", "provider": ", ".join(providers), "emojis": entries,
            "ready": sum(entry["discord_code"] is not None for entry in entries),
            "total": len(entries)}


def _save(application_id, records):
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".cloudtix-emojis-", delete=False) as handle:
            temporary = handle.name
            json.dump({"schema_version": 1, "application_id": str(application_id),
                       "emojis": records}, handle, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class _DiscordError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Discord HTTP {status}")


async def _request(session, method, path, deadline, payload=None):
    for attempt in range(4):
        if time.monotonic() >= deadline:
            raise TimeoutError("Emoji startup synchronization exceeded its time budget")
        async with session.request(method, API + path, json=payload) as response:
            if response.status < 400:
                return await response.json()
            delay = None
            if response.status == 429:
                data = await response.json()
                delay = max(0.1, float(data.get("retry_after", 1))) + 0.1
            elif response.status >= 500 and method == "GET":
                delay = 2 ** attempt
            if delay is None or attempt == 3:
                raise _DiscordError(response.status)
            if time.monotonic() + delay >= deadline:
                raise TimeoutError("Discord retry delay exceeds emoji startup time budget")
        await asyncio.sleep(delay)
    raise RuntimeError("Unreachable retry state")


async def sync_from_token(token):
    """Upload missing assets without deleting or changing any existing emojis."""
    os.environ.pop(_VERIFIED_APP_ENV, None)
    if not token:
        LOG.info("CloudTIX emojis: no bot token available; using Unicode fallbacks")
        return
    import aiohttp

    enabled = os.getenv("CLOUDTIX_EMOJI_SYNC", "true").strip().lower() == "true"
    deadline = time.monotonic() + 180
    uploaded = 0
    records = {}
    async with aiohttp.ClientSession(
        headers={"Authorization": f"Bot {token}"},
        timeout=aiohttp.ClientTimeout(total=20),
    ) as session:
        application = await _request(session, "GET", "/oauth2/applications/@me", deadline)
        app_id = str(application["id"])
        os.environ[_VERIFIED_APP_ENV] = app_id
        response = await _request(session, "GET", f"/applications/{app_id}/emojis", deadline)
        existing = {emoji["name"]: emoji for emoji in response["items"]}
        # Reconcile all existing entries first, so a later rate limit cannot
        # hide already available emojis further down the manifest.
        for entry in MANIFEST["emojis"]:
            emoji = existing.get(entry["name"])
            if emoji is not None:
                records[entry["key"]] = {"id": str(emoji["id"]), "name": emoji["name"],
                                          "animated": bool(emoji.get("animated", False)),
                                          "sha256": entry["sha256"]}
        _save(app_id, records)
        for entry in MANIFEST["emojis"]:
            emoji = existing.get(entry["name"])
            if emoji is None and enabled:
                data = (ASSETS / entry["file"]).read_bytes()
                if len(data) > 256 * 1024 or hashlib.sha256(data).hexdigest() != entry["sha256"]:
                    LOG.error("Invalid bundled emoji asset: %s", entry["key"])
                    continue
                mime = "image/gif" if entry["animated"] else "image/png"
                payload = {"name": entry["name"], "image": f"data:{mime};base64,"
                           + base64.b64encode(data).decode("ascii")}
                try:
                    emoji = await _request(session, "POST", f"/applications/{app_id}/emojis",
                                           deadline, payload)
                    uploaded += 1
                except _DiscordError as error:
                    LOG.warning("CloudTIX emoji %s: HTTP %s", entry["key"], error.status)
                    if error.status in (401, 403, 429) or error.status >= 500:
                        break
                    continue
                except (TimeoutError, aiohttp.ClientError):
                    LOG.warning("CloudTIX emoji upload interrupted; remaining assets use Unicode")
                    break
            if emoji is not None:
                records[entry["key"]] = {"id": str(emoji["id"]), "name": emoji["name"],
                                          "animated": bool(emoji.get("animated", False)),
                                          "sha256": entry["sha256"]}
                _save(app_id, records)
    LOG.info("CloudTIX emojis: %s/%s ready, %s uploaded", len(records), len(MANIFEST["emojis"]), uploaded)
