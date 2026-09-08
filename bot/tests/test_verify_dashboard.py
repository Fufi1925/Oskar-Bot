#!/usr/bin/env python3
"""Regression checks for the user-friendly OAuth verification dashboard."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PANEL = (ROOT / "dashboard/components/dashboard/verify-panel.tsx").read_text(encoding="utf-8")
failures: list[str] = []


def check(label: str, condition: bool) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}")
    if not condition:
        failures.append(label)


print("\nVerify-Dashboard")
for section in ("Einrichtung", "Blacklist", "Nachrichten", "Erweitert", "Verlauf"):
    check(f"responsiver Tab {section}", f'label: "{section}"' in PANEL)

for feature in (
    "Sichere Verifizierung",
    "Live-Vorschau",
    "Panel jetzt posten",
    "identify · guilds",
    "Server-Blacklist aktivieren",
    "Eigene Ablehnungs-DM verwenden",
    "Verifizierungs-Verlauf",
    "Mindestalter des Discord-Kontos",
):
    check(feature, feature in PANEL)

check("kein CAPTCHA-Schalter", "CAPTCHA Only" not in PANEL and "Nur CAPTCHA" not in PANEL)
check("keine Methodenauswahl", "verification_method" not in PANEL)
check("OAuth-Datensparsamkeit erklärt", "nicht gespeichert" in re.sub(r"\s+", " ", PANEL))
check("mobile Tabs können horizontal scrollen", "overflow-x-auto" in PANEL)
check("Desktop-Vorschau bleibt sichtbar", "xl:sticky" in PANEL)
check("ungespeicherte Daten blockieren das Posten", "p.dirty > 0" in PANEL)
check("Blacklist-IDs werden vor dem Speichern geprüft", r"^\d{17,20}$" in PANEL)

print(f"\n{len(failures)} Fehler")
for failure in failures:
    print(f"  - {failure}")
sys.exit(1 if failures else 0)
