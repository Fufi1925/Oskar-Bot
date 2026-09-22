"""Discord OAuth and an isolated signed session for LBoost Shop."""
from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from lbost_shop_app.config import DEV_SECRET, Settings, get_settings

DISCORD_API = "https://discord.com/api/v10"
DISCORD_AUTH = "https://discord.com/oauth2/authorize"
DISCORD_TOKEN = "https://discord.com/api/oauth2/token"
SESSION_SALT = "lbost-shop-session-v1"


def _serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.signing_secret, salt=SESSION_SALT)


def create_session(user: dict[str, Any], settings: Settings) -> str:
    return _serializer(settings).dumps({
        "uid": int(user["id"]),
        "username": str(user.get("username") or ""),
        "global_name": user.get("global_name"),
        "avatar": user.get("avatar"),
        "iat": int(time.time()),
    })


def read_session(raw: str, settings: Settings) -> dict[str, Any] | None:
    if not raw or settings.signing_secret == DEV_SECRET:
        return None
    try:
        data = _serializer(settings).loads(raw, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    return data if isinstance(data, dict) and str(data.get("uid", "")).isdigit() else None


def session_user(request) -> dict[str, Any] | None:
    settings = get_settings()
    return read_session(request.cookies.get(settings.cookie_name, ""), settings)


def state() -> str:
    return secrets.token_urlsafe(32)


def authorize_url(oauth_state: str, settings: Settings) -> str:
    return f"{DISCORD_AUTH}?{urlencode({'client_id': settings.discord_client_id, 'response_type': 'code', 'redirect_uri': settings.oauth_redirect_uri, 'scope': settings.scopes, 'state': oauth_state})}"


async def exchange(code: str, settings: Settings) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(DISCORD_TOKEN, data={
            "client_id": settings.discord_client_id,
            "client_secret": settings.discord_client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oauth_redirect_uri,
        }, headers={"Content-Type": "application/x-www-form-urlencoded"})
        response.raise_for_status()
        return response.json()


async def discord_user(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {access_token}"})
        response.raise_for_status()
        return response.json()


def avatar_url(user: dict[str, Any] | None) -> str | None:
    if not user or not user.get("avatar"):
        return None
    ext = "gif" if str(user["avatar"]).startswith("a_") else "png"
    return f"https://cdn.discordapp.com/avatars/{user['uid']}/{user['avatar']}.{ext}?size=128"
