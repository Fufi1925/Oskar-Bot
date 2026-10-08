"""Server policy reads and strict OWNER_IDS-only dashboard controls."""
from fastapi import APIRouter, Depends, HTTPException, Request
from api.routes.owner_louckup import service_guard
from utils import dashboard_settings as store, owner_louckup, account_security

router = APIRouter(dependencies=[Depends(service_guard)])


def owner(request: Request):
    actor = request.headers.get('x-dashboard-settings-actor', '')
    if actor not in owner_louckup.owner_ids(): raise HTTPException(403, 'owner_required')
    return actor


@router.get('/oauth-policy')
async def policy():
    # Internal use by the anonymous OAuth initiation routes; no browser proxy.
    return {'scopes': store.read()['scopes']}


@router.get('/settings')
async def settings(request: Request):
    owner(request)
    return store.read()


@router.patch('/settings')
async def save(data: dict, request: Request):
    actor = owner(request)
    try: return store.save(data.get('scopes'), actor)
    except ValueError as error: raise HTTPException(400, str(error))


@router.post('/revoke-all')
async def revoke_all(request: Request):
    return {'revoked_before_ms': store.revoke_everyone(owner(request))}


@router.post('/revoke-user')
async def revoke_user(data: dict, request: Request):
    owner(request)
    uid = data.get('user_id')
    if not isinstance(uid, str) or not owner_louckup.valid_id(uid): raise HTTPException(400, 'invalid_user_id')
    uid = str(int(uid))
    return {'user_id': uid, 'revoked_before_ms': account_security.revoke_all(uid)}
