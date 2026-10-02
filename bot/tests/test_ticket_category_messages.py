"""Regression coverage for per-category Premium greetings and real role pings."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_category_message_is_migration_safe_and_persisted():
    store = read("bot/api/ticket_panels.py")
    cog = read("bot/cogs/commands/ticket.py")
    guard = read("bot/api/schema_guard.py")
    for source in (store, cog, guard):
        assert "ticket_welcome_title" in source
        assert "ticket_welcome_message" in source
    assert "existing_title" in store and "existing_message" in store
    assert 'cat_info["ticket_welcome_title"]' in cog
    assert 'cat_info["ticket_welcome_message"]' in cog


def test_category_message_is_premium_gated_without_blocking_normal_edits():
    route = read("bot/api/routes/tickets.py")
    block = route[route.index("async def upsert_category"):route.index("@router.delete", route.index("async def upsert_category"))]
    assert "has_premium_access" in block
    assert "configure=True" in block
    assert "key not in category_message_fields" in block


def test_ticket_role_mentions_are_explicitly_allowed():
    cog = read("bot/cogs/commands/ticket.py")
    start = cog.index('pings = [user.mention]')
    end = cog.index("created_message =", start)
    block = cog[start:end]
    assert "ping_roles.append(role)" in block
    assert "allowed_mentions=discord.AllowedMentions" in block
    assert "roles=ping_roles" in block
    assert "users=[user]" in block
    assert "everyone=False" in block


def test_dashboard_has_category_editor_and_live_preview():
    page = read("dashboard/components/dashboard/ticket-panels.tsx")
    assert "Eigene Nachricht für diese Kategorie" in page
    assert "Live-Vorschau" in page
    assert "CATEGORY_BUTTON_PREVIEW" in page
    assert "ticket_welcome_title" in page
    assert "ticket_welcome_message" in page
    assert "premiumConfigurable" in page
