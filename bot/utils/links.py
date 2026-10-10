# ╔══════════════════════════════════════════════════════════════════╗
# ║   Public links the bot puts in messages                          ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Where the dashboard lives, and how to link to it.

There was no shared answer to that. ``utils/nuke_alert.py`` read
``DASHBOARD_URL`` and skipped its button when it was empty -- which it
is on the live deployment, so that button never appeared. The welcome
DM had a hard-coded ``https://.vercel.app``, a URL with no host at all,
which is presumably why it was commented out rather than fixed.

So: one function, and it falls back through the variables that *are*
set in production rather than requiring a new one.

``NEXTAUTH_URL`` is the reliable one -- the dashboard cannot log anybody
in without it, so if the site works, that value is correct.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit


PUBLIC_WEBSITE_URL = "https://cloudtix.up.railway.app"
# Retained only to migrate URL settings from the former deployment.
_LEGACY_WEBSITE_HOSTS = {"universtiy-bot.up.railway.app", "university-bot.up.railway.app"}


def normalize_public_url(value: str | None, *, origin_only: bool = False) -> str:
    """Normalize configured public URLs and migrate the former website host."""
    raw = (value or "").strip().strip('"').strip("'")
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        if (parts.scheme not in {"http", "https"} or not host
                or host.startswith(".") or parts.username or parts.password):
            return ""
        # Accessing port also rejects malformed port values.
        _ = parts.port
        scheme, netloc = parts.scheme, parts.netloc
        if host in _LEGACY_WEBSITE_HOSTS:
            scheme, netloc = "https", "cloudtix.up.railway.app"
        return urlunsplit((scheme, netloc,
                          "" if origin_only else parts.path.rstrip("/"),
                          "" if origin_only else parts.query,
                          "" if origin_only else parts.fragment))
    except ValueError:
        return ""


def _clean(value: str | None) -> str:
    result = normalize_public_url(value, origin_only=True)
    if not result or "." not in (urlsplit(result).hostname or ""):
        return ""
    return result


def dashboard_url() -> str:
    """
    The dashboard's public address, or "" when it cannot be determined.

    Checked in order of how likely each is to be both set and correct:

      1. ``DASHBOARD_URL``   -- explicit, wins when present
      2. ``NEXTAUTH_URL``    -- required for login, so it is always set
                                and always right on a working deployment
      ``DASHBOARD_PUBLIC_URL`` is also accepted as an explicit override.
      ``WEBSITE_URL``, ``CORS_ORIGINS`` and ``RAILWAY_PUBLIC_DOMAIN``
      provide fallbacks for services without NextAuth.
    """
    for name in ("DASHBOARD_URL", "DASHBOARD_PUBLIC_URL", "NEXTAUTH_URL", "WEBSITE_URL"):
        found = _clean(os.getenv(name))
        if found:
            return found

    # CORS_ORIGINS can hold several, comma separated.
    for candidate in (os.getenv("CORS_ORIGINS") or "").split(","):
        found = _clean(candidate)
        if found:
            return found

    domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or "").strip()
    return _clean(f"https://{domain}") if domain else ""


def guild_dashboard_url(guild_id: int | str, tab: str = "") -> str:
    """
    Link straight to one server's settings, optionally to one tab.

    Returns "" when there is no dashboard URL, so callers can leave the
    button out rather than render one that goes nowhere.
    """
    base = dashboard_url()
    if not base:
        return ""
    path = f"{base}/dashboard/guild/{guild_id}"
    return f"{path}/{tab.strip('/')}" if tab else path


def support_url() -> str:
    """The support server invite."""
    for name in ("SUPPORT_INVITE_URL", "NEXT_PUBLIC_SUPPORT_INVITE"):
        found = (os.getenv(name) or "").strip()
        if found:
            return found
    try:
        from utils.config import serverLink

        return (serverLink or "").strip()
    except Exception:  # noqa: BLE001
        return ""
