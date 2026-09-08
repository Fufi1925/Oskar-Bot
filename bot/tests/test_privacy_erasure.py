#!/usr/bin/env python3
"""Real SQLite flow for reviewed account erasure and its exclusions."""

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile

BOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("privacy_erasure_isolated", BOT / "utils/privacy_erasure.py")
privacy = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(privacy)

failures = []
def check(name, ok, detail=""):
    print(f"  {'ok  ' if ok else 'FAIL'} {name} {detail if not ok else ''}")
    if not ok: failures.append(name)

def make(path, statements):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with sqlite3.connect(path) as conn:
        for sql, params in statements:
            conn.execute(sql, params)

def one(path, sql, params=()):
    with sqlite3.connect(path) as conn:
        return conn.execute(sql, params).fetchone()

old = os.getcwd()
with tempfile.TemporaryDirectory() as tmp:
    os.chdir(tmp)
    os.environ["PRIVACY_HASH_PEPPER"] = "test-only-pepper"
    uid, name = "1303627964734246944", "Fufi"

    make("db/admin_config.db", [
        ("CREATE TABLE dashboard_logins(user_id TEXT, username TEXT)", ()),
        ("CREATE TABLE dashboard_bans(user_id TEXT, reason TEXT)", ()),
        ("INSERT INTO dashboard_logins VALUES(?,?)", (uid, name)),
        ("INSERT INTO dashboard_bans VALUES(?,?)", (uid, "security")),
    ])
    make("db/leveling.db", [
        ("CREATE TABLE levels(user_id INTEGER, xp INTEGER, messages INTEGER)", ()),
        ("INSERT INTO levels VALUES(?,?,?)", (int(uid), 900, 42)),
    ])
    make("db/cookie_consent.db", [
        ("CREATE TABLE cookie_consents(user_id TEXT, user_name TEXT)", ()),
        ("INSERT INTO cookie_consents VALUES(?,?)", (uid, name)),
    ])
    make("db/account_preferences.db", [
        ("CREATE TABLE account_preferences(user_id TEXT PRIMARY KEY,language TEXT,theme TEXT,timezone TEXT,number_format TEXT,date_format TEXT,start_page TEXT,updated_at INTEGER)", ()),
        ("INSERT INTO account_preferences VALUES(?,?,?,?,?,?,?,?)", (uid, "en", "light", "UTC", "en-GB", "iso", "/konto", 1)),
    ])
    make("db/web_apply.db", [
        ("CREATE TABLE web_applications(user_id INTEGER PRIMARY KEY,user_name TEXT,avatar TEXT,answers TEXT)", ()),
        ("INSERT INTO web_applications VALUES(?,?,?,?)", (int(uid), name, "avatar", json.dumps(["private"]))),
    ])
    make("db/premium.db", [
        ("CREATE TABLE premium_keys(redeemed_by TEXT,revoked INTEGER)", ()),
        ("INSERT INTO premium_keys VALUES(?,0)", (uid,)),
    ])
    make("db/premium_trial.db", [
        ("CREATE TABLE premium_trials(user_id TEXT PRIMARY KEY,guild_id TEXT,reset_by TEXT)", ()),
        ("INSERT INTO premium_trials VALUES(?,?,?)", (uid, "1", "admin")),
    ])

    request = privacy.create_request(uid, name)
    check("request starts in undo window", request["status"] == "undo")
    check("wrong account cannot cancel", not privacy.cancel(request["id"], "999"))
    check("the owner can cancel within ten seconds", privacy.cancel(request["id"], uid))

    request = privacy.create_request(uid, name)
    with privacy._connect() as conn:
        conn.execute("UPDATE erasure_requests SET status='pending' WHERE id=?", (request["id"],))
    result = privacy.approve(request["id"], "owner")
    check("approved request completes", result and result["status"] == "completed")
    check("dashboard profile is deleted", one("db/admin_config.db", "SELECT COUNT(*) FROM dashboard_logins")[0] == 0)
    check("cookie link is deleted", one("db/cookie_consent.db", "SELECT COUNT(*) FROM cookie_consents")[0] == 0)
    check("personal preferences are deleted", one("db/account_preferences.db", "SELECT COUNT(*) FROM account_preferences")[0] == 0)
    app = one("db/web_apply.db", "SELECT user_id,user_name,avatar,answers FROM web_applications")
    check("application is retained without personal fields", app[0] != int(uid) and app[1:] == (privacy.ANON_LABEL, "", "[]"), str(app))
    premium = one("db/premium.db", "SELECT redeemed_by,revoked FROM premium_keys")
    check("premium is revoked and pseudonymised", premium[1] == 1 and premium[0] != uid)
    check("a deleted account cannot repeat its trial", privacy.trial_already_used(uid))

    # Explicit exclusions requested by the product owner.
    check("XP and message activity remain", one("db/leveling.db", "SELECT xp,messages FROM levels WHERE user_id=?", (int(uid),)) == (900, 42))
    check("security bans remain", one("db/admin_config.db", "SELECT reason FROM dashboard_bans WHERE user_id=?", (uid,)) == ("security",))
    check("completed audit no longer stores raw Discord id", uid not in json.dumps(result))

os.chdir(old)
route_src = (BOT / "api/routes/privacy.py").read_text(encoding="utf-8")
server_src = (BOT / "api/server.py").read_text(encoding="utf-8")
proxy_src = (BOT.parent / "dashboard/app/api/bot/[...path]/route.ts").read_text(encoding="utf-8")
admin_src = (BOT.parent / "dashboard/components/dashboard/admin-content.tsx").read_text(encoding="utf-8")
check("Fufi receives one Discord DM after the undo window", "store.FUFI_ID" in route_src and "pending_notifications" in route_src)
check("restart recovery worker exists", "privacy_worker" in server_src and "privacy.notify_pending" in server_src)
check("only global admins may decide", 'scope === "privacy"' in proxy_src and "Owner access required" in proxy_src)
check("admin dashboard contains the review tab", 'label: "Datenlöschung"' in admin_src and "<PrivacyErasureAdmin />" in admin_src)
print(f"\n{len(failures)} failures")
sys.exit(1 if failures else 0)
