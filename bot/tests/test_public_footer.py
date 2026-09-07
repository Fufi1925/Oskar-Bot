#!/usr/bin/env python3
"""Regression checks for the shared public website footer."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / "dashboard"
failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        failures.append(f"{label}: {detail}" if detail else label)
        print(f" FAIL  {label}")


def main() -> int:
    footer = (DASHBOARD / "components/public-footer.tsx").read_text(encoding="utf-8")
    layout = (DASHBOARD / "app/layout.tsx").read_text(encoding="utf-8")
    home = (DASHBOARD / "app/page.tsx").read_text(encoding="utf-8")
    commands = (DASHBOARD / "app/commands/page.tsx").read_text(encoding="utf-8")
    legal = (DASHBOARD / "components/legal-page.tsx").read_text(encoding="utf-8")
    api_server = (ROOT / "bot/api/server.py").read_text(encoding="utf-8")

    print("\nDie gemeinsame öffentliche Fußzeile")
    check("sie wird genau einmal im Root-Layout eingebunden",
          layout.count("<PublicFooter ") == 1)
    check("Startseite hat keine zweite Fußzeile", "<footer" not in home)
    check("Befehlsseite hat keine zweite Fußzeile", "<footer" not in commands)
    check("Rechtstexte haben keine zweite Fußzeile", "<footer" not in legal)
    check("das Dashboard ist ausdrücklich ausgenommen",
          'pathname.startsWith("/dashboard")' in footer)
    check("/docs erreicht die Website statt FastAPIs Swagger-Seite",
          "docs_url=None" in api_server and "redoc_url=None" in api_server
          and "openapi_url=None" in api_server)

    print("\nInhalt und Handy-Aufbau")
    check("Marke und Beschreibung stehen links", "Der Discord-Bot für" in footer)
    check("Schnellzugriff und Kontakt sind eigene Spalten",
          "Schnellzugriff" in footer and "Kontakt" in footer)
    check("auf dem Handy stehen die Bereiche untereinander",
          "grid gap-12" in footer and "lg:grid-cols-[" in footer)
    check("die gewünschte Team-Zeile ist vorhanden",
          "vom University-Team" in footer and "&copy; {2026}" in footer)
    check("Discord, Mail und das gewünschte TikTok-Profil sind verlinkt",
          "supportInvite" in footer and "TIKTOK_URL" in footer
          and "mailto:" in footer)
    check("Instagram bleibt wie gewünscht draußen",
          "INSTAGRAM_URL" not in footer and "Instagram" not in footer)

    print("\nLive-Status unten rechts")
    check("er fragt den unabhängigen Status ab",
          'fetch("/api/status"' in footer)
    check("jede Anfrage hat fünf Sekunden Timeout",
          "AbortSignal.timeout(5000)" in footer)
    check("er aktualisiert höchstens einmal pro Minute",
          "window.setInterval(load, 60_000)" in footer)
    check("der Timer wird sicher beendet",
          "window.clearInterval(timer)" in footer)
    check("online ist grün und führt zur Statusseite",
          'online === true' in footer and "bg-emerald-400" in footer
          and 'href="/status"' in footer)
    check("der Status steht am rechten Ende der unteren Zeile",
          "sm:justify-between" in footer and "<LiveStatus />" in footer)

    print(f"\n{len(failures)} Fehler")
    for failure in failures:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
