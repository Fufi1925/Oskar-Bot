"""
Database schema guard.

Every cog creates its own tables the first time it runs. The API, however,
reads those same tables — and on a fresh deployment it usually gets there
first. The result was a dashboard full of 500s:

    sqlite3.OperationalError: no such table: automod

This module creates the tables the API reads, using the exact same schema the
cogs use. `CREATE TABLE IF NOT EXISTS` makes it a no-op once a cog has already
created them, so nothing is overwritten and no data is touched.

Called once on API startup.
"""

from __future__ import annotations

import os

import aiosqlite

# db file -> list of CREATE statements
SCHEMA: dict[str, tuple[str, ...]] = {
    "db/automod.db": (
        """CREATE TABLE IF NOT EXISTS automod (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS automod_punishments (
            guild_id INTEGER,
            event TEXT,
            punishment TEXT,
            PRIMARY KEY (guild_id, event)
        )""",
        """CREATE TABLE IF NOT EXISTS automod_ignored (
            guild_id INTEGER,
            type TEXT,
            id INTEGER
        )""",
        """CREATE TABLE IF NOT EXISTS automod_config (
            guild_id INTEGER,
            event TEXT,
            enabled INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, event)
        )""",
        """CREATE TABLE IF NOT EXISTS automod_logging (
            guild_id INTEGER PRIMARY KEY,
            log_channel INTEGER
        )""",
    ),
    "db/ticket.db": (
        """CREATE TABLE IF NOT EXISTS guild_configs (
            guild_id INTEGER PRIMARY KEY,
            panel_channel_id INTEGER,
            logging_channel_id INTEGER,
            panel_message_id INTEGER,
            panel_type TEXT,
            embed_title TEXT,
            embed_description TEXT,
            embed_color INTEGER,
            embed_image_url TEXT,
            embed_thumbnail_url TEXT,
            closed_category_id INTEGER
        )""",
        """CREATE TABLE IF NOT EXISTS ticket_categories (
            category_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT NOT NULL,
            emoji TEXT,
            notified_roles TEXT,
            button_style INTEGER,
            discord_category_id INTEGER
        )""",
        """CREATE TABLE IF NOT EXISTS open_tickets (
            channel_id INTEGER PRIMARY KEY,
            ticket_number INTEGER,
            guild_id INTEGER,
            creator_id INTEGER NOT NULL,
            category_db_id INTEGER,
            created_at TEXT NOT NULL,
            closed_by_id INTEGER,
            closed_at TEXT,
            is_locked BOOLEAN DEFAULT FALSE,
            is_claimed BOOLEAN DEFAULT FALSE,
            claimed_by_id INTEGER
        )""",
        """CREATE TABLE IF NOT EXISTS user_ticket_counts (
            guild_id INTEGER,
            user_id INTEGER,
            ticket_count INTEGER DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )""",
    ),
    "db/leveling.db": (
        """CREATE TABLE IF NOT EXISTS leveling_settings (
            guild_id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 0,
            channel_id INTEGER,
            level_message TEXT DEFAULT 'Congratulations {user}! You have reached level {level}!',
            embed_color INTEGER DEFAULT 0,
            level_image TEXT,
            thumbnail_enabled INTEGER DEFAULT 1,
            xp_per_message INTEGER DEFAULT 20,
            min_xp INTEGER DEFAULT 15,
            max_xp INTEGER DEFAULT 25,
            cooldown_seconds INTEGER DEFAULT 60,
            dm_level_up INTEGER DEFAULT 0
        )""",
        """CREATE TABLE IF NOT EXISTS user_xp (
            guild_id INTEGER,
            user_id INTEGER,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 0,
            messages INTEGER DEFAULT 0,
            last_message REAL DEFAULT 0,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS level_rewards (
            guild_id INTEGER,
            level INTEGER,
            role_id INTEGER,
            PRIMARY KEY (guild_id, level)
        )""",
    ),
    "db/welcome.db": (
        """CREATE TABLE IF NOT EXISTS welcome (
            guild_id INTEGER PRIMARY KEY,
            welcome_type TEXT,
            welcome_message TEXT,
            channel_id INTEGER,
            embed_data TEXT,
            auto_delete_duration INTEGER
        )""",
    ),
    "db/anti.db": (
        """CREATE TABLE IF NOT EXISTS antinuke (
            guild_id INTEGER PRIMARY KEY,
            status BOOLEAN
        )""",
        """CREATE TABLE IF NOT EXISTS whitelisted_users (
            guild_id INTEGER,
            user_id INTEGER,
            ban BOOLEAN, kick BOOLEAN, prune BOOLEAN, botadd BOOLEAN,
            serverup BOOLEAN, memup BOOLEAN, chcr BOOLEAN, chdl BOOLEAN,
            chup BOOLEAN, rlcr BOOLEAN, rlup BOOLEAN, rldl BOOLEAN,
            meneve BOOLEAN, mngweb BOOLEAN, mngstemo BOOLEAN,
            PRIMARY KEY (guild_id, user_id)
        )""",
        """CREATE TABLE IF NOT EXISTS limit_settings (
            guild_id INTEGER,
            action_type TEXT,
            action_limit INTEGER,
            time_window INTEGER,
            PRIMARY KEY (guild_id, action_type)
        )""",
        """CREATE TABLE IF NOT EXISTS punishment (
            guild_id INTEGER PRIMARY KEY,
            punishment TEXT
        )""",
    ),
    "db/verification.db": (
        # The channel and the role were NOT NULL, which made it
        # impossible to save any other setting before picking them --
        # the insert failed outright. They are optional now; the API
        # refuses to *switch the feature on* without them instead.
        """CREATE TABLE IF NOT EXISTS verification_config (
            guild_id INTEGER PRIMARY KEY,
            verification_channel_id INTEGER,
            verified_role_id INTEGER,
            log_channel_id INTEGER,
            verification_method TEXT DEFAULT 'both',
            enabled BOOLEAN DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )""",
        """CREATE TABLE IF NOT EXISTS verification_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            verification_method TEXT NOT NULL,
            verified_at TEXT NOT NULL
        )""",
    ),
    "db/vanity.db": (
        """CREATE TABLE IF NOT EXISTS vanity_roles (
            guild_id INTEGER,
            vanity TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            log_channel_id INTEGER NOT NULL,
            current_status TEXT,
            PRIMARY KEY (guild_id, vanity)
        )""",
    ),
    "db/customrole.db": (
        # Column names come from the customrole cog; the API selects them by name.
        """CREATE TABLE IF NOT EXISTS roles (
            guild_id INTEGER PRIMARY KEY,
            staff TEXT,
            girl TEXT,
            vip TEXT,
            guest TEXT,
            frnd TEXT,
            reqrole INTEGER
        )""",
        # A named command per role: ">gamer @user" toggles it. This
        # declared (guild_id, user_id) at one point, which matches
        # nothing in the codebase -- the cog and the API both address
        # rows by name. Because schema_guard runs first and
        # CREATE TABLE IF NOT EXISTS is a no-op against an existing
        # table, every fresh deploy got the wrong shape and each
        # prefixed message raised "no such column: name".
        """CREATE TABLE IF NOT EXISTS custom_roles (
            guild_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, name)
        )""",
    ),
    "db/logging.db": (
        """CREATE TABLE IF NOT EXISTS logging (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            enabled INTEGER DEFAULT 0
        )""",
    ),
    "db/autorole.db": (
        """CREATE TABLE IF NOT EXISTS autorole (
            guild_id INTEGER PRIMARY KEY,
            bots TEXT NOT NULL DEFAULT '[]',
            humans TEXT NOT NULL DEFAULT '[]'
        )""",
    ),
    "db/autoreact.db": (
        """CREATE TABLE IF NOT EXISTS autoreact (
            guild_id INTEGER,
            trigger TEXT,
            emojis TEXT
        )""",
    ),
    "db/invc.db": (
        """CREATE TABLE IF NOT EXISTS vcroles (
            guild_id INTEGER PRIMARY KEY,
            role_id INTEGER,
            enabled INTEGER DEFAULT 0
        )""",
    ),
    "db/np.db": (
        """CREATE TABLE IF NOT EXISTS np (
            id INTEGER PRIMARY KEY,
            expiry_time TEXT
        )""",
        """CREATE TABLE IF NOT EXISTS np_roles (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            PRIMARY KEY (guild_id, role_id)
        )""",
    ),
    "db/nickname.db": (
        """CREATE TABLE IF NOT EXISTS nickname_rules (
            guild_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            prefix TEXT DEFAULT '',
            suffix TEXT DEFAULT '',
            enabled INTEGER DEFAULT 1,
            PRIMARY KEY (guild_id, role_id)
        )""",
    ),
    "db/settings.db": (
        """CREATE TABLE IF NOT EXISTS guild_extra_settings (
            guild_id INTEGER PRIMARY KEY,
            delete_command_messages INTEGER DEFAULT 0,
            mention_prefix_response INTEGER DEFAULT 1,
            same_voice_only INTEGER DEFAULT 1
        )""",
    ),
    "db/prefix.db": (
        """CREATE TABLE IF NOT EXISTS prefixes (
            guild_id INTEGER PRIMARY KEY,
            prefix TEXT NOT NULL
        )""",
    ),
    "db/block.db": (
        """CREATE TABLE IF NOT EXISTS user_blacklist (user_id TEXT PRIMARY KEY)""",
        """CREATE TABLE IF NOT EXISTS guild_blacklist (guild_id TEXT PRIMARY KEY)""",
    ),
    "db/admin_config.db": (
        # Who signed in to the dashboard, and who is locked out of it.
        """CREATE TABLE IF NOT EXISTS dashboard_logins (
            user_id TEXT PRIMARY KEY,
            username TEXT DEFAULT '',
            avatar TEXT DEFAULT '',
            first_seen INTEGER DEFAULT 0,
            last_seen INTEGER DEFAULT 0,
            login_count INTEGER DEFAULT 0,
            last_path TEXT DEFAULT ''
        )""",
        """CREATE TABLE IF NOT EXISTS dashboard_bans (
            user_id TEXT PRIMARY KEY,
            banned_by TEXT DEFAULT '',
            banned_at INTEGER DEFAULT 0,
            reason TEXT DEFAULT '',
            expires_at INTEGER DEFAULT 0
        )""",
    ),
    "db/j2c.db": (
        """CREATE TABLE IF NOT EXISTS j2c (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER,
            category_id INTEGER,
            name_template TEXT,
            user_limit INTEGER DEFAULT 0
        )""",
    ),
    "db/warn.db": (
        """CREATE TABLE IF NOT EXISTS warns (
            guild_id INTEGER,
            user_id INTEGER,
            warns INTEGER,
            PRIMARY KEY (guild_id, user_id)
        )""",
        # Who warned whom, when and why. Both the >warn command and the
        # dashboard write here through utils/warn_store.py -- they used to
        # keep separate SQL, which is why warnings issued in Discord showed
        # up without a reason.
        """CREATE TABLE IF NOT EXISTS warn_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            moderator_id INTEGER,
            reason TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            active INTEGER DEFAULT 1
        )""",
        """CREATE INDEX IF NOT EXISTS idx_warn_log_guild_user
            ON warn_log (guild_id, user_id, active)""",
    ),
    "db/greet_extras.db": (
        # The image toggle for welcome/leave and the goodbye message.
        # Deliberately not extra columns on db/welcome.db: that table is
        # read with a fixed SELECT order in two places, both unpacking
        # exactly six values, so a seventh column would silently shift
        # them.
        """CREATE TABLE IF NOT EXISTS greet_extras (
            guild_id INTEGER PRIMARY KEY,
            welcome_image_enabled INTEGER DEFAULT 1,
            welcome_image_url TEXT DEFAULT '',
            leave_enabled INTEGER DEFAULT 0,
            leave_channel_id INTEGER DEFAULT 0,
            leave_message TEXT DEFAULT '',
            leave_image_enabled INTEGER DEFAULT 1,
            leave_image_url TEXT DEFAULT ''
        )""",
    ),
    "db/user_lookup.db": (
        # Users banned from the bot entirely -- not just from commands.
        # The old user_blacklist only gated command invocations; it let
        # the dashboard login through and did not stop anyone from
        # inviting the bot. Entries here are mirrored into that table so
        # the existing blacklist_check() in every command keeps working.
        """CREATE TABLE IF NOT EXISTS bot_bans (
            user_id TEXT PRIMARY KEY,
            reason TEXT DEFAULT '',
            banned_by TEXT,
            banned_at INTEGER NOT NULL,
            note TEXT DEFAULT ''
        )""",
        # What a mass ban or owner warning actually achieved.
        """CREATE TABLE IF NOT EXISTS mass_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            actor TEXT,
            reason TEXT DEFAULT '',
            ok_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            detail TEXT DEFAULT '',
            created_at INTEGER NOT NULL
        )""",
        """CREATE INDEX IF NOT EXISTS idx_mass_actions_user
            ON mass_actions (user_id, created_at)""",
    ),
    "db/ticket_notify.db": (
        # Settings for the ticket DM notifications, per guild.
        """CREATE TABLE IF NOT EXISTS notify_settings (
            guild_id INTEGER PRIMARY KEY,
            user_dm_enabled INTEGER DEFAULT 0,
            staff_dm_enabled INTEGER DEFAULT 0,
            user_delay INTEGER DEFAULT 300,
            staff_delay INTEGER DEFAULT 300,
            user_cooldown INTEGER DEFAULT 3600,
            staff_cooldown INTEGER DEFAULT 3600,
            quiet_enabled INTEGER DEFAULT 0,
            quiet_start INTEGER DEFAULT 22,
            quiet_end INTEGER DEFAULT 8
        )""",
        # Who last wrote in which ticket, and what is still pending.
        """CREATE TABLE IF NOT EXISTS ticket_state (
            channel_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            creator_id INTEGER NOT NULL,
            last_user_msg INTEGER DEFAULT 0,
            last_staff_msg INTEGER DEFAULT 0,
            last_staff_id INTEGER,
            staff_has_written INTEGER DEFAULT 0,
            sleeping INTEGER DEFAULT 0,
            sleep_by INTEGER,
            pending_user INTEGER DEFAULT 0,
            pending_staff INTEGER DEFAULT 0
        )""",
        # Backs the cooldown: nobody gets a second DM for the same
        # ticket within the configured window.
        """CREATE TABLE IF NOT EXISTS notify_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL,
            target_id INTEGER NOT NULL,
            kind TEXT NOT NULL,
            sent_at INTEGER NOT NULL
        )""",
        """CREATE INDEX IF NOT EXISTS idx_notify_log_lookup
            ON notify_log (channel_id, target_id, kind, sent_at)""",
        """CREATE INDEX IF NOT EXISTS idx_state_pending
            ON ticket_state (pending_user, pending_staff)""",
    ),
    "db/timer.db": (
        # Running timers. Without this table a redeploy silently dropped
        # every timer -- the countdown lived only in a Python loop.
        """CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER,
            user_id INTEGER NOT NULL,
            title TEXT DEFAULT '',
            ends_at INTEGER NOT NULL,
            done INTEGER DEFAULT 0
        )""",
        """CREATE INDEX IF NOT EXISTS idx_timers_due
            ON timers (done, ends_at)""",
    ),
    "db/invite.db": (
        # The tracking endpoints store the invite log channel in a table
        # called "logging" inside invite.db (not to be confused with
        # logging.db, which belongs to the event logger).
        """CREATE TABLE IF NOT EXISTS logging (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER
        )""",
    ),
}


async def ensure_schema() -> dict[str, int]:
    """
    Create every table the API reads.

    Safe to call repeatedly: each statement is CREATE TABLE IF NOT EXISTS, so
    tables a cog already made are left exactly as they are.
    """
    os.makedirs("db", exist_ok=True)
    created: dict[str, int] = {}

    for db_path, statements in SCHEMA.items():
        try:
            async with aiosqlite.connect(db_path) as db:
                for statement in statements:
                    await db.execute(statement)
                await db.commit()
            created[db_path] = len(statements)
        except Exception as exc:
            print(f"[schema_guard] {db_path} failed: {exc}")

    await _ensure_columns()

    total = sum(created.values())
    print(f"[schema_guard] Verified {total} tables across {len(created)} databases")
    return created


# Columns added after a table already shipped. CREATE TABLE IF NOT EXISTS
# does nothing for an existing table, so these need an explicit ALTER.
ADDED_COLUMNS = (
    # Lets a restore delete the previous verification panel instead of
    # leaving a dead one behind next to the new message.
    ("db/verification.db", "verification_config", "panel_message_id", "INTEGER"),
    ("db/verification.db", "verification_config", "panel_channel_id", "INTEGER"),
)


async def _ensure_columns() -> None:
    for db_path, table, column, coltype in ADDED_COLUMNS:
        try:
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(f"PRAGMA table_info([{table}])") as cursor:
                    existing = {row[1] for row in await cursor.fetchall()}
                if not existing or column in existing:
                    continue
                await db.execute(
                    f"ALTER TABLE [{table}] ADD COLUMN [{column}] {coltype}"
                )
                await db.commit()
                print(f"[schema_guard] added {table}.{column}")
        except Exception as exc:
            print(f"[schema_guard] cannot add {table}.{column}: {exc}")
