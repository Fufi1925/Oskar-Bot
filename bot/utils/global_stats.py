"""Counts from connected guilds; never from the partial/global user cache."""
import asyncio

from utils import command_stats

_members_lock = asyncio.Lock()


async def global_counts(bot) -> dict[str, int]:
    async with _members_lock:
        guilds = list(bot.guilds)
        semaphore = asyncio.Semaphore(4)
        async def complete(guild):
            expected = getattr(guild, "member_count", None)
            if expected is not None and len(guild.members) < expected:
                async with semaphore:
                    await asyncio.wait_for(guild.chunk(cache=True), timeout=20)
                if len(guild.members) < (getattr(guild, "member_count", None) or expected):
                    raise RuntimeError("Global member statistics are unavailable: member lists are incomplete.")
        await asyncio.gather(*(complete(guild) for guild in guilds))
        # One Discord account can belong to many of these servers.
        users = {member.id for guild in guilds for member in guild.members}
    return {"global_servers": len(guilds), "global_users": len(users),
            "global_commands": await command_stats.total_uses(strict=True)}
