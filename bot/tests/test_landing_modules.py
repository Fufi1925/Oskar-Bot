#!/usr/bin/env python3
"""Regression checks for the complete, truthful public landing page."""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PAGE = (ROOT / "dashboard/app/page.tsx").read_text(encoding="utf-8")
failures: list[str] = []


def check(label: str, condition: bool) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}")
    if not condition:
        failures.append(label)


print("\nVollständiger Modulüberblick")
expected = {
    "Server-Design", "Backups", "Server-Statistiken", "Anti-Nuke", "AutoMod",
    "Honeypot", "Verifizierung", "Notfallmodus", "Jail", "Nachtmodus",
    "Begrüßung", "Bewerbungen", "Abschied", "Beitritts-DM", "Auto-Rolle",
    "Reaktions-Rollen", "Eigene Rollen", "Vanity-Rollen", "Nickname", "Level-System",
    "Giveaways", "Counting", "Booster", "Benachrichtigungen", "Auto-Reaktion",
    "Autoresponder", "Custom Commands", "Anonymer Chat · Beta", "Musik",
    "Join to Create", "Sprach-Rolle", "Tickets", "Eigene Nachricht",
    "Sticky-Nachricht", "Einladungen", "Einladungs-Log", "No Prefix",
    "Speedrun · Premium", "Vorlagen-Upload · Experimentell",
    "Vorlagen-Community · Experimentell", "Teamliste", "Team-Update · Beta",
    "Logs", "Bot-Logs", "Server-Werkzeuge", "Dashboard Access",
    "Support-Warteraum · Beta",
}
for module in sorted(expected):
    check(module, bool(re.search(r'\[\s*"' + re.escape(module) + r'"\s*,', PAGE)))
check("47 Module werden aus den Gruppen berechnet", "MODUL_ANZAHL" in PAGE and len(expected) == 47)
for group in ("Design & Daten", "Schutz & Sicherheit", "Mitglieder & Community",
              "Interaktion & Automatisierung", "Sprache & Audio",
              "Nachrichten & Werkzeuge", "Vorlagen & Verwaltung"):
    check(f"Gruppe {group}", f'titel: "{group}"' in PAGE)

print("\nPremium-Werbung in der Seitenmitte")
features = PAGE.index('id="funktionen"')
premium = PAGE.index("Premium · Testphase", features)
stats = PAGE.index("{/* ── Zahlen", premium)
check("Premium steht zwischen Modulen und Kennzahlen", features < premium < stats)
for statement in ("Kaufen ist während der Testphase noch nicht möglich",
                  "Bis zu 10 Backups", "Bis zu 20 Custom Commands",
                  "Rollen, Kanäle und Online-Nutzer", "Ein Zugang für beide Bots"):
    check(statement, re.sub(r"\s+", " ", statement) in re.sub(r"\s+", " ", PAGE))
check("Beta-Antrag ist verlinkt", 'href="/dashboard/premium/beta"' in PAGE)
check("öffentlicher Vergleich ist verlinkt", 'href="/premium"' in PAGE)

print("\nWahrheitsgemäßes FAQ")
check("FAQ verschweigt Premium-Sperren nicht", "Einige Erweiterungen sind Premium vorbehalten" in PAGE)
check("FAQ behauptet keinen aktiven Verkauf", "Kann ich Premium bereits kaufen?" in PAGE and "Noch nicht." in PAGE)
check("FAQ verspricht keine Support-Antwortzeit", "am selben Tag" not in PAGE)
check("FAQ behauptet keine vollständige Bot-Übersetzung", "Einzelne ältere" in PAGE)
check("Messwerte vor Einführung werden nicht erfunden", "nicht rückwirkend erfunden" in PAGE)
check("acht neue Fragen", len(re.findall(r"\n\s+frage:", PAGE[PAGE.index("const FAQ"):PAGE.index("function FaqZeile")])) == 8)

print(f"\n{len(failures)} Fehler")
for failure in failures:
    print(f"  - {failure}")
sys.exit(1 if failures else 0)
