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

## Adding a module

Append to `CASES` in `test_partial_updates.py`:

```python
("my-module", "/my-module", ("enabled", True), ("some_field", 42)),
```

`None` for both pairs makes the test discover the first two booleans the
GET returns and toggle those instead — handy for pure toggle maps.

## Why these exist

Two bug classes hit this project more than once:

1. A PATCH rebuilding every field from defaults, so saving one switch
   silently reset the others. Use `api.patch_utils.merge_partial()`.
2. A response model declaring `str` for a column stored as INTEGER, which
   only fails after the first value is written.

Both are invisible on an empty server and only show up later, which is
exactly why they need automated coverage.
