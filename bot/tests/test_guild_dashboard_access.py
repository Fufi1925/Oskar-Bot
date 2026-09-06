#!/usr/bin/env python3
"""Small end-to-end store check for per-guild dashboard grants."""

import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from api.routes import guild_access as access  # noqa: E402


class Color:
    value = 0x5865F2


class Avatar:
    url = "https://cdn.example/avatar.png"


class Role:
    def __init__(self, role_id, name, default=False):
        self.id, self.name = role_id, name
        self.color, self.managed, self.members = Color(), False, []
        self._default = default

    def is_default(self):
        return self._default


class Member:
    bot = False
    display_name = "Alice"
    display_avatar = Avatar()

    def __init__(self, user_id, roles):
        self.id, self.roles = user_id, roles

    def __str__(self):
        return "alice"


class Guild:
    id, name, owner_id, member_count, icon = 888, "Test", 1, 2, None

    def __init__(self):
        self.everyone = Role(self.id, "@everyone", True)
        self.staff = Role(99, "Staff")
        self.member = Member(42, [self.everyone, self.staff])
        self.staff.members = [self.member]

    def get_role(self, role_id):
        return next((role for role in (self.everyone, self.staff) if role.id == role_id), None)

    def get_member(self, user_id):
        return self.member if user_id == self.member.id else None

    async def fetch_member(self, _user_id):
        raise RuntimeError("not found")


class Bot:
    def __init__(self):
        self.guild = Guild()
        self.guilds = [self.guild]

    def get_guild(self, guild_id):
        return self.guild if guild_id == self.guild.id else None

    def get_user(self, _user_id):
        return None


async def noop(*_args, **_kwargs):
    pass


async def main():
    access.DB_PATH = os.path.join(tempfile.mkdtemp(), "access.db")
    access.feature_audit.log_action = noop
    bot = Bot()

    await access.add_role(888, access.GrantRole(role_id="99"), bot)
    assert (await access.check_access(888, 42, bot))["source"] == "role"

    await access.add_user(888, access.GrantUser(user_id="42"), bot)
    listing = await access.list_access(888, bot)
    assert len(listing["roles"]) == 1 and len(listing["users"]) == 1
    assert len((await access.user_guilds(42, bot))["guilds"]) == 1

    await access.remove_role(888, 99)
    await access.remove_user(888, 42)
    assert not (await access.check_access(888, 42, bot))["allowed"]
    print("guild dashboard access: all checks passed")


if __name__ == "__main__":
    asyncio.run(main())
