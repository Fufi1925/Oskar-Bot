#!/usr/bin/env python3
"""Läuft alle Tests des Shop-Bereichs und meldet eine Zeile pro Datei.

Ein eigener Runner, weil die Tests des Hauptbots (``bot/tests/run_all.py``)
PYTHONPATH und Datenbankpfade des Bots setzen — der Shop ist bewusst eine
eigene Anwendung mit eigener SQLite-Datei.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def main() -> int:
    fehlgeschlagen: list[str] = []
    umgebung = dict(**{"PYTHONPATH": str(ROOT), "PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(Path.home())})
    for test in sorted(HERE.glob("test_*.py")):
        try:
            lauf = subprocess.run([sys.executable, str(test)], cwd=ROOT, capture_output=True, text=True, timeout=600, env=umgebung)
        except subprocess.TimeoutExpired:
            print(f"ZEITÜBERSCHRITT  {test.name}")
            fehlgeschlagen.append(test.name)
            continue
        ausgabe = (lauf.stdout + lauf.stderr).strip().splitlines()
        letzte = ausgabe[-1] if ausgabe else "(keine Ausgabe)"
        if lauf.returncode == 0:
            print(f"ok    {test.name:28} {letzte}")
        else:
            print(f"FEHLER {test.name:28} {letzte}")
            fehlgeschlagen.append(test.name)
    print(f"\n{len(list(HERE.glob('test_*.py'))) - len(fehlgeschlagen)}/{len(list(HERE.glob('test_*.py')))} Testdateien grün")
    if fehlgeschlagen:
        print("Fehlgeschlagen: " + ", ".join(fehlgeschlagen))
    return 1 if fehlgeschlagen else 0


if __name__ == "__main__":
    raise SystemExit(main())
