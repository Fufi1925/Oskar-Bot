#!/usr/bin/env python3
"""Complete Premium ticket flow for customer-branded LBoost dashboards."""
from __future__ import annotations
import tempfile
import sqlite3
from pathlib import Path
from lbost_shop_app import db
from lbost_shop_app.config import Settings

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "lbost_shop_app/main.py").read_text()
BOT = (ROOT / "lbost_shop_bot/client.py").read_text()
TEMPLATE = (ROOT / "lbost_shop_app/templates/tickets.html").read_text()
TRANSCRIPT = (ROOT / "lbost_shop_app/templates/ticket_transcript.html").read_text()
SHELL = (ROOT / "lbost_shop_app/templates/dashboard_base.html").read_text()
JS = (ROOT / "lbost_shop_app/static/dashboard.js").read_text()
UNIVERSITY = (ROOT.parent / "dashboard/components/dashboard/ticket-panels.tsx").read_text()
NOTIFY = (ROOT.parent / "dashboard/components/dashboard/ticket-notify-panel.tsx").read_text()
failures = []

def check(name, value):
    print(("ok   " if value else "FAIL ") + name)
    if not value: failures.append(name)

check("customer branding replaces University", "{{ brand }}" in SHELL and "Premium Control Center" in SHELL and "University Bot</strong>" not in SHELL)
check("all custom dashboards are premium", 'premium = True' in MAIN and "PREMIUM_MAX_COMMANDS" in MAIN)
check("visual panel/category editor", all(x in TEMPLATE for x in ("data-panel", "data-category", "data-add-question", "Transcript immer ins Ticket-Log")))
check("no JSON editor for tickets", "panels_json" in TEMPLATE and "type=\"hidden\"" in TEMPLATE)
check("complete actions", all(x in BOT for x in ('shop:ticket:claim', 'shop:ticket:unclaim', 'shop:ticket:lock', 'shop:ticket:unlock', 'shop:ticket:reopen', 'delete_yes', 'delete_no')))
check("button and dropdown panels", 'panel.get("panel_type") == "dropdown"' in MAIN and "shop:ticket:select:" in BOT)
check("category-specific panels", "selected_category_key" in BOT and "category_keys" in BOT)
check("University panel design sections", all(label in TEMPLATE and label in UNIVERSITY for label in (
    "Ticket-Panels", "Darstellung", "Erweiterte Einstellungen", "Fragen vor der Erstellung",
    "Für alle Panels", "Transcript immer ins Ticket-Log", "Archiv-Kategorie", "Team-Rollen"
)))
check("University notification sections", all(label in TEMPLATE and label in NOTIFY for label in (
    "DM an den Ersteller", "DM an das Team", "Ruhezeit", "Wann der Bot eine DM schickt"
)))
check("visual Discord resource pickers", all(token in TEMPLATE for token in ("data-picker", "data-role-picker", "server_emojis")) and "<select" not in TEMPLATE)
check("category editor and live preview", all(token in TEMPLATE for token in ("data-category-modal", "Eigene Nachricht für diese Kategorie", "data-modal-preview-title")))
check("notification runtime", "ticket_notify_worker" in BOT and "record_ticket_activity" in BOT and '">sleep"' in BOT and '">wake"' in BOT)
check("save-before-send flow", "data-send-panel" in TEMPLATE and "fetch(form.action" in JS)
check("private transcript login", "/Tickets/Transkript/{ticket_id}" in MAIN and "session_user_any" in MAIN)
check("ticket owner transcript access", 'transcript["owner_id"]' in MAIN and 'transcript["closed_by"]' in MAIN)
check("Discord transcript design", all(x in TRANSCRIPT for x in ("TICKET ARCHIVE", "discord", "attachment", "reaction", "read-only")))
check("90-day retention", "90 * 86400" in db.__loader__.get_source(db.__name__))

with tempfile.TemporaryDirectory() as folder:
    settings = Settings(db_path=str(Path(folder) / "shop.sqlite3"), secret_key="test", token_encryption_key="test")
    db.reset_schema_cache()
    db.transcript_speichern(123, 456, "Guild", "ticket-0001", 7, 8, "default", [{"id":"1","content":"hello"}], settings)
    row = db.transcript_laden(123, settings)
    check("transcript DB roundtrip", bool(row and row["messages"][0]["content"] == "hello" and row["owner_id"] == 7))
    columns = {item[1] for item in sqlite3.connect(settings.db_path).execute("PRAGMA table_info(tickets)")}
    check("notification state survives restarts", {"last_owner_message", "last_staff_message", "last_staff_id", "user_dm_at", "staff_dm_at", "notify_sleep"} <= columns)

raise SystemExit(1 if failures else 0)
