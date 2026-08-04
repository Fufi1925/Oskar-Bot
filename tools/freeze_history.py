#!/usr/bin/env python3
"""
Die Git-Historie in eine Datei schreiben, die ins Image kommt.

Im Docker-Image gibt es kein ``.git`` -- der Dockerfile kopiert nur
``bot/`` und ``dashboard/``. Der Tester-Reiter braucht die Historie
aber zur Laufzeit. Also wird sie beim Build eingefroren.

Aufruf (im Dockerfile, vor dem COPY von bot/):

    python tools/freeze_history.py

Schlaegt das fehl -- kein Git, flacher Klon, was auch immer -- wird eine
leere Datei geschrieben und mit 0 beendet. Ein fehlender Changelog darf
keinen Deploy verhindern.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "bot", "deploy_history.json")

# So viele Commits wandern ins Image. Vierzig decken mehrere Deploys ab,
# ohne die Datei aufzublaehen.
LIMIT = 40


def main() -> int:
    sep, field = "\x1e", "\x1f"
    commits: list[dict] = []

    try:
        result = subprocess.run(
            ["git", "log", f"-{LIMIT}",
             f"--format=%H{field}%at{field}%s{field}%b{sep}"],
            cwd=REPO, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            for chunk in result.stdout.split(sep):
                if not chunk.strip():
                    continue
                parts = chunk.strip("\n").split(field)
                if len(parts) < 3:
                    continue
                commits.append({
                    "commit": parts[0],
                    "at": parts[1],
                    "subject": parts[2],
                    "body": parts[3] if len(parts) > 3 else "",
                })
        else:
            print(f"[freeze_history] git log failed: {result.stderr[:200]}",
                  file=sys.stderr)
    except Exception as exc:  # pragma: no cover
        print(f"[freeze_history] {type(exc).__name__}: {exc}", file=sys.stderr)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump({"commits": commits}, handle, ensure_ascii=False, indent=1)

    print(f"[freeze_history] {len(commits)} commits -> {OUT}")
    # Immer 0: ein fehlender Changelog ist kein Grund, den Deploy
    # abzubrechen.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
