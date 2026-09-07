#!/usr/bin/env python3
"""Dark is the default and the global theme switch stays persistent."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
layout = (ROOT / "dashboard/app/layout.tsx").read_text()
toggle = (ROOT / "dashboard/components/theme-toggle.tsx").read_text()
css = (ROOT / "dashboard/app/globals.css").read_text()
checks = {
    "dark is the server-rendered default": 'data-theme="dark"' in layout,
    "saved theme is restored before paint": "localStorage.getItem('dashboard-theme')" in layout and "t==='light'?'light':'dark'" in layout,
    "toggle is mounted globally": "<ThemeToggle />" in layout,
    "toggle sits at the lower right": "fixed bottom-5 right-5" in toggle,
    "choice is persisted": 'localStorage.setItem("dashboard-theme"' in toggle,
    "both accessible buttons exist": 'aria-label="Helles Design"' in toggle and 'aria-label="Dunkles Design"' in toggle,
    "light and dark CSS exist": 'html[data-theme="light"]' in css and 'html[data-theme="dark"]' in css,
    "media keep their real colours": 'html[data-theme="light"] img' in css,
}
failed = 0
for label, okay in checks.items():
    print(("  ok   " if okay else "  FAIL ") + label)
    failed += not okay
print(f"\n{failed} failures")
raise SystemExit(1 if failed else 0)
