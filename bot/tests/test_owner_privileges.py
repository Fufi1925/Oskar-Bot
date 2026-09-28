"""Persistence and isolation of per-OWNER_IDS special bypasses."""

import asyncio
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))


async def run() -> int:
    from utils import dashboard_roles as roles

    failures = []

    def check(name, condition):
        print(f"  {'PASS' if condition else 'FAIL'}  {name}")
        if not condition:
            failures.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        roles.DB_PATH = os.path.join(tmp, "admin_config.db")
        roles.configured_owner_ids = lambda: {"111111111111111111", "222222222222222222"}
        roles._loaded = False
        roles._owner_privilege_cache.clear()
        await roles.load(force=True)

        defaults = roles.owner_privileges("111111111111111111")
        check("legacy owners retain every bypass until configured", all(defaults.values()))
        check(
            "non-owners never inherit owner bypasses",
            not any(roles.owner_privileges("333333333333333333").values()),
        )

        saved = await roles.set_owner_privileges(
            "222222222222222222",
            {"guild_owner_bypass": True, "premium_bypass": False},
            updated_by="111111111111111111",
        )
        check("one owner can configure another owner", saved["guild_owner_bypass"])
        check("individual bypasses can be disabled", not saved["premium_bypass"])

        roles._owner_privilege_cache.clear()
        roles._loaded = False
        await roles.load(force=True)
        reloaded = roles.owner_privileges("222222222222222222")
        check("owner bypasses survive a reload", reloaded == saved)

        try:
            await roles.set_owner_privileges(
                "111111111111111111",
                {"premium_bypass": True},
                updated_by="333333333333333333",
            )
            denied = False
        except PermissionError:
            denied = True
        check("non-owners cannot edit owner bypasses", denied)

    print(f"\n{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
