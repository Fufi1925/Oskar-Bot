"""
Full server configuration export and import.

Every module stores its settings in its own SQLite table keyed by guild_id.
This walks all of them at runtime instead of keeping a hardcoded list, so
tables added by future cogs are picked up automatically.

Export produces a single JSON file containing every row belonging to one
guild. Import writes it back, remapping nothing — it is meant for restoring
the same server or cloning a setup onto another one.

What is deliberately NOT exported:
  * per-user data (XP, warnings, ticket counts, invite stats) — that is
    history, not configuration, and copying it to another server is wrong
  * open tickets and log entries
  * the global blacklist and dashboard roles, which are not guild settings
"""

from __future__ import annotations

import glob
import json
import os
import time
from typing import Any

import aiosqlite

SCHEMA_VERSION = 1

# Tables holding user history rather than configuration. Skipped on export
# so a config file stays portable between servers.
USER_DATA_TABLES = {
    # The leveling system's XP. `user_xp` is the pre-rewrite table, kept
    # here so an old backup still round-trips; `levels` is the live one.
    "levels",
    "user_xp",
    "warns",
    "warn_log",
    "open_tickets",
    "user_ticket_counts",
    "verification_logs",
    # Per-member role assignments, not a server setting.
    "custom_roles",
}

# NOTE: `np` (the no-prefix allow list) used to be treated as user data and
# was therefore missing from every backup — even though it is configured on
# the dashboard under /noprefix and is pure configuration. Restoring a backup
# silently dropped everyone's no-prefix access.

# Tables that are global, not per guild.
GLOBAL_TABLES = {
    "user_blacklist",
    "guild_blacklist",
    "dashboard_role_assignments",
    "dashboard_owners",
    "admin_features",
    "admin_feature_rollout",
    "admin_feature_meta",
    "admin_audit_log",
    "notification_history",
    "admin_approval_queue",
    "bot_settings",
    "config",
    "premium_guilds",
    "scheduled_announcements",
}

# Friendly names so the dashboard can show what a file contains.
MODULE_LABELS = {
    "prefixes": "Command prefix",
    "welcome": "Welcome messages",
    "automod": "Automod",
    "automod_config": "Automod rules",
    "automod_punishments": "Automod punishments",
    "automod_ignored": "Automod exceptions",
    "automod_logging": "Automod log channel",
    "antinuke": "Anti-nuke",
    "whitelisted_users": "Anti-nuke whitelist",
    "limit_settings": "Anti-nuke limits",
    "punishment": "Anti-nuke punishment",
    "leveling_settings": "Leveling",
    "level_rewards": "Level rewards",
    "level_multipliers": "XP multipliers",
    "level_excluded": "Leveling exceptions",
    "verification_config": "Verification",
    "vanity_roles": "Vanity roles",
    "autorole": "Auto roles",
    "autoreact": "Auto reactions",
    "vcroles": "Voice roles",
    "roles": "Custom roles",
    "nickname_rules": "Nickname rules",
    "np_roles": "No-prefix roles",
    "guild_extra_settings": "Extra settings",
    "guild_configs": "Ticket system",
    "ticket_categories": "Ticket categories",
    "logging": "Logging",
    "j2c": "Join to create",
}


async def _tables_with_guild_id(db: aiosqlite.Connection) -> dict[str, list[str]]:
    """Return {table: columns} for every table that has a guild_id column."""
    found: dict[str, list[str]] = {}

    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ) as cursor:
        names = [row[0] for row in await cursor.fetchall()]

    for name in names:
        try:
            async with db.execute(f"PRAGMA table_info([{name}])") as cursor:
                columns = [row[1] for row in await cursor.fetchall()]
        except Exception:
            continue
        if "guild_id" in columns:
            found[name] = columns

    return found


async def export_guild(guild_id: int, *, include_user_data: bool = False) -> dict[str, Any]:
    """Collect every configuration row belonging to one guild."""
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": int(time.time()),
        "guild_id": str(guild_id),
        "include_user_data": include_user_data,
        "databases": {},
    }

    modules: list[str] = []
    total_rows = 0

    for db_path in iter_database_files():
        db_name = db_key(db_path)
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                tables = await _tables_with_guild_id(db)

                exported: dict[str, list[dict]] = {}
                for table, _columns in tables.items():
                    if table in GLOBAL_TABLES:
                        continue
                    if table in USER_DATA_TABLES and not include_user_data:
                        continue

                    try:
                        async with db.execute(
                            f"SELECT * FROM [{table}] WHERE guild_id = ?", (guild_id,)
                        ) as cursor:
                            rows = [dict(row) for row in await cursor.fetchall()]
                    except Exception as exc:
                        print(f"[config_transfer] skip {db_name}.{table}: {exc}")
                        continue

                    if rows:
                        exported[table] = rows
                        total_rows += len(rows)
                        label = MODULE_LABELS.get(table)
                        if label and label not in modules:
                            modules.append(label)

                if exported:
                    payload["databases"][db_name] = exported
        except Exception as exc:
            print(f"[config_transfer] cannot read {db_path}: {exc}")

    payload["summary"] = {
        "modules": sorted(modules),
        "table_count": sum(len(t) for t in payload["databases"].values()),
        "row_count": total_rows,
    }
    return payload


# Configuration that does not live in SQLite. These were missing from every
# backup, so birthdays and join-DM templates were silently lost on a restore.
JSON_CONFIG_FILES = (
    "jsondb/birthdays.json",
    "jsondb/joindm_messages.json",
    "jsondb/birthday_logs.json",
    "ignore.json",
    "channels.json",
)

# Not every cog puts its database in db/. Reaction roles use rr.db and
# join-to-create uses j2c_data.db, both in the working directory, so a
# backup that only globbed db/*.db silently skipped them.
EXTRA_DB_FILES = (
    "rr.db",
    "j2c_data.db",
)


def iter_database_files() -> list[str]:
    """Every SQLite file that belongs in a backup, wherever it lives."""
    found = sorted(glob.glob("db/*.db"))
    for name in EXTRA_DB_FILES:
        if os.path.exists(name) and name not in found:
            found.append(name)
    return found


def db_key(path: str) -> str:
    """
    Stable name for a database inside a backup.

    Files in db/ keep their bare name for backwards compatibility with
    backups written before the extra locations were covered.
    """
    directory, base = os.path.split(path)
    return base if directory in ("", "db") else path.replace("/", "__")


def db_path_from_key(key: str) -> str:
    """Reverse of db_key()."""
    if "__" in key:
        return key.replace("__", "/")
    return key if key in EXTRA_DB_FILES else os.path.join("db", key)


def _collect_json_files() -> dict[str, Any]:
    """Read the JSON config files that belong in a backup."""
    out: dict[str, Any] = {}
    for name in JSON_CONFIG_FILES:
        if not os.path.exists(name):
            continue
        try:
            with open(name, encoding="utf-8") as handle:
                out[name] = json.load(handle)
        except Exception as exc:
            print(f"[config_transfer] cannot read {name}: {exc}")
    return out


def _restore_json_files(files: dict[str, Any], *, replace: bool) -> dict[str, int]:
    """
    Write JSON config files back.

    With replace=False the existing content is kept and only missing
    top-level keys are added, mirroring how the SQLite side merges.
    """
    written: dict[str, int] = {}
    for name, payload in (files or {}).items():
        if name not in JSON_CONFIG_FILES:
            continue  # never write a path that came from the file itself
        try:
            target = payload
            if not replace and os.path.exists(name):
                try:
                    with open(name, encoding="utf-8") as handle:
                        current = json.load(handle)
                    if isinstance(current, dict) and isinstance(payload, dict):
                        merged = dict(payload)
                        merged.update(current)
                        target = merged
                except Exception:
                    target = payload

            os.makedirs(os.path.dirname(name) or ".", exist_ok=True)
            with open(name, "w", encoding="utf-8") as handle:
                json.dump(target, handle, indent=4, ensure_ascii=False)
            written[name] = len(target) if hasattr(target, "__len__") else 1
        except Exception as exc:
            print(f"[config_transfer] cannot write {name}: {exc}")
    return written


async def export_everything(*, include_user_data: bool = False) -> dict[str, Any]:
    """
    Collect EVERYTHING: every guild, every module, plus the global/admin
    tables (dashboard team & roles, feature flags, bot settings, blacklist,
    premium, announcements).

    This is the "one file for the whole bot" backup. Unlike export_guild()
    it does not filter by guild_id and it deliberately DOES include the
    global tables, because for a full restore you want them back too.
    """
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "exported_at": int(time.time()),
        "scope": "global",
        "include_user_data": include_user_data,
        "databases": {},
    }

    modules: list[str] = []
    total_rows = 0
    guild_ids: set[str] = set()
    global_tables_found: list[str] = []

    for db_path in iter_database_files():
        db_name = db_key(db_path)
        try:
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row

                async with db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ) as cursor:
                    names = [row[0] for row in await cursor.fetchall()]

                exported: dict[str, list[dict]] = {}
                for table in names:
                    # Per-user history is history, not configuration.
                    if table in USER_DATA_TABLES and not include_user_data:
                        continue

                    try:
                        async with db.execute(f"SELECT * FROM [{table}]") as cursor:
                            rows = [dict(row) for row in await cursor.fetchall()]
                    except Exception as exc:
                        print(f"[config_transfer] skip {db_name}.{table}: {exc}")
                        continue

                    if not rows:
                        continue

                    exported[table] = rows
                    total_rows += len(rows)

                    if table in GLOBAL_TABLES:
                        global_tables_found.append(table)
                    else:
                        label = MODULE_LABELS.get(table)
                        if label and label not in modules:
                            modules.append(label)

                    # Track how many servers are covered.
                    for row in rows:
                        gid = row.get("guild_id")
                        if gid not in (None, ""):
                            guild_ids.add(str(gid))

                if exported:
                    payload["databases"][db_name] = exported
        except Exception as exc:
            print(f"[config_transfer] cannot read {db_path}: {exc}")

    # Not everything lives in SQLite.
    payload["json_files"] = _collect_json_files()
    if payload["json_files"]:
        modules.append("Birthdays & join DMs")

    payload["summary"] = {
        "modules": sorted(modules),
        "global_tables": sorted(set(global_tables_found)),
        "guild_count": len(guild_ids),
        "guild_ids": sorted(guild_ids),
        "table_count": sum(len(t) for t in payload["databases"].values()),
        "row_count": total_rows,
        "json_files": sorted(payload["json_files"]),
    }
    return payload


async def preview_global_import(data: dict[str, Any]) -> dict[str, Any]:
    """Describe what a global import would do, without writing anything."""
    if not isinstance(data, dict):
        raise ValueError("The file does not contain a configuration object.")
    if "databases" not in data:
        raise ValueError("Missing 'databases' — is this a backup file?")

    version = int(data.get("schema_version", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"This file was written by a newer version (schema {version}). "
            "Update the bot first."
        )

    modules: list[str] = []
    global_tables: list[str] = []
    guild_ids: set[str] = set()
    tables = 0
    rows = 0
    missing: list[str] = []

    for db_name, table_map in data["databases"].items():
        exists = os.path.exists(db_path_from_key(db_name))
        for table, entries in table_map.items():
            tables += 1
            rows += len(entries)
            if table in GLOBAL_TABLES:
                global_tables.append(table)
            else:
                label = MODULE_LABELS.get(table)
                if label and label not in modules:
                    modules.append(label)
            for entry in entries:
                gid = entry.get("guild_id")
                if gid not in (None, ""):
                    guild_ids.add(str(gid))
            if not exists:
                missing.append(f"{db_name}.{table}")

    json_files = sorted(
        n for n in (data.get("json_files") or {}) if n in JSON_CONFIG_FILES
    )
    if json_files:
        modules.append("Birthdays & join DMs")

    return {
        "scope": data.get("scope", "guild"),
        "exported_at": data.get("exported_at"),
        "includes_user_data": bool(data.get("include_user_data")),
        "modules": sorted(modules),
        "global_tables": sorted(set(global_tables)),
        "guild_count": len(guild_ids),
        "table_count": tables,
        "row_count": rows,
        "json_files": json_files,
        "missing_databases": sorted(set(missing)),
    }


async def import_everything(
    data: dict[str, Any],
    *,
    replace: bool = True,
    include_global: bool = True,
) -> dict[str, Any]:
    """
    Restore a full-bot backup produced by export_everything().

    replace=True wipes each imported table before writing, which is what
    "restore this backup" means. replace=False merges rows in.

    include_global=False keeps the current dashboard team, feature flags and
    bot settings untouched and only restores the per-server configuration —
    useful when importing another instance's servers.
    """
    await preview_global_import(data)

    applied: dict[str, int] = {}
    skipped: list[str] = []

    for db_name, table_map in data["databases"].items():
        db_path = db_path_from_key(db_name)

        # Recreating a whole database file is out of scope; a missing file
        # means the owning cog never ran here.
        if not os.path.exists(db_path):
            skipped.append(f"{db_name} (no such database)")
            continue

        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ) as cursor:
                    existing = {row[0] for row in await cursor.fetchall()}

                for table, entries in table_map.items():
                    if table not in existing:
                        skipped.append(f"{db_name}.{table} (table missing)")
                        continue
                    if table in GLOBAL_TABLES and not include_global:
                        skipped.append(f"{db_name}.{table} (global, skipped)")
                        continue
                    if not entries:
                        continue

                    try:
                        async with db.execute(f"PRAGMA table_info([{table}])") as cursor:
                            columns = [row[1] for row in await cursor.fetchall()]
                    except Exception as exc:
                        skipped.append(f"{db_name}.{table} ({exc})")
                        continue

                    if replace:
                        try:
                            await db.execute(f"DELETE FROM [{table}]")
                        except Exception as exc:
                            skipped.append(f"{db_name}.{table} (clear failed: {exc})")
                            continue

                    written = 0
                    for entry in entries:
                        # Keep only columns this table actually has, so an
                        # older backup still imports after a schema change.
                        usable = {k: v for k, v in entry.items() if k in columns}
                        if not usable:
                            continue

                        names = ", ".join(f"[{c}]" for c in usable)
                        marks = ", ".join("?" for _ in usable)
                        try:
                            await db.execute(
                                f"INSERT OR REPLACE INTO [{table}] ({names}) "
                                f"VALUES ({marks})",
                                tuple(usable.values()),
                            )
                            written += 1
                        except Exception as exc:
                            print(f"[config_transfer] row failed in {table}: {exc}")

                    await db.commit()
                    if written:
                        applied[f"{db_name}.{table}"] = written
        except Exception as exc:
            skipped.append(f"{db_name} ({exc})")

    json_written = _restore_json_files(
        data.get("json_files") or {}, replace=replace
    )

    return {
        "scope": "global",
        "applied": applied,
        "tables_written": len(applied),
        "rows_written": sum(applied.values()),
        "json_files_written": sorted(json_written),
        "skipped": skipped,
    }


async def preview_import(data: dict[str, Any]) -> dict[str, Any]:
    """
    Describe what an import would do, without writing anything.

    Used by the dashboard to show a confirmation step.
    """
    if not isinstance(data, dict):
        raise ValueError("The file does not contain a configuration object.")
    if "databases" not in data:
        raise ValueError("Missing 'databases' — is this a config export?")

    version = int(data.get("schema_version", 0))
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"This file was written by a newer version (schema {version}). Update the bot first."
        )

    modules: list[str] = []
    tables = 0
    rows = 0
    unknown: list[str] = []

    for db_name, table_map in data["databases"].items():
        db_path = db_path_from_key(db_name)
        exists = os.path.exists(db_path)

        for table, entries in table_map.items():
            tables += 1
            rows += len(entries)
            label = MODULE_LABELS.get(table)
            if label and label not in modules:
                modules.append(label)
            if not exists:
                unknown.append(f"{db_name}.{table}")

    return {
        "source_guild_id": data.get("guild_id"),
        "exported_at": data.get("exported_at"),
        "includes_user_data": bool(data.get("include_user_data")),
        "modules": sorted(modules),
        "table_count": tables,
        "row_count": rows,
        "missing_databases": sorted(set(unknown)),
    }


async def import_guild(
    guild_id: int,
    data: dict[str, Any],
    *,
    replace: bool = True,
) -> dict[str, Any]:
    """
    Write a configuration export back into the databases.

    guild_id is taken from the target, not the file, so a config can be
    cloned onto a different server. With replace=True the guild's existing
    rows in each imported table are removed first, which is what "restore
    this backup" means; with replace=False rows are merged in.
    """
    await preview_import(data)  # validates and raises on nonsense

    applied: dict[str, int] = {}
    skipped: list[str] = []

    for db_name, table_map in data["databases"].items():
        db_path = db_path_from_key(db_name)
        if not os.path.exists(db_path):
            skipped.append(f"{db_name} (no such database)")
            continue

        try:
            async with aiosqlite.connect(db_path) as db:
                existing = await _tables_with_guild_id(db)

                for table, entries in table_map.items():
                    if table not in existing:
                        skipped.append(f"{db_name}.{table} (table missing)")
                        continue
                    if table in GLOBAL_TABLES:
                        skipped.append(f"{db_name}.{table} (not a guild setting)")
                        continue
                    if not entries:
                        continue

                    columns = existing[table]

                    if replace:
                        await db.execute(
                            f"DELETE FROM [{table}] WHERE guild_id = ?", (guild_id,)
                        )

                    written = 0
                    for entry in entries:
                        # Only keep columns this table actually has, so an
                        # older export still imports after a schema change.
                        usable = {k: v for k, v in entry.items() if k in columns}
                        if not usable:
                            continue
                        usable["guild_id"] = guild_id

                        names = ", ".join(f"[{c}]" for c in usable)
                        marks = ", ".join("?" for _ in usable)
                        try:
                            await db.execute(
                                f"INSERT OR REPLACE INTO [{table}] ({names}) VALUES ({marks})",
                                tuple(usable.values()),
                            )
                            written += 1
                        except Exception as exc:
                            print(f"[config_transfer] row failed in {table}: {exc}")

                    await db.commit()
                    if written:
                        applied[f"{db_name}.{table}"] = written
        except Exception as exc:
            skipped.append(f"{db_name} ({exc})")

    return {
        "guild_id": str(guild_id),
        "applied": applied,
        "tables_written": len(applied),
        "rows_written": sum(applied.values()),
        "skipped": skipped,
    }
