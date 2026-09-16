"""Regression checks for the public homepage country map and 10-minute cooldown."""
from __future__ import annotations

import importlib.util
import os
import sqlite3
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "bot" / "utils" / "homepage_visitors.py"

spec = importlib.util.spec_from_file_location("homepage_visitors_test", MODULE)
assert spec and spec.loader
visitors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visitors)


def test_same_ip_counts_again_only_after_ten_minutes():
    with tempfile.TemporaryDirectory() as tmp:
        visitors.DB_PATH = os.path.join(tmp, "visitors.db")
        peter = "8.8.8.8"
        other = "1.1.1.1"

        assert visitors.record(peter, "DE", now=1_000) is True
        assert visitors.record(peter, "DE", now=1_599) is False
        assert visitors.record(other, "GB", now=1_599) is True
        assert visitors.record(peter, "DE", now=1_600) is True
        assert visitors.record("", "DE", now=1_700) is False
        assert visitors.record(peter, "Germany", now=1_700) is False

        result = visitors.summary()
        values = {item["country"]: item["views"] for item in result["countries"]}
        assert result["total"] == 3
        assert values == {"DE": 2, "GB": 1}
        assert result["metric"] == "homepage_page_views"
        assert result["cooldown_seconds"] == 600

        # Die lesbare IP darf weder in Tabellen noch im gespeicherten Inhalt stehen.
        with sqlite3.connect(visitors.DB_PATH) as db:
            columns = [row[1] for row in db.execute("PRAGMA table_info(homepage_recent_visitors)")]
            stored = " ".join(str(value) for row in db.execute("SELECT * FROM homepage_recent_visitors") for value in row)
        assert "ip" not in columns
        assert peter not in stored
        assert other not in stored


def test_recent_check_uses_same_cooldown():
    with tempfile.TemporaryDirectory() as tmp:
        visitors.DB_PATH = os.path.join(tmp, "visitors.db")
        visitors.record("8.8.4.4", "DE", now=2_000)
        assert visitors.recently_seen("8.8.4.4", now=2_599) is True
        assert visitors.recently_seen("8.8.4.4", now=2_600) is False


def test_public_route_uses_forwarded_ip_and_country_not_browser_body():
    route = (ROOT / "bot" / "api" / "routes" / "bot.py").read_text(encoding="utf-8")
    bff = (ROOT / "dashboard" / "app" / "api" / "bot" / "[...path]" / "route.ts").read_text(encoding="utf-8")
    page = (ROOT / "dashboard" / "app" / "page.tsx").read_text(encoding="utf-8")
    component = (ROOT / "dashboard" / "components" / "home" / "homepage-world-map.tsx").read_text(encoding="utf-8")

    assert 'request.headers.get("x-firewall-client-ip", "")' in route
    assert 'request.headers.get("x-firewall-country", "")' in route
    assert "homepage_visitors.lookup_country" in route
    assert 'rest[0] === "visitor-map"' in bff
    assert "<HomepageWorldMap />" in page
    assert 'laden("POST")' in component
    assert "visitorsByCountry" not in component
