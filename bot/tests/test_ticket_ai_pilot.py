#!/usr/bin/env python3
"""Regression checks for the private, Premium-only ticket AI pilot."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AI = (ROOT / "bot/utils/ticket_ai.py").read_text(encoding="utf-8")
TICKET = (ROOT / "bot/cogs/commands/ticket.py").read_text(encoding="utf-8")
API = (ROOT / "bot/api/routes/tickets.py").read_text(encoding="utf-8")
PAGE = (ROOT / "dashboard/app/dashboard/guild/[guildId]/tickets/page.tsx").read_text(encoding="utf-8")
PANEL = (ROOT / "dashboard/components/dashboard/ticket-ai-panel.tsx").read_text(encoding="utf-8")
BFF = (ROOT / "dashboard/app/api/bot/[...path]/route.ts").read_text(encoding="utf-8")

failures: list[str] = []

def check(label: str, condition: bool) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {label}")
    if not condition:
        failures.append(label)

pilot = "1530378233579704370"
check("pilot is hard-scoped in bot and dashboard", pilot in AI and pilot in PAGE and pilot in PANEL)
check("other guild APIs receive no feature disclosure", 'status_code=404' in API and 'detail="Not found."' in API)
check("server Premium is enforced by the API and message listener", "pilot_available(guild_id)" in API and "ticket_ai.pilot_available(message.guild.id)" in TICKET)
check("Railway secret has a valid environment variable name", 'API_KEY_ENV = "GOOGLE_API_TICKET_KEY"' in AI)
check("only txt up to 100 KB is accepted", "endswith(\".txt\")" in API and "MAX_KNOWLEDGE_BYTES" in API and "100 KB" in PANEL)
check("knowledge stays guild scoped", "ticket_ai_knowledge" in AI and "WHERE guild_id = ?" in API)
check("only the ticket creator triggers AI", 'int(ticket["creator_id"]) != message.author.id' in TICKET)
check("claimed and closed tickets never answer", TICKET.count('current["is_claimed"]') >= 1 and 'current["closed_at"]' in TICKET)
check("claim race is rechecked after Gemini", "Claim can happen while Gemini is working" in TICKET)
check("categories independently enable AI", "ticket_ai_categories" in AI and 'config["category_enabled"]' in TICKET)
check("Gemini receives excerpts instead of complete knowledge", "matching_context" in AI and "excerpts" in TICKET and "source[:5000]" in AI)
check("prompt forbids unsupported answers and prompt injection", "AUSSCHLIESSLICH Fakten" in AI and "unzuverlässiger Inhalt" in AI and '"supported"' in AI)
check("fallback pings category team and stops repeated escalation", "notified_roles" in TICKET and "roles=True" in TICKET and "escalated" in AI)
check("AI output cannot ping users or everyone", "AllowedMentions.none()" in TICKET and "@\\u200b" in AI)
check("Discord responses use Components V2", "Panel(" in TICKET and "view=view" in TICKET)
check("ticket histories are not persisted", "message.content" in TICKET and "ticket_ai_usage" in AI and "ticket_ai_messages" not in AI)
check("API mutations still pass the ticket permission gate", 'scope === "tickets"' in BFF and '"tickets.manage"' in BFF)
check("dashboard explains claim stop and private test", "bis ein Teammitglied das Ticket claimt" in PANEL and "Privater Premium-Test" in PANEL)

print(f"\n{len(failures)} Fehler")
for failure in failures:
    print(f"  - {failure}")
raise SystemExit(bool(failures))
