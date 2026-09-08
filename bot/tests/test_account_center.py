#!/usr/bin/env python3
"""Account privacy, session security and measured activity regression tests."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import sys
import tempfile

import aiosqlite

ROOT = Path(__file__).resolve().parents[2]
BOT = ROOT / "bot"
DASHBOARD = ROOT / "dashboard"
sys.path.insert(0, str(BOT))

from utils import account_preferences, account_security, leveling_store  # noqa: E402

failures: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        failures.append(f"{label}: {detail}" if detail else label)
        print(f" FAIL  {label}")


async def activity_scenario(path: str) -> None:
    async with aiosqlite.connect(path) as db:
        await leveling_store.ensure_schema(db)
        await leveling_store.add_xp(db, 11, 22, 25)
        await leveling_store.add_xp(db, 11, 22, 30)
        activity = await leveling_store.account_activity(db, 22, 30)
        check("XP der Nachrichten wird tageweise summiert", activity["xp_30d"] == 55)
        check("Nachrichten werden tageweise gezählt", activity["messages_30d"] == 2)
        check("der aktive Server stammt aus Messwerten", activity["active_guild"]["measured"] is True)
        check("30 Tage werden vollständig als Slots geliefert", len(activity["daily"]) == 30)
        check("Zeiträume vor Messbeginn bleiben unbekannt",
              any(not day["known"] for day in activity["daily"][:-1]))
        progress = activity["best_progress"]
        check("Level-Fortschritt nennt aktuelle und benötigte XP",
              progress["current"] == 55 and progress["needed"] > 55)


def main() -> int:
    print("\nPersönlicher Aktivitätsverlauf")
    with tempfile.TemporaryDirectory() as tmp:
        try:
            asyncio.run(asyncio.wait_for(activity_scenario(os.path.join(tmp, "leveling.db")), timeout=5))
        except TimeoutError:
            check("der Aktivitätstest endet innerhalb von fünf Sekunden", False, "Timeout")

    print("\nSitzungen und Widerruf")
    with tempfile.TemporaryDirectory() as tmp:
        original = account_security.DB_PATH
        account_security.DB_PATH = os.path.join(tmp, "security.db")
        try:
            first = account_security.record_session("22", "Mozilla/5.0 (Linux; Android 14) Chrome/120")
            second = account_security.record_session("22", "Mozilla/5.0 (Windows NT 10.0) Firefox/120")
            check("Geräte werden verständlich benannt", "Android" in first["device"])
            check("ein Wechsel der Geräteklasse wird markiert", bool(second["unusual"]))
            check("es werden keine IP-Adressen gespeichert",
                  "ip" not in {column.lower() for column in second})
            import sqlite3
            with sqlite3.connect(account_security.DB_PATH) as conn:
                retained_agent = conn.execute(
                    "SELECT user_agent FROM account_sessions ORDER BY id DESC LIMIT 1"
                ).fetchone()[0]
            check("der rohe User-Agent wird nicht aufbewahrt", retained_agent == "")
            issued = account_security.revoke_all("22")
            check("alle älteren JWTs werden widerrufen",
                  account_security.revoked_before("22") == issued and issued > 0)
        finally:
            account_security.DB_PATH = original

    print("\nPersönliche Einstellungen")
    with tempfile.TemporaryDirectory() as tmp:
        original = account_preferences.DB_PATH
        account_preferences.DB_PATH = os.path.join(tmp, "preferences.db")
        try:
            saved = account_preferences.save("22", {
                "language": "en", "theme": "light", "timezone": "UTC",
                "number_format": "en-GB", "date_format": "iso", "start_page": "/konto",
            })
            check("Einstellungen werden kontogebunden gespeichert",
                  saved["language"] == "en" and saved["start_page"] == "/konto")
            check("Einstellungen bleiben beim erneuten Lesen erhalten",
                  account_preferences.get("22")["theme"] == "light")
            try:
                account_preferences.save("22", {"start_page": "https://example.org"})
                invalid_rejected = False
            except ValueError:
                invalid_rejected = True
            check("externe oder ungültige Startseiten werden abgelehnt", invalid_rejected)
        finally:
            account_preferences.DB_PATH = original

    print("\nVerdrahtung der Kontoseite")
    page = (DASHBOARD / "app/konto/page.tsx").read_text(encoding="utf-8")
    privacy = (DASHBOARD / "components/account-privacy-panel.tsx").read_text(encoding="utf-8")
    security = (DASHBOARD / "components/account-security-panel.tsx").read_text(encoding="utf-8")
    activity = (DASHBOARD / "components/account-activity-panel.tsx").read_text(encoding="utf-8")
    support = (DASHBOARD / "components/account-support-panel.tsx").read_text(encoding="utf-8")
    applications = (DASHBOARD / "components/account-applications-panel.tsx").read_text(encoding="utf-8")
    preferences = (DASHBOARD / "components/account-preferences-panel.tsx").read_text(encoding="utf-8")
    proxy = (DASHBOARD / "app/api/bot/[...path]/route.ts").read_text(encoding="utf-8")
    auth = (DASHBOARD / "lib/auth.ts").read_text(encoding="utf-8")

    for component in (
        "AccountActivityPanel", "AccountSupportPanel", "AccountApplicationsPanel",
        "AccountPreferencesPanel", "AccountSecurityPanel", "AccountPrivacyPanel",
    ):
        check(f"{component} ist auf der Kontoseite", f"<{component}" in page)
    check("Datenschutz bietet Inventar und JSON-Download",
          "getMyPrivacyInventory" in privacy and "exportMyData" in privacy and "Blob" in privacy)
    check("vergangene Löschanträge werden angezeigt", "getMyErasureRequests" in privacy)
    check("Cookie-Einstellungen lassen sich zurücksetzen", "HINWEIS_COOKIE" in privacy)
    check("Sicherheitsbereich kann alle Sitzungen widerrufen",
          "revokeAccountSessions" in security and "Von allen Geräten abmelden" in security)
    check("Discord-Berechtigungen werden sichtbar erklärt", "permissions" in security)
    check("7 und 30 Tage sind wählbar", "([7, 30] as const)" in activity)
    check("nicht gemessene Tage haben einen eigenen Zustand", "item.known" in activity)
    check("Support zeigt echte Tickets, Status und Discord-Link",
          "getAccountSupport" in support and 'fetch("/api/status"' in support and "support_invite" in support)
    check("Bewerbungen zeigen Status, Datum und Rückmeldung",
          "getMyApplication" in applications and "created_at" in applications and "application.reason" in applications)
    check("alle persönlichen Auswahlfelder sind vorhanden",
          all(term in preferences for term in ("language", "theme", "timezone", "number_format", "date_format", "start_page")))
    check("BFF bindet Kontoaktionen an die eigene Sitzung",
          "rest[1] !== session.user.id" in proxy and '"session", "revoke"' in proxy and 'action === "preferences"' in proxy)
    check("JWTs werden serverseitig gegen den Widerruf geprüft",
          "revokedBefore" in auth and "sessionRevoked" in auth)
    check("die Widerrufsprüfung hat ein festes Timeout", "AbortSignal.timeout(2000)" in auth)

    print(f"\n{len(failures)} Fehler")
    for failure in failures:
        print(f"  - {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
