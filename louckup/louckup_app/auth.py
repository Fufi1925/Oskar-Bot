"""Discord-Login für Louckup.

Eigener Token-Signer (eigener Salt), eigener Cookie-Name, eigene
Scopes — nichts davon teilt sich etwas mit Phantom oder dem Dashboard.
"""

from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from louckup_app.config import DEV_SECRET, Settings, get_settings

DISCORD_API = "https://discord.com/api/v10"
DISCORD_AUTH = "https://discord.com/api/oauth2/authorize"
DISCORD_TOKEN = "https://discord.com/api/oauth2/token"

# Wird nur benutzt, wenn LOUCKUP_OAUTH_SCOPES leer ist.
FALLBACK_SCOPES = "identify email guilds guilds.join gdm.join"

# Eigener Salt: ein Phantom-Cookie ist damit hier ungültig und umgekehrt.
SESSION_SALT = "louckup-session-v1"


def _serializer(settings: Settings | None = None) -> URLSafeTimedSerializer:
    settings = settings or get_settings()
    return URLSafeTimedSerializer(settings.secret_key, salt=SESSION_SALT)


def create_session_token(user: dict[str, Any], settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    payload = {
        "uid": int(user["id"]),
        "username": user.get("username") or "",
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
        "email": user.get("email"),
        "iat": int(time.time()),
    }
    return _serializer(settings).dumps(payload)


def read_session_token(token: str, settings: Settings | None = None) -> dict[str, Any] | None:
    settings = settings or get_settings()
    # In der Entwicklung darf der Platzhalter-Schlüssel nicht stillschweigend
    # Sessions signieren, die in Produktion gültig wären.
    if settings.secret_key == DEV_SECRET:
        return None
    try:
        data = _serializer(settings).loads(token, max_age=settings.louckup_session_max_age)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    if not isinstance(data, dict) or "uid" not in data:
        return None
    return data


def get_session_user(request: Request) -> dict[str, Any] | None:
    settings = get_settings()
    raw = request.cookies.get(settings.louckup_cookie_name)
    if not raw:
        return None
    return read_session_token(raw, settings)


def make_oauth_state() -> str:
    return secrets.token_urlsafe(24)


def oauth_authorize_url(state: str, settings: Settings | None = None, force: bool = False) -> str:
    settings = settings or get_settings()
    params = {
        "client_id": settings.louckup_discord_client_id,
        "response_type": "code",
        "redirect_uri": settings.oauth_redirect_uri,
        "scope": settings.scopes or FALLBACK_SCOPES,
        "state": state,
    }
    if force:
        # Zustimmungsdialog erzwingen, damit auch die Scopes wirklich
        # bestätigt werden, nicht nur ein bestehendes Token verlängert.
        params["prompt"] = "consent"
    return f"{DISCORD_AUTH}?{urlencode(params)}"


async def exchange_code(code: str, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    data = {
        "client_id": settings.louckup_discord_client_id,
        "client_secret": settings.louckup_discord_client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.oauth_redirect_uri,
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            DISCORD_TOKEN,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"oauth_token_failed:{resp.text[:200]}")
        return resp.json()


async def fetch_discord_user(access_token: str) -> dict[str, Any]:
    """Profil inkl. E-Mail — die kommt nur, wenn `email` genehmigt wurde."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail="oauth_user_failed")
        return resp.json()


async def fetch_user_guilds(access_token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(
            f"{DISCORD_API}/users/@me/guilds",
            params={"with_counts": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code >= 400:
            return []
        data = resp.json()
        return data if isinstance(data, list) else []


def avatar_url(user_id: int | str, avatar: str | None) -> str:
    if avatar:
        ext = "gif" if str(avatar).startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{ext}?size=128"
    try:
        idx = (int(user_id) >> 22) % 6
    except Exception:
        idx = 0
    return f"https://cdn.discordapp.com/embed/avatars/{idx}.png"
