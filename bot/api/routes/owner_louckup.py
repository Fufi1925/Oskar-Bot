"""Separate from the old lookup. Every data request requires owner + step-up."""
from __future__ import annotations
import hmac
import os
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from api.dependencies import get_bot, run_on_bot_loop
from utils import owner_louckup as store, user_lookup


def service_guard(authorization: str = Header(default='')):
    key = os.getenv('DASHBOARD_API_KEY', '')
    if not key or not hmac.compare_digest(authorization.encode(), ('Bearer ' + key).encode()):
        raise HTTPException(401, 'Unauthorized')


router = APIRouter(dependencies=[Depends(service_guard)])


def owner_guard(request: Request):
    actor = request.headers.get('x-louckup-actor', '')
    binding = request.headers.get('x-louckup-session', '')
    if actor not in store.owner_ids():
        raise HTTPException(403, 'Owner access required')
    if len(binding) != 64 or any(c not in '0123456789abcdef' for c in binding):
        raise HTTPException(401, 'Dashboard session required')
    return actor, binding


@router.get('/status')
async def status(request: Request):
    actor, binding = owner_guard(request)
    expires = store.grant_expires(actor, binding, request.headers.get('x-louckup-grant', ''))
    return {'configured': store.authenticator_key() is not None, 'unlocked': bool(expires), 'expires_at': expires}


@router.post('/unlock')
async def unlock(data: dict, request: Request):
    actor, binding = owner_guard(request)
    try:
        return store.unlock(actor, binding, str(data.get('code', '')))
    except store.AuthError as error:
        raise HTTPException(error.status, error.reason, headers={'Retry-After': str(error.retry)} if error.retry else None)


@router.post('/lock')
async def lock(request: Request):
    owner_guard(request)
    store.lock(request.headers.get('x-louckup-grant', ''))
    return {'unlocked': False}


@router.post('/oauth-snapshot')
async def snapshot(data: dict):
    # Server-to-server only. The browser proxy does not expose this action.
    try:
        store.capture_oauth(data)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, 'Invalid OAuth snapshot')
    return {'recorded': True}


@router.get('/users/{user_id}')
async def lookup(user_id: str, request: Request, bot=Depends(get_bot)):
    actor, binding = owner_guard(request)
    if not store.grant_expires(actor, binding, request.headers.get('x-louckup-grant', '')):
        raise HTTPException(403, 'Two-factor authentication required')
    if not store.valid_id(user_id):
        raise HTTPException(400, 'Invalid Discord ID')
    data = await run_on_bot_loop(user_lookup.lookup(bot, user_id))
    # Explicit allowlist: no database dump, private messages or OAuth credentials.
    profile = {key: data.get(key) for key in ('user_id', 'found', 'username', 'display_name', 'avatar', 'is_bot', 'created_at')}
    guild_fields = ('guild_id', 'guild_name', 'guild_icon', 'member_count', 'is_owner', 'is_admin', 'top_role', 'joined_at', 'roles')
    guilds = [{key: guild.get(key) for key in guild_fields} for guild in data['guilds']]
    ban = data.get('bot_ban')
    store.record_lookup(actor, user_id)
    return {'profile': profile, 'bot': {'guilds': guilds, 'cached_member_data': True,
            'members_intent': bool(getattr(getattr(bot, 'intents', None), 'members', False)),
            'ban': {key: ban.get(key) for key in ('reason', 'banned_at', 'banned_by')} if ban else None},
            'dashboard': store.login_summary(user_id), 'oauth': store.oauth_snapshot(user_id)}
