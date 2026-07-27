# Tests

Standalone scripts — no pytest required.

```bash
cd bot
python3 tests/run_all.py          # everything
python3 tests/test_partial_updates.py   # a single file
```

Each file exits non-zero on failure, so `run_all.py` works as a CI step.
They run against a temporary directory and a fake bot, so they never touch
the real `db/` folder or talk to Discord.

## What each file guards

| File | Catches |
|---|---|
| `test_patch_utils.py` | The merge helper itself: unsent fields keep their stored value, `false` is still written, unknown keys are dropped. |
| `test_partial_updates.py` | End to end per module: set switch A, change only B, reload — A must survive. This is the bug that shipped in guild extra-settings. |
| `test_response_types.py` | Response models vs. what the tables actually store. Discord IDs are INTEGER in SQLite but declared as strings, which made GET return 500 once a value existed. |
| `test_panel_restore.py` | Panels are reposted after a restore, dead reaction roles are cleaned up. |
| `test_servertools.py` | The server tools: overview, security scan, audits, actions. |
| `test_ticket_panels.py` | Several ticket panels per guild, and that a partial save keeps the rest. |
| `test_snowflake_ids.py` | Discord IDs stay strings. `Number("1327995167345819721")` rounds to `…819600`, which is why picking a channel silently did nothing. |
| `test_giveaways.py` | Entries via the button, weighted and guaranteed draws, editing a running giveaway, entry requirements — and that the odds never reach the Discord message. |
| `test_leveling.py` | The XP curve, one storage table instead of two, min/max XP actually being random, multipliers not stacking, reward roles, auto-delete settings, the colour ramps and automatic role ladder, and the migration off the old tables. |
| `test_vanity_broadcast.py` | Vanity triggers normalise to one form, the status match respects word boundaries, roles given by hand are never revoked; broadcasts record a per-guild outcome, preview sends nothing, and a schedule can be called back. |
| `test_welcome.py` | One renderer for the greeter and the dashboard preview. They used to fill different placeholders, so the preview showed something no member would ever get. |

## Adding a module

Append to `CASES` in `test_partial_updates.py`:

```python
("my-module", "/my-module", ("enabled", True), ("some_field", 42)),
```

`None` for both pairs makes the test discover the first two booleans the
GET returns and toggle those instead — handy for pure toggle maps.

## Why these exist

Five bug classes hit this project more than once:

1. A PATCH rebuilding every field from defaults, so saving one switch
   silently reset the others. Use `api.patch_utils.merge_partial()`.
2. A response model declaring `str` for a column stored as INTEGER, which
   only fails after the first value is written.
3. The same thing implemented twice — a feature and its dashboard preview
   drifting apart. The welcome message had two renderers with two
   different sets of placeholders. Share the code instead.
4. A feature whose name does not match what it does. "Vanity roles"
   polled whether the *invite* existed and gave the role to everyone;
   "Global Broadcast" wrote a dashboard banner and reached no Discord
   server at all. Both looked like they worked.
5. Two tables holding the same numbers. Leveling wrote `user_xp` **and**
   `users`; reads went to the first, the admin commands to the second, so
   `resetxp` reported success and changed nothing. One table, one owner.

All five are invisible on an empty server and only show up later, which
is exactly why they need automated coverage.
