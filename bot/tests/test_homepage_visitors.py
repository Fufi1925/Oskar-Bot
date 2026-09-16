"""Regression checks for the public, anonymous homepage country map."""
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "bot" / "utils" / "homepage_visitors.py"

spec = importlib.util.spec_from_file_location("homepage_visitors_test", MODULE)
assert spec and spec.loader
visitors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(visitors)


def test_country_page_views_are_real_aggregates_without_identifiers():
    with tempfile.TemporaryDirectory() as tmp:
        visitors.DB_PATH = os.path.join(tmp, "visitors.db")
        assert visitors.record("DE") is True
        assert visitors.record("de") is True
        assert visitors.record("GB") is True
        assert visitors.record("") is False
        assert visitors.record("Germany") is False

        result = visitors.summary()
        values = {item["country"]: item["views"] for item in result["countries"]}
        assert result["total"] == 3
        assert result["today"] == 3
        assert values == {"DE": 2, "GB": 1}
        assert result["metric"] == "homepage_page_views"


def test_public_route_does_not_accept_country_from_browser_body():
    route = (ROOT / "bot" / "api" / "routes" / "bot.py").read_text(encoding="utf-8")
    bff = (ROOT / "dashboard" / "app" / "api" / "bot" / "[...path]" / "route.ts").read_text(encoding="utf-8")
    page = (ROOT / "dashboard" / "app" / "page.tsx").read_text(encoding="utf-8")
    component = (ROOT / "dashboard" / "components" / "home" / "homepage-world-map.tsx").read_text(encoding="utf-8")

    assert 'request.headers.get("x-firewall-country", "")' in route
    assert 'rest[0] === "visitor-map"' in bff
    assert "<HomepageWorldMap />" in page
    assert "keine erfundenen Beispieldaten" in component
    assert "visitorsByCountry" not in component
