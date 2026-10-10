import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import aiosqlite

from utils import emoji, verify_store
from cogs.commands.verification import ConfigurablePanel, VCard, Verification


def text_of(view):
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay))


def test_english_defaults_migrate_stock_fields_without_overwriting_custom_text():
    settings = verify_store.normalise({
        "panel_title": f"{emoji.WARNING} Server-Verifizierung",
        "panel_text": "My server's custom instructions: {role}",
        "panel_footer": "Bereitgestellt von CloudTIX",
        "button_label": "Verifizieren",
        "dm_success_text": "Our custom welcome",
    })
    assert settings["panel_title"] == verify_store.DEFAULTS["panel_title"]
    assert settings["panel_text"] == "My server's custom instructions: {role}"
    assert settings["panel_footer"] == "Powered by CloudTIX"
    assert settings["button_label"] == "Verify with Discord"
    assert settings["dm_success_text"] == "Our custom welcome"
    assert "How to verify" in verify_store.DEFAULTS["panel_text"]
    assert "Your privacy" in verify_store.DEFAULTS["panel_text"]


def test_public_panel_and_success_errors_use_v2_custom_emojis_and_english():
    async def scenario():
        guild = SimpleNamespace(id=123, name="Example Server", member_count=42,
                                get_role=lambda role_id: SimpleNamespace(name="Verified"))
        settings = {**verify_store.DEFAULTS, "verified_role_ids": [456], "verified_count": 21}
        cog = Verification.__new__(Verification)
        panel = cog.build_panel(guild, settings)
        assert isinstance(panel, ConfigurablePanel) and panel.has_components_v2()
        body = text_of(panel)
        assert "Verify your account" in body and "Example Server" in body and "@Verified" in body
        assert emoji.WARNING in body and emoji.INFO in body and emoji.LOCK in body
        buttons = [item for item in panel.walk_children() if isinstance(item, discord.ui.Button)]
        assert buttons[0].label == "Verify with Discord" and buttons[0].url.endswith("/api/verify/start?guild=123")
        assert buttons[1].label == "21 verified members" and buttons[1].disabled
        preview = cog.build_panel(guild, settings, preview=True)
        assert "Preview" in text_of(preview)
        assert all(item.disabled for item in preview.walk_children() if isinstance(item, discord.ui.Button))
        for tone, marker in [("success", emoji.TICK), ("warning", emoji.WARNING), ("error", emoji.CROSS_ALT)]:
            view = VCard("Verification complete" if tone == "success" else "Verification unavailable", "Please try again.", tone=tone)
            assert view.has_components_v2() and marker in text_of(view)
    asyncio.run(scenario())


def test_startup_refreshes_existing_panels_once_and_preserves_custom_text(tmp_path, monkeypatch):
    from cogs.commands import verification
    path = str(tmp_path / "verification.db")
    monkeypatch.setattr(verification, "DATABASE_PATH", path)
    async def scenario():
        async with aiosqlite.connect(path) as db:
            await verify_store.ensure_schema(db)
            await verify_store.save_settings(db, 123, {
                "enabled": True, "verification_channel_id": 5, "verified_role_id": 6,
                "panel_message_id": 7, "panel_channel_id": 5,
                "panel_title": f"{emoji.WARNING} Server-Verifizierung",
                "panel_text": "My custom instructions remain intact.",
            })
            await verify_store.save_settings(db, 222, {
                "enabled": False, "verification_channel_id": 5, "verified_role_id": 6,
                "panel_message_id": 8, "panel_channel_id": 5,
            })
        message = SimpleNamespace(edit=AsyncMock())
        channel = SimpleNamespace(fetch_message=AsyncMock(return_value=message))
        guild = SimpleNamespace(id=123, name="Example Server", member_count=42,
            get_role=lambda role_id: SimpleNamespace(name="Verified"), get_channel=lambda channel_id: channel)
        cog = Verification.__new__(Verification)
        cog.bot = SimpleNamespace(get_guild=lambda guild_id: guild)
        cog._panels_refreshed = False
        await cog.on_ready()
        await cog.on_ready()
        channel.fetch_message.assert_awaited_once_with(7)
        message.edit.assert_awaited_once()
        kwargs = message.edit.call_args.kwargs
        assert kwargs["content"] is None and kwargs["embeds"] == []
        assert kwargs["view"].has_components_v2()
        body = text_of(kwargs["view"])
        assert "Verify your account" in body and "My custom instructions remain intact." in body
    asyncio.run(scenario())
