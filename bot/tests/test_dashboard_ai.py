from pathlib import Path

ROOT = Path(__file__).parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_dashboard_ai_is_allowlisted_and_guild_scoped():
    store = read("bot/utils/dashboard_ai.py")
    route = read("bot/api/routes/dashboard_ai.py")
    bff = read("dashboard/app/api/bot/[...path]/route.ts")
    assert "dashboard_ai_users" in store
    assert "await dashboard_ai.allowed(actor)" in route
    assert 'scope === "dashboard-ai"' in bff
    assert "verifyGuildAccess(guildId)" in bff
    assert "x-firewall-actor" in route


def test_dashboard_ai_never_receives_sensitive_server_data():
    store = read("bot/utils/dashboard_ai.py")
    assert "Du erhältst bewusst keinerlei Serverdaten" in store
    assert "_best_text_channel" in store
    prompt = store[store.index("prompt = f"):store.index("text = await ticket_ai.generate_text")]
    assert "text_channels" not in prompt and "channel.id" not in prompt
    assert "KEINE Fragen nach Serverdaten" in store


def test_dashboard_ai_uses_ticket_key_and_confirmation_plans():
    store = read("bot/utils/dashboard_ai.py")
    route = read("bot/api/routes/dashboard_ai.py")
    page = read("dashboard/app/dashboard/guild/[guildId]/ai/page.tsx")
    assert "ticket_ai.generate_text" in store
    assert "GROQ" not in store or "ticket_ai" in store
    assert "dashboard_ai_plans" in store and "PLAN_TTL" in store
    assert "take_plan" in route
    assert "Änderungen anwenden" in page and "Verwerfen" in page


def test_only_validated_dashboard_actions_are_applied():
    store = read("bot/utils/dashboard_ai.py")
    route = read("bot/api/routes/dashboard_ai.py")
    assert 'kind == "set_module"' in store
    assert 'kind == "configure_welcome"' in store
    assert "module in guild_modules.MODULE_KEYS" in store
    assert "channel_id in channel_ids" in store
    assert "await guild_modules.set_enabled" in route
    assert "patch_antinuke" in route
