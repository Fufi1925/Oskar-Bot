"""Guild knowledge and personal dashboard coaching, stored in the ticket DB."""
from __future__ import annotations
import time
from contextlib import asynccontextmanager
import aiosqlite
from utils import ticket_ai

DB = 'db/ticket.db'
CHAT_RETENTION = 30 * 86400


@asynccontextmanager
async def connection():
    async with aiosqlite.connect(DB, timeout=10) as db:
        db.row_factory = aiosqlite.Row
        for statement in ticket_ai.SCHEMA:
            await db.execute(statement)
        await db.commit()
        yield db


async def memories(guild_id: int) -> list[dict]:
    async with connection() as db:
        async with db.execute('SELECT * FROM ticket_ai_memories WHERE guild_id=? ORDER BY updated_at DESC,id DESC', (guild_id,)) as cur:
            return [dict(row) for row in await cur.fetchall()]


def validate(content, title='') -> tuple[str, str]:
    if not isinstance(content, str) or not content.strip():
        raise ValueError('empty_knowledge')
    content = content.replace('\x00', '').strip()
    if not content:
        raise ValueError('empty_knowledge')
    if len(content) > 4000:
        raise ValueError('memory_too_long')
    title = str(title or content.split('\n')[0]).strip()[:120]
    return content, title


async def write_memory(db, guild_id: int, content: str, title: str, source: str, memory_id: int | None = None) -> int:
    content, title = validate(content, title)
    if memory_id is not None:
        async with db.execute('SELECT id FROM ticket_ai_memories WHERE id=? AND guild_id=?', (memory_id, guild_id)) as cur:
            if not await cur.fetchone(): raise ValueError('memory_not_found')
    else:
        async with db.execute('SELECT id FROM ticket_ai_memories WHERE guild_id=? AND content=?', (guild_id, content)) as cur:
            duplicate = await cur.fetchone()
        if duplicate: return int(duplicate[0])
    async with db.execute('SELECT content FROM ticket_ai_memories WHERE guild_id=? AND id<>?', (guild_id, memory_id or 0)) as cur:
        entries = await cur.fetchall()
    if len(entries) >= 200 or sum(len(row[0].encode('utf-8')) for row in entries) + len(content.encode('utf-8')) > ticket_ai.MAX_KNOWLEDGE_BYTES:
        raise ValueError('knowledge_too_large')
    if memory_id is None:
        cur = await db.execute('INSERT INTO ticket_ai_memories(guild_id,title,content,source,updated_at) VALUES(?,?,?,?,?)', (guild_id,title,content,source,int(time.time())))
        return int(cur.lastrowid)
    await db.execute('UPDATE ticket_ai_memories SET title=?,content=?,updated_at=? WHERE guild_id=? AND id=?', (title,content,int(time.time()),guild_id,memory_id))
    return memory_id


async def save_memory(guild_id, content, title='', memory_id=None):
    async with connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        result = await write_memory(db, guild_id, content, title, 'manual', memory_id)
        await db.commit()
        return result


async def remove_memory(guild_id, memory_id):
    async with connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        cur = await db.execute('DELETE FROM ticket_ai_memories WHERE id=? AND guild_id=?', (memory_id,guild_id))
        if not cur.rowcount: raise ValueError('memory_not_found')
        await disable_without_knowledge(db, guild_id)
        await db.commit()


async def disable_without_knowledge(db, guild_id):
    async with db.execute('SELECT 1 FROM ticket_ai_memories WHERE guild_id=? UNION ALL SELECT 1 FROM ticket_ai_knowledge WHERE guild_id=? LIMIT 1', (guild_id,guild_id)) as cur:
        if not await cur.fetchone():
            await db.execute('UPDATE ticket_ai_settings SET enabled=0 WHERE guild_id=?', (guild_id,))


async def history(guild_id, user_id):
    async with connection() as db:
        await db.execute('DELETE FROM ticket_ai_coaching WHERE created_at<?', (int(time.time())-CHAT_RETENTION,))
        await db.commit()
        async with db.execute('SELECT id,role,content,created_at FROM ticket_ai_coaching WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 60', (guild_id,user_id)) as cur:
            return [dict(row) for row in reversed(await cur.fetchall())]


async def clear_history(guild_id, user_id):
    async with connection() as db:
        await db.execute('DELETE FROM ticket_ai_coaching WHERE guild_id=? AND user_id=?', (guild_id,user_id))
        await db.commit()


async def record_exchange(guild_id, user_id, message, answer, teach=False):
    async with connection() as db:
        await db.execute('BEGIN IMMEDIATE')
        memory_id = await write_memory(db,guild_id,message,'','chat') if teach else None
        now = int(time.time())
        await db.executemany('INSERT INTO ticket_ai_coaching(guild_id,user_id,role,content,created_at) VALUES(?,?,?,?,?)', [(guild_id,user_id,'user',message,now),(guild_id,user_id,'assistant',answer,now)])
        await db.execute('DELETE FROM ticket_ai_coaching WHERE guild_id=? AND user_id=? AND id NOT IN (SELECT id FROM ticket_ai_coaching WHERE guild_id=? AND user_id=? ORDER BY id DESC LIMIT 60)', (guild_id,user_id,guild_id,user_id))
        await db.commit()
    return memory_id
