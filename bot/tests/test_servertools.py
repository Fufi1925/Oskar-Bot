"""
Server tools: the scans report real state, the actions change real things,
and the guard rails hold.

The previous per-guild admin dashboard was twenty toggles that wrote a
boolean nothing read. These endpoints replace it, so the important part is
that they refuse what they must refuse — deleting @everyone, touching a
role above the bot, an unknown verification level — rather than failing
halfway through and leaving the server in a strange state.

Run:  python3 tests/test_servertools.py
"""

import os
import sys
import tempfile
import warnings
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

os.environ["ALLOW_KEYLESS_API"] = "true"
os.environ.pop("DASHBOARD_API_KEY", None)
warnings.filterwarnings("ignore")

import discord  # noqa: E402

GUILD = 111


def perms(**kw):
    p = discord.Permissions.none()
    for k, v in kw.items():
        setattr(p, k, v)
    return p


class FakeRole:
    def __init__(self, rid, name, permissions, position, members=0, managed=False):
        self.id, self.name = rid, name
        self.permissions, self.position = permissions, position
        self.colour = discord.Colour(0)
        self.managed, self.mentionable, self.hoist = managed, False, False
        self.members = [object()] * members
        self.deleted = False
        self.edited = None

    def is_default(self):
        return self.name == "@everyone"

    async def delete(self, reason=None):
        self.deleted = True

    async def edit(self, **kwargs):
        self.edited = kwargs


class FakeChannel:
    def __init__(self, cid, name):
        self.id, self.name = cid, name
        self.category = None
        self.slowmode_delay = 0
        self.overwrites = {}

    def is_nsfw(self):
        return False

    def overwrites_for(self, _role):
        return discord.PermissionOverwrite()

    def permissions_for(self, _member):
        return perms(send_messages=True, read_messages=True)

    async def edit(self, slowmode_delay=None, reason=None):
        if slowmode_delay is not None:
            self.slowmode_delay = slowmode_delay

    async def set_permissions(self, target, overwrite=None, reason=None):
        self.overwrites[target] = overwrite


class FakeInvite:
    def __init__(self, code):
        self.code, self.url = code, f"https://discord.gg/{code}"
        self.uses, self.max_uses, self.max_age = 3, 0, 0
        self.channel, self.inviter, self.created_at = None, None, None
        self.revoked = False

    async def delete(self, reason=None):
        self.revoked = True


class FakeGuild:
    id, name, icon, owner_id = GUILD, "Test", None, 1
    member_count, emojis = 8, []
    premium_tier, premium_subscription_count = 0, 0
    created_at = datetime.now(timezone.utc) - timedelta(days=500)
    verification_level = discord.VerificationLevel.low

    def __init__(self):
        self.default_role = FakeRole(1, "@everyone", perms(), 0)
        self.admin = FakeRole(900, "Admin", perms(administrator=True, kick_members=True), 3, members=2)
        self.unused = FakeRole(901, "Leer", perms(), 2)
        self.above = FakeRole(902, "Owner", perms(administrator=True), 9, members=1)
        self.managed = FakeRole(903, "BotRole", perms(), 1, managed=True)
        self.roles = [self.default_role, self.admin, self.unused, self.above, self.managed]

        self.channel = FakeChannel(800, "general")
        self.text_channels = [self.channel]
        self.voice_channels, self.categories = [], []
        self.members = []

        self.me = type("M", (), {})()
        self.me.top_role = FakeRole(950, "Bot", perms(), 5)
        self.me.guild_permissions = perms(
            manage_roles=True, manage_guild=True, manage_webhooks=True
        )
        self.invite = FakeInvite("abc123")
        self.edited = None

    def get_role(self, rid):
        return next((r for r in self.roles if r.id == int(rid)), None)

    def get_channel(self, cid):
        return self.channel if int(cid) == 800 else None

    async def webhooks(self):
        return []

    async def invites(self):
        return [self.invite]

    async def edit(self, **kwargs):
        self.edited = kwargs


class FakeBot:
    user = type("U", (), {"name": "Bot", "id": 1})()

    def __init__(self):
        self.guilds = [FakeGuild()]

    def get_guild(self, gid):
        return self.guilds[0] if int(gid) == GUILD else None

    def get_cog(self, _name):
        return None


def run():
    import api.dependencies as dep
    from api.server import create_app
    from fastapi.testclient import TestClient

    bot = FakeBot()
    dep.set_bot(bot)
    client = TestClient(create_app())
    base = f"/api/v1/servertools/{GUILD}"
    guild = bot.guilds[0]

    failures = []

    def check(name, ok, extra=""):
        if ok:
            print(f"  PASS  {name}")
        else:
            failures.append(f"{name} {extra}")
            print(f"  FAIL  {name} {extra}")

    # --- literal paths must win over the {id} routes ------------------
    r = client.get(f"{base}/roles/audit")
    check("roles/audit is not swallowed by roles/{id}",
          r.status_code == 200 and "summary" in r.json(), f"-> {r.status_code}")

    # --- the scan finds the planted problems --------------------------
    r = client.get(f"{base}/security-scan")
    kinds = {f["kind"] for f in r.json().get("findings", [])}
    check("scan reports the admin role", "admin_role" in kinds, str(kinds))
    check("scan reports the weak verification level",
          "verification_level" in kinds, str(kinds))
    check("scan scores below 100", r.json().get("score", 100) < 100)

    # --- strip admin keeps the other permissions ----------------------
    r = client.post(f"{base}/roles/900/strip-admin", json={})
    edited = guild.admin.edited
    kept = bool(edited) and edited["permissions"].kick_members
    dropped = bool(edited) and not edited["permissions"].administrator
    check("strip-admin removes only Administrator",
          r.status_code == 200 and dropped and kept, str(edited))

    # --- guard rails ---------------------------------------------------
    r = client.post(f"{base}/roles/902/strip-admin", json={})
    check("refuses a role above the bot", r.status_code == 400, f"-> {r.status_code}")

    r = client.delete(f"{base}/roles/1")
    check("refuses to delete @everyone", r.status_code == 400, f"-> {r.status_code}")

    r = client.delete(f"{base}/roles/903")
    check("refuses to delete a managed role", r.status_code == 400, f"-> {r.status_code}")

    r = client.delete(f"{base}/roles/999999")
    check("unknown role gives 404", r.status_code == 404, f"-> {r.status_code}")

    # --- cleanup only removes empty, unmanaged roles below the bot ----
    r = client.post(f"{base}/roles/cleanup-unused", json={})
    body = r.json()
    check("cleanup removes the empty role",
          body.get("removed") == ["Leer"], str(body))
    check("cleanup keeps the managed role", not guild.managed.deleted)
    check("cleanup keeps roles with members", not guild.admin.deleted)

    # --- verification level -------------------------------------------
    r = client.post(f"{base}/verification-level", json={"level": "medium"})
    check("verification level is applied",
          r.status_code == 200
          and guild.edited
          and guild.edited["verification_level"] == discord.VerificationLevel.medium,
          str(guild.edited))

    r = client.post(f"{base}/verification-level", json={"level": "nonsense"})
    check("invalid verification level is rejected",
          r.status_code == 400, f"-> {r.status_code}")

    # --- slowmode -------------------------------------------------------
    r = client.post(f"{base}/channels/800/slowmode", json={"seconds": 30})
    check("slowmode is applied",
          r.status_code == 200 and guild.channel.slowmode_delay == 30,
          str(guild.channel.slowmode_delay))

    r = client.post(f"{base}/channels/800/slowmode", json={"seconds": 99999})
    check("slowmode is capped at Discord's maximum",
          guild.channel.slowmode_delay == 21600, str(guild.channel.slowmode_delay))

    r = client.post(f"{base}/channels/800/slowmode", json={"seconds": "abc"})
    check("non-numeric slowmode is rejected", r.status_code == 400, f"-> {r.status_code}")

    # --- invites ---------------------------------------------------------
    r = client.delete(f"{base}/invites/abc123")
    check("invite is revoked", r.status_code == 200 and guild.invite.revoked)

    r = client.delete(f"{base}/invites/doesnotexist")
    check("unknown invite gives 404", r.status_code == 404, f"-> {r.status_code}")

    # --- lockdown ---------------------------------------------------------
    r = client.post(f"{base}/lockdown", json={"lock": True})
    ow = guild.channel.overwrites.get(guild.default_role)
    check("lockdown blocks sending",
          r.status_code == 200 and ow and ow.send_messages is False, str(ow))

    r = client.post(f"{base}/lockdown", json={"lock": False})
    ow = guild.channel.overwrites.get(guild.default_role)
    check("unlock restores inherit (not an explicit allow)",
          ow is not None and ow.send_messages is None, str(ow))

    # --- unknown guild ----------------------------------------------------
    r = client.get(f"/api/v1/servertools/999999/overview")
    check("unknown guild gives 404", r.status_code == 404, f"-> {r.status_code}")

    print(f"\n{len(failures)} failures")
    for line in failures:
        print(f"   {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        os.makedirs(os.path.join(tmp, "db"), exist_ok=True)
        os.makedirs(os.path.join(tmp, "jsondb"), exist_ok=True)
        os.chdir(tmp)
        sys.exit(run())
