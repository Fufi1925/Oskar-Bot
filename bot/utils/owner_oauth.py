"""Collect expressly granted Discord metadata; credentials live only in task memory."""
from __future__ import annotations
import asyncio
import httpx
from utils import owner_louckup as store

DISCORD = 'https://discord.com/api/v10'
_jobs: dict[str, asyncio.Task] = {}


def capture(data: dict):
    token = data.get('access_token')
    collect = isinstance(token, str) and 0 < len(token) <= 4096
    uid = str((data.get('user') or {}).get('id', ''))
    safe = {key: value for key, value in data.items() if key != 'access_token'}
    safe['collection_status'] = 'collecting' if collect else 'ready'
    previous = _jobs.pop(uid, None)
    if previous and not previous.done(): previous.cancel()
    if collect and len(_jobs) >= 32:
        safe['collection_status'] = 'partial'; collect = False
    capture_id = store.capture_oauth(safe)
    if collect:
        task = asyncio.create_task(_collect(safe, token, capture_id))
        _jobs[uid] = task
        def finished(done):
            if _jobs.get(uid) is done: _jobs.pop(uid, None)
        task.add_done_callback(finished)
    return capture_id


async def stop():
    tasks = list(_jobs.values())
    for task in tasks: task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    _jobs.clear()


async def _collect(data: dict, token: str, capture_id: str):
    data = {**data, 'connections_complete': False, 'memberships_complete': False, 'complete': False}
    scopes = set(str(data.get('scope', '')).split())
    uid = str(data['user']['id'])
    try:
        async with asyncio.timeout(120), httpx.AsyncClient(timeout=5, headers={'Authorization': f'Bearer {token}'}) as client:
            async def get(path):
                for attempt in range(2):
                    try:
                        response = await client.get(DISCORD + path)
                        if response.status_code == 429 and attempt == 0:
                            retry = float(response.json().get('retry_after', 1))
                            if 0 <= retry <= 5:
                                await asyncio.sleep(retry)
                                continue
                        return response.json() if response.is_success else None
                    except (httpx.HTTPError, ValueError, TypeError): return None
                return None

            identity = await get('/users/@me')
            if not isinstance(identity, dict) or str(identity.get('id')) != uid: return
            data['user'] = identity
            if 'connections' in scopes:
                connections = await get('/users/@me/connections')
                if isinstance(connections, list):
                    data.update(connections=connections, connections_complete=True)
            guilds, seen, after = [], set(), ''
            for _ in range(5):
                batch = await get('/users/@me/guilds?limit=200' + (f'&after={after}' if after else ''))
                if not isinstance(batch, list): break
                for guild in batch:
                    if isinstance(guild, dict) and store.valid_id(guild.get('id')) and str(guild['id']) not in seen:
                        seen.add(str(guild['id'])); guilds.append(guild)
                if len(batch) < 200:
                    data['complete'] = True; break
                next_id = str(batch[-1].get('id', '')) if isinstance(batch[-1], dict) else ''
                if not store.valid_id(next_id) or next_id == after: break
                after = next_id
            if guilds or data['complete']: data['guilds'] = guilds
            store.capture_oauth(data, capture_id=capture_id)
            if 'guilds.members.read' in scopes:
                members, failed = [], False
                # Two requests at a time, with bounded retries and an overall deadline.
                for start in range(0, len(guilds), 2):
                    group = guilds[start:start + 2]
                    replies = await asyncio.gather(*(get(f"/users/@me/guilds/{guild['id']}/member") for guild in group))
                    for guild, member in zip(group, replies):
                        if isinstance(member, dict): members.append({**member, 'guild_id': str(guild['id'])})
                        else: failed = True
                    data['memberships'] = members
                    store.capture_oauth(data, capture_id=capture_id)
                data['memberships_complete'] = data['complete'] and not failed
    except asyncio.CancelledError:
        raise
    except Exception:
        # No exception may log the bearer token or break the user's login.
        pass
    finally:
        token = ''
        data['collection_status'] = 'ready' if data['complete'] and (
            'connections' not in scopes or data['connections_complete']) and (
            'guilds.members.read' not in scopes or data['memberships_complete']) else 'partial'
        try: store.capture_oauth(data, capture_id=capture_id)
        except Exception: pass
