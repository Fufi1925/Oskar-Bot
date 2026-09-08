#!/usr/bin/env python3
"""Regression checks for the user-friendly OAuth verification dashboard."""

from pathlib import Path
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
    "Verifizierung",
    "Live-Vorschau",
    "Panel jetzt posten",
    "OAuth2",
    "Server-Blacklist aktivieren",
    "Eigene Ablehnungs-DM verwenden",
    "Verifizierungs-Verlauf",
    "Mindestalter des Discord-Kontos",
):
    check(feature, feature in PANEL)

check("kein CAPTCHA-Schalter", "CAPTCHA Only" not in PANEL and "Nur CAPTCHA" not in PANEL)
check("keine Methodenauswahl", "verification_method" not in PANEL)
check("keine unnötige Ablauf-Erklärung", "So funktioniert die Prüfung" not in PANEL)
check("keine technischen Scope-Namen", "identify · guilds" not in PANEL)
check("keine Vorschau unter einzelnen Textfeldern", "Sofort-Vorschau" not in PANEL)
check("nur die passende zentrale Live-Vorschau bleibt", PANEL.count("Live-Vorschau") == 1)
check("bis zu drei Verify-Rollen", "[0, 1, 2].map" in PANEL and "bis zu 3" in PANEL)
check("Unverifiziert-Rolle steht in der Grundkonfiguration",
      PANEL.index("Unverifiziert-Rolle entfernen") < PANEL.index('tab === "advanced"'))
check("mobile Tabs können horizontal scrollen", "overflow-x-auto" in PANEL)
check("Desktop-Vorschau bleibt sichtbar", "xl:sticky" in PANEL)
check("ungespeicherte Daten blockieren das Posten", "p.dirty > 0" in PANEL)
check("Blacklist-IDs werden vor dem Speichern geprüft", r"^\d{17,20}$" in PANEL)

print(f"\n{len(failures)} Fehler")
for failure in failures:
    print(f"  - {failure}")
sys.exit(1 if failures else 0)
