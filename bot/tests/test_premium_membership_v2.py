"""Focused regression checks for account Premium and three fixed guild slots."""
from __future__ import annotations
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils import premium_membership as membership  # noqa: E402


def main() -> int:
    original = membership.DB_PATH
    failures: list[str] = []
    def check(label: str, condition: bool) -> None:
        print(("  ok   " if condition else "  FAIL ") + label)
        if not condition: failures.append(label)
    try:
        with tempfile.TemporaryDirectory() as directory:
            membership.DB_PATH = os.path.join(directory, "premium-v2.db")
            check("new account starts without Premium", not membership.account_status("42")["premium"])
            request = membership.request_purchase("42", 90)
            check("purchase request is pending", request["status"] == "pending")
            check("only one pending request per account", membership.request_purchase("42", 365)["already"])
            account = membership.decide_request(request["id"], True, "admin")
            check("approval activates the requested package", account["premium"] and account["duration_days"] == 90)
            try:
                membership.request_purchase("42", 30)
                active_request_blocked = False
            except ValueError:
                active_request_blocked = True
            check("active accounts cannot open another purchase request", active_request_blocked)
            for guild_id in (101, 102, 103): membership.assign_slot("42", guild_id)
            check("exactly three slots are occupied", len(membership.account_status("42")["slots"]) == 3)
            try:
                membership.assign_slot("42", 104)
                fourth_blocked = False
            except ValueError:
                fourth_blocked = True
            check("a fourth slot is rejected", fourth_blocked)
            try:
                membership.assign_slot("99", 101)
                fixed = False
            except ValueError:
                fixed = True
            check("an assigned guild cannot move to another account", fixed)
            with sqlite3.connect(membership.DB_PATH) as db:
                db.execute("UPDATE premium_accounts SET expires_at=? WHERE user_id='42'", (int(time.time()) - 1,))
            frozen = membership.guild_status(101)
            check("keep mode continues at runtime after expiry", frozen["runtime"] and frozen["frozen"])
            check("expired keep mode is not configurable", not frozen["configurable"])
            membership.set_expiry_action(101, "disable")
            check("disable mode stops runtime without deleting the slot", not membership.guild_status(101)["runtime"])
            direct = membership.grant_server(200, "777", 12, "admin")
            check("admin can directly grant a server custom days", direct["active"] and direct["duration_days"] == 12)
            check("server owner gets a grant notice", membership.pending_server_notice("777")["kind"] == "granted")
            revoked = membership.revoke_server(200, delete_settings=False, owner_user_id="777")
            check("admin can revoke while keeping settings", revoked["revoked"] and not revoked["settings_deleted"])
            permanent = membership.grant_custom("99", None)
            check("admin can grant lifetime account Premium", permanent["premium"] and permanent["lifetime"])
    finally:
        membership.DB_PATH = original
    print(f"\n{len(failures)} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
