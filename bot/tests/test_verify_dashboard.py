#!/usr/bin/env python3
"""Regression checks for the user-friendly OAuth verification dashboard."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
PANEL = (ROOT / "dashboard/components/dashboard/verify-panel.tsx").read_text(encoding="utf-8")
PULL = (ROOT / "dashboard/components/dashboard/user-pull-panel.tsx").read_text(encoding="utf-8")
NAV = (ROOT / "dashboard/app/dashboard/layout.tsx").read_text(encoding="utf-8")
BFF = (ROOT / "dashboard/app/api/bot/[...path]/route.ts").read_text(encoding="utf-8")
OAUTH_START = (ROOT / "dashboard/app/api/verify/start/route.ts").read_text(encoding="utf-8")
OAUTH_CALLBACK = (ROOT / "dashboard/app/api/verify/callback/route.ts").read_text(encoding="utf-8")
VERIFY_RESULT = (ROOT / "dashboard/app/verify/[guildId]/page.tsx").read_text(encoding="utf-8")
VERIFY_API = (ROOT / "bot/api/routes/verify.py").read_text(encoding="utf-8")
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

print("\nUser Pull")
check("unter den Rollen verlinkt", "User Pull" in PANEL and "/verification/pull" in PANEL)
check("Verifizierung bleibt im Schutz-Tab aufklappbar",
      'name: "Verifizierung"' in NAV and "subItem.children" in NAV
      and "Verifizierung aufklappen" in NAV)
check("Unterpunkt heißt Pull", 'name: "Pull"' in NAV)
check("eigene responsive Pull-Seite", "sm:place-items-center" in PULL and "UserPullPanel" in PULL)
check("Pull all verarbeitet nur autorisierte Nutzer",
      "Abrufbare Mitglieder" in PULL and "Nicht autorisierte Mitglieder" in PULL
      and "Pull all" in PULL)
check("Pull-all-Assistent hat Server, Rolle, Zusammenfassung und Code",
      all(text in PULL for text in ("Zielserver auswählen", "Zielrolle festlegen",
                                   "Pull all bestätigen", "Vierstelligen Code eingeben")))
check("Code-Kanal wird nach zehn Minuten gelöscht",
      "privaten Code-Kanal" in PULL and "nach 10 Minuten gelöscht" in PULL
      and "await asyncio.sleep(600)" in VERIFY_API
      and "User-Pull-Code nach 10 Minuten gelöscht" in VERIFY_API)
check("Pull all läuft als Fortschrittsjob", "Pull-all-Fortschritt" in PULL
      and "verification_pull_jobs" in VERIFY_API and "_run_pull_all_job" in VERIFY_API)
check("minimale Mitgliederdaten", all(value in PULL for value in ("Discord-ID", "verified_at", "pull_status", "avatar")))
check("keine sensiblen Mitgliederdaten", all(value not in PULL.lower() for value in ("ip-adresse", "standort", "gerät", "e-mail")))
check("Owner-Sperransicht ist blau", "Inhaberzugriff erforderlich" in PULL and "border-blue-500/20" in PULL)
check("Pull-BFF ist strikt owner-only", 'rest[1] === "pull"' in BFF and "ownsGuildOnDiscord(guildId)" in BFF)
check("guilds.join wird nur bei eingeschaltetem Pull angefordert",
      "if (settings.user_pull_enabled)" in OAUTH_START
      and 'scopes += " guilds.join"' in OAUTH_START)
check("Access-Token wird nie gespeichert und Pull nutzt Refresh-Autorisierung",
      "refresh_token: refreshToken" in OAUTH_CALLBACK
      and "access_token: accessToken" not in OAUTH_CALLBACK)
check("Verify widerruft nicht mehr die Dashboard-OAuth-Sitzung",
      "/oauth2/token/revoke" not in OAUTH_CALLBACK
      and "same Discord application" in OAUTH_CALLBACK)
check("temporärer Bot-Ausfall wird einmal wiederholt",
      "completion.status >= 500" in OAUTH_CALLBACK and "completion = await complete()" in OAUTH_CALLBACK)
check("Fehlerseite zeigt konkrete Rollenursache und erneuten Versuch",
      "role_unavailable" in VERIFY_RESULT and 'status === "error"' in VERIFY_RESULT
      and "Erneut mit Discord prüfen" in VERIFY_RESULT)

print(f"\n{len(failures)} Fehler")
for failure in failures:
    print(f"  - {failure}")
sys.exit(1 if failures else 0)
