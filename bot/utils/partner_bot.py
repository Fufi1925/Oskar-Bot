# ╔══════════════════════════════════════════════════════════════════╗
# ║   Handing a server over to the template bot                      ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Inviting a second bot and letting it know who sent it.

**A bot cannot invite another bot.** Discord has no API for it, not even
with administrator rights: the OAuth2 flow requires a signed-in human
clicking "Authorise" in a browser. That is deliberate — otherwise one
compromised bot could pull in a dozen more, which is precisely a nuke.

So the flow is: University Bot posts a ready-made invite link carrying a
signed `state` value. When the template bot joins, it reads that value
back and knows the join came from us, for which guild, and who asked.

The signature matters. Without it anybody could append
`?state=university-bot` to their own invite and have the template bot
treat a stranger's server as ours.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time


# Shared between the two bots. Both must see the same value or the
# signature check fails — which is the point.
# Identifies us to the template bot. Part of the signed payload, so
# changing it invalidates every link already handed out -- the template
# bot compares against this exact string.
SOURCE = "university-bot"

SECRET_ENV = "PARTNER_HANDSHAKE_SECRET"

# How long a handshake stays valid. Long enough to click through the
# Discord dialog, short enough that a leaked link is worthless tomorrow.
MAX_AGE = 3600


def _secret() -> bytes:
    value = os.getenv(SECRET_ENV, "")
    return value.encode("utf-8") if value else b""


def is_configured() -> bool:
    return bool(_secret())


def _b64(raw: bytes) -> str:
    # URL-safe and unpadded: this ends up in a query string.
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def make_state(guild_id: int, user_id: int, extra: dict | None = None) -> str:
    """
    A signed token describing who is inviting the template bot where.

    Carried through Discord's OAuth dialog untouched and handed back to
    the other bot on join.
    """
    payload = {
        "g": str(guild_id),
        "u": str(user_id),
        "t": int(time.time()),
        "src": SOURCE,
    }
    if extra:
        payload.update(extra)

    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def read_state(state: str) -> dict | None:
    """
    Verify and unpack a token. None means do not trust it.

    Checked in this order: shape, signature, age. The signature is
    compared with `compare_digest` so a wrong guess cannot be narrowed
    down by timing.
    """
    if not state or "." not in state or not _secret():
        return None

    body, _, signature = state.partition(".")
    try:
        expected = _b64(
            hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            return None

        payload = json.loads(_unb64(body).decode("utf-8"))
    except Exception:
        return None

    if payload.get("src") != SOURCE:
        return None

    issued = int(payload.get("t", 0))
    if issued <= 0 or time.time() - issued > MAX_AGE:
        return None

    return payload


def invite_url(
    client_id: str, *, guild_id: int, user_id: int,
    permissions: int = 8, extra: dict | None = None,
) -> str:
    """
    The link a human clicks to add the template bot.

    `guild_id` preselects the server in the dialog, `disable_guild_select`
    stops somebody from redirecting it elsewhere by accident, and `state`
    is what makes the other side able to recognise us.
    """
    from urllib.parse import urlencode

    query = {
        "client_id": str(client_id),
        "permissions": str(permissions),
        "scope": "bot applications.commands",
        "guild_id": str(guild_id),
        "disable_guild_select": "true",
    }
    if is_configured():
        query["state"] = make_state(guild_id, user_id, extra)

    return "https://discord.com/oauth2/authorize?" + urlencode(query)


# ── the receiving side, for reference ───────────────────────────────
#
# The template bot cannot read `state` from the join event — Discord does
# not pass it to the bot. It arrives at the OAuth *redirect URI*, which
# is a web endpoint the other bot owns. The flow there is:
#
#   1. user clicks the link, authorises
#   2. Discord redirects to the template bot's redirect URI with
#      ?code=…&guild_id=…&state=…
#   3. that endpoint calls read_state(state); if it verifies, the guild
#      is marked as "sent by University Bot" before it has even joined
#   4. on_guild_join looks the guild up and posts the template
#
# `pending_handoffs` below is the small piece of that the template bot
# needs; it is kept here so both bots can share one implementation.


class Handoffs:
    """
    Guilds that were sent over, waiting for the bot to actually join.

    In-memory on purpose: an entry is worthless after MAX_AGE, and losing
    them on restart is safer than acting on a stale one.
    """

    def __init__(self) -> None:
        self._pending: dict[int, dict] = {}

    def remember(self, guild_id: int, payload: dict) -> None:
        self._pending[int(guild_id)] = {**payload, "seen": time.time()}
        self._prune()

    def claim(self, guild_id: int) -> dict | None:
        """Take the entry, if there is a fresh one. Removes it."""
        self._prune()
        return self._pending.pop(int(guild_id), None)

    def peek(self, guild_id: int) -> dict | None:
        self._prune()
        return self._pending.get(int(guild_id))

    def _prune(self) -> None:
        cutoff = time.time() - MAX_AGE
        for guild_id in [
            g for g, p in self._pending.items() if p.get("seen", 0) < cutoff
        ]:
            self._pending.pop(guild_id, None)

    def __len__(self) -> int:
        self._prune()
        return len(self._pending)


handoffs = Handoffs()
