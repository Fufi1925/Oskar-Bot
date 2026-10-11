"""CloudTIX's bundled application emojis, synchronized before cog imports.

Standalone-safe: do not import utils/core here. Discord remains the authority
for IDs and animated flags. Missing uploads always have a Unicode fallback.
"""
import asyncio
import base64
from datetime import datetime, timezone
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
# Later packs take precedence for native bot aliases. Retired collections are
# kept for the precise deletion plan; the replacement pack has unique keys.
NEUTRAL_PACK = ASSETS / "neutral/emojis.json"
for relative_manifest in ("discord-color/emojis.json", "discord-utility/emojis.json", "bot-gray/emojis.json", "bot-color/emojis.json", "neutral/emojis.json"):
    pack_path = ASSETS / relative_manifest
    if pack_path.exists():
        MANIFEST["emojis"].extend(json.loads(pack_path.read_text(encoding="utf-8"))["emojis"])
API = "https://discord.com/api/v10"
_VERIFIED_APP_ENV = "CLOUDTIX_VERIFIED_EMOJI_APPLICATION_ID"
_retirement_path = ASSETS / "retirement.json"
RETIREMENT = json.loads(_retirement_path.read_text(encoding="utf-8")) if _retirement_path.exists() else {}
RETIRED_KEYS = set(RETIREMENT.get("retired_keys", []))
RETIRED_NAMES = set(RETIREMENT.get("names", []))


def _retired(entry):
    return entry["key"] in RETIRED_KEYS or entry["name"] in RETIRED_NAMES


def _retirement_report_path():
    return _cache_path().with_name("cloudtix-emoji-retirement.json")


def retirement_status(application_id=None):
    if not RETIREMENT:
        return None
    app_id = str(application_id or os.getenv(_VERIFIED_APP_ENV) or "")
    try:
        data = json.loads(_retirement_report_path().read_text(encoding="utf-8"))
        if data.get("application_id") == app_id and data.get("plan_id") == RETIREMENT["plan_id"]:
            return {key: data.get(key) for key in ("status", "deleted", "remaining", "updated_at", "error")}
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return {"status": "pending", "deleted": 0, "remaining": None}


def _save_retirement_status(application_id, status, deleted, remaining, error=None):
    path = _retirement_report_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"application_id": str(application_id), "plan_id": RETIREMENT["plan_id"],
            "status": status, "deleted": deleted, "remaining": remaining,
            "error": error, "updated_at": datetime.now(timezone.utc).isoformat()}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".cloudtix-emoji-retirement-", delete=False) as handle:
            temporary = handle.name
            json.dump(data, handle)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _matches_retirement(emoji):
    # Both exact historical names and Discord's actual creation date must match.
    # No prefix-based deletion, guild emoji deletion or guessed application ID.
    if emoji.get("name") not in RETIRED_NAMES:
        return False
    emoji_id = str(emoji.get("id", ""))
    if not re.fullmatch(r"[1-9][0-9]{16,19}", emoji_id):
        return False
    created_ms = (int(emoji_id) >> 22) + 1420070400000
    start_ms = datetime.fromisoformat(RETIREMENT["created_from_utc"]).timestamp() * 1000
    end_ms = datetime.fromisoformat(RETIREMENT["created_until_utc"]).timestamp() * 1000
    return start_ms <= created_ms < end_ms


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
    if _retired(entry):
        return None
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
    collection = {entry["key"]: _code(entry, cached) or entry["fallback"]
                  for entry in MANIFEST["emojis"]}
    # Later active packs override the matching semantic keys and constants.
    for entry in MANIFEST["emojis"]:
        if entry.get("replaces"):
            collection[entry["replaces"]] = collection[entry["key"]]
        for semantic_key in entry.get("replaces_keys", []):
            collection[semantic_key] = collection[entry["key"]]
    return collection


def apply_constants(namespace, collection):
    for entry in MANIFEST["emojis"]:
        value = collection[entry["key"]]
        namespace[f"CT_{entry['key'].upper()}"] = value
        for constant in entry["constants"]:
            namespace[constant] = value


def catalog(application_id=None, *, dashboard_only=True):
    cached = _cache(application_id)
    entries = [{**entry, "discord_code": _code(entry, cached), "retired": _retired(entry)}
               for entry in MANIFEST["emojis"]
               if not dashboard_only or (
                   entry["file"].startswith("neutral/") if NEUTRAL_PACK.exists()
                   else entry.get("dashboard_visible", True))]
    providers = list(dict.fromkeys(entry.get("provider", MANIFEST["provider"]) for entry in entries))
    return {"brand": "CloudTIX", "provider": ", ".join(providers), "emojis": entries,
            "ready": sum(entry["discord_code"] is not None for entry in entries),
            "total": len(entries), "cleanup": retirement_status(application_id)}


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
                if response.status == 204:
                    return None
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
        # Upload the current bot style and dashboard pack before older sets,
        # so unused historical artwork cannot consume the startup time budget.
        upload_entries = sorted((entry for entry in MANIFEST["emojis"] if not _retired(entry)), key=lambda entry: (
            0 if entry["file"].startswith("neutral/") else
            1 if entry["file"].startswith("bot-color/") else
            2 if entry.get("dashboard_visible", True) else 3
        ))
        for entry in upload_entries:
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


async def cleanup_retired_from_token(token):
    """Execute the user's dated deletion plan without delaying bot startup.

    Verify the token's own application, delete only exact managed names whose
    snowflakes fall in the requested window, and confirm absence with a new GET.
    Rate limits/network failures leave a resumable report and retry in background.
    """
    if not token or not RETIREMENT:
        return
    import aiohttp

    application_id = None
    deleted = 0
    remaining = None
    async with aiohttp.ClientSession(headers={"Authorization": f"Bot {token}"},
                                     timeout=aiohttp.ClientTimeout(total=20)) as session:
        while True:
            deadline = time.monotonic() + 120
            try:
                if application_id is None:
                    application = await _request(session, "GET", "/oauth2/applications/@me", deadline)
                    application_id = str(application["id"])
                    previous = retirement_status(application_id) or {}
                    deleted = int(previous.get("deleted") or 0)
                response = await _request(session, "GET", f"/applications/{application_id}/emojis", deadline)
                targets = [emoji for emoji in response["items"] if _matches_retirement(emoji)]
                remaining = len(targets)
                if not targets:
                    _save_retirement_status(application_id, "completed", deleted, 0)
                    LOG.info("CloudTIX emoji cleanup confirmed: %s deleted, no matching emojis remaining", deleted)
                    return
                _save_retirement_status(application_id, "running", deleted, remaining)
                for emoji in targets:
                    try:
                        await _request(session, "DELETE", f"/applications/{application_id}/emojis/{emoji['id']}", deadline)
                        deleted += 1
                    except _DiscordError as error:
                        if error.status != 404:
                            raise
                    remaining -= 1
                    _save_retirement_status(application_id, "running", deleted, remaining)
                # Repeat the GET before marking completion; stale cache counts
                # or a successful DELETE alone never serve as confirmation.
            except _DiscordError as error:
                if application_id:
                    _save_retirement_status(application_id, "blocked" if error.status in (401, 403) else "waiting",
                                            deleted, remaining, f"Discord HTTP {error.status}")
                LOG.warning("CloudTIX emoji cleanup: Discord HTTP %s", error.status)
                if error.status in (401, 403):
                    return
                await asyncio.sleep(30)
            except (TimeoutError, aiohttp.ClientError):
                if application_id:
                    _save_retirement_status(application_id, "waiting", deleted, remaining, "Discord temporarily unavailable")
                LOG.warning("CloudTIX emoji cleanup paused; retrying in 30 seconds")
                await asyncio.sleep(30)
