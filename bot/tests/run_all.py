#!/usr/bin/env python3
"""
Run every test in this folder.

    cd bot && python3 tests/run_all.py

Each test is a standalone script that exits non-zero on failure, so this
also works as a CI step without pytest being installed.
"""

import glob
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BOT = os.path.dirname(HERE)

SKIP = {"run_all.py", "__init__.py"}


def main() -> int:
    scripts = sorted(
        p for p in glob.glob(os.path.join(HERE, "test_*.py"))
        if os.path.basename(p) not in SKIP
    )

    failed = []
    for path in scripts:
        name = os.path.basename(path)
        print(f"\n=== {name} " + "=" * (56 - len(name)))
        result = subprocess.run(
            [sys.executable, path],
            cwd=BOT,
            capture_output=True,
            text=True,
        )
        # The API logs one JSON line per request; drop it from the report.
        for line in result.stdout.splitlines():
            if line.startswith('{"timestamp"') or line.startswith("[schema_guard]"):
                continue
            print(line)
        if result.returncode != 0:
            failed.append(name)
            tail = result.stderr.strip().splitlines()[-3:]
            for line in tail:
                print(f"    {line}")

    print("\n" + "=" * 64)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print(f"All {len(scripts)} test files passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
