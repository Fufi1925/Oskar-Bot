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


def _clean(value: str | None) -> str:
    text = (value or "").strip().rstrip("/")
    # A bare scheme with no host, e.g. the old "https://.vercel.app",
    # renders as a button that goes nowhere. Discord accepts the URL and
    # the user gets a dead link, so it is treated as unset.
    if not text or "://" not in text:
        return ""
    host = text.split("://", 1)[1]
    if not host or host.startswith(".") or "." not in host:
        return ""
    return text


def dashboard_url() -> str:
    """
    The dashboard's public address, or "" when it cannot be determined.

    Checked in order of how likely each is to be both set and correct:

      1. ``DASHBOARD_URL``   -- explicit, wins when present
      2. ``NEXTAUTH_URL``    -- required for login, so it is always set
                                and always right on a working deployment
      3. ``CORS_ORIGINS``    -- first entry, set for the same reason
      4. ``WEBSITE_URL``     -- what the status bot calls it
    """
    for name in ("DASHBOARD_URL", "NEXTAUTH_URL", "WEBSITE_URL"):
        found = _clean(os.getenv(name))
        if found:
            return found

    # CORS_ORIGINS can hold several, comma separated.
    for candidate in (os.getenv("CORS_ORIGINS") or "").split(","):
        found = _clean(candidate)
        if found:
            return found

    return ""


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
