import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from cogs.commands.honeypot import Honeypot, KicksButton
from utils import honeypot as store
from utils import interaction_notices


def text_of(view):
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay))


def test_persistent_button_opens_private_real_statistics_with_own_brand(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "honeypot.db"))
    monkeypatch.setenv("NEXTAUTH_URL", "https://cloudtix.up.railway.app")
    async def scenario():
        views = []
        bot = SimpleNamespace(guilds=[1, 2, 3], add_view=views.append,
                              user=SimpleNamespace(id=1530349205372145715, display_avatar=SimpleNamespace(url="https://cdn.discordapp.com/avatars/123/logo.png")))
        cog = Honeypot(bot)
        bot.get_cog = lambda name: cog
        await cog.cog_load()
        try:
            await store.save(await cog._db(), 111, enabled=True, channel_id=999, kicks=2)
            await store.save(await cog._db(), 222, enabled=True, kicks=3)
            assert views[0].is_persistent()
            button = views[0].children[0]
            assert button.custom_id == "honeypot:kicks" and not button.disabled
            interaction = SimpleNamespace(guild_id=111, client=bot, user=SimpleNamespace(),
                response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
            await button.callback(interaction)
            interaction.response.defer.assert_awaited_once_with(ephemeral=True)
            reply = interaction.followup.send.call_args.kwargs
            assert reply["ephemeral"] and reply["view"].has_components_v2()
            body = text_of(reply["view"])
            assert "What is a Honeypot?" in body and "<:" in body
            assert "Total moderated in this server: `2`" in body and "Total moderations: `5`" in body
            assert "Total servers: `3`" in body
            links = [item.url for item in reply["view"].walk_children() if isinstance(item, discord.ui.Button)]
            assert "https://cloudtix.up.railway.app/docs" in links
            assert "https://cloudtix.up.railway.app/honeypot/stats" in links
            assert any("client_id=1530349205372145715" in link for link in links)
            assert all("riskymh" not in link for link in links)
            # Existing warning customizations must never override the fixed text.
            embed = cog._baue_embed({"title": "Old title", "text": "Old text"})
            assert embed.title == store.DEFAULT_TITLE and embed.description == store.DEFAULT_TEXT
            assert embed.thumbnail.url == bot.user.display_avatar.url
            await store.save(await cog._db(), 111, enabled=False)
            await button.callback(interaction)
            assert "Module disabled" in text_of(interaction.followup.send.call_args.kwargs["view"])
        finally:
            await cog.cog_unload()
    asyncio.run(scenario())


def test_disabled_notice_distinguishes_members_and_administrators():
    async def scenario():
        for permissions, expected in [
            (discord.Permissions.none(), "Ask a server administrator"),
            (discord.Permissions(administrator=True), "Please enable this module"),
            (discord.Permissions(manage_guild=True), "Please enable this module"),
        ]:
            user = SimpleNamespace(guild_permissions=permissions)
            inter = SimpleNamespace(user=user, response=SimpleNamespace(is_done=lambda: False, send_message=AsyncMock()))
            await interaction_notices.notify(inter, "honeypot")
            reply = inter.response.send_message.call_args.kwargs
            assert reply["ephemeral"] and reply["view"].has_components_v2()
            body = text_of(reply["view"])
            assert expected in body and "<:" in body
            if not permissions.administrator and not permissions.manage_guild:
                assert "disabled intentionally" in body
    asyncio.run(scenario())


def test_existing_panels_are_upgraded_once_after_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "honeypot.db"))
    async def scenario():
        bot = SimpleNamespace(add_view=lambda view: None, get_guild=lambda guild_id: SimpleNamespace(id=guild_id))
        cog = Honeypot(bot)
        await cog.cog_load()
        try:
            await store.save(await cog._db(), 111, enabled=True)
            await store.save(await cog._db(), 222, enabled=False)
            cog.sende_oder_aktualisiere = AsyncMock()
            await cog.on_ready()
            await cog.on_ready()
            assert cog.sende_oder_aktualisiere.await_count == 1
            assert cog.sende_oder_aktualisiere.call_args.args[0].id == 111
        finally:
            await cog.cog_unload()
    asyncio.run(scenario())


def test_failed_warning_send_does_not_activate_an_unmarked_trap(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "honeypot.db"))
    async def scenario():
        cog = Honeypot(SimpleNamespace(add_view=lambda view: None))
        await cog.cog_load()
        try:
            cog._stelle_kanal_sicher = AsyncMock(return_value=SimpleNamespace(id=999))
            cog._nach_oben = AsyncMock()
            cog.sende_oder_aktualisiere = AsyncMock(return_value=None)
            result = await cog.aktiviere(SimpleNamespace(id=111))
            assert not result["ok"]
            record = await cog.settings(111)
            assert not record["enabled"] and record["channel_id"] is None
        finally:
            await cog.cog_unload()
    asyncio.run(scenario())


@pytest.mark.parametrize("target", [None, "888"])
def test_channel_switch_rebuilds_warning_and_rolls_back_failed_changes(tmp_path, monkeypatch, target):
    from api.routes import honeypot as routes
    monkeypatch.setattr(store, "DB_PATH", str(tmp_path / "honeypot.db"))
    async def scenario():
        cog = Honeypot(SimpleNamespace(add_view=lambda view: None))
        await cog.cog_load()
        try:
            guild = SimpleNamespace(id=111, get_channel=lambda channel_id: SimpleNamespace(id=channel_id, name="trap"),
                                    text_channels=[], roles=[], me=None)
            bot = SimpleNamespace(get_guild=lambda guild_id: guild, get_cog=lambda name: cog)
            monkeypatch.setattr(routes, "_db", cog._db)
            monkeypatch.setattr(routes.feature_audit, "log_action", AsyncMock())
            await store.save(await cog._db(), 111, enabled=True, custom_channel_id=777, channel_id=777, message_id=123)
            async def activate(guild):
                record = await cog.settings(111)
                assert record["channel_id"] is None and record["message_id"] is None
                await store.save(await cog._db(), 111, channel_id=int(target) if target else 999, message_id=456)
                return {"ok": True}
            cog.aktiviere = activate
            cog.sende_oder_aktualisiere = AsyncMock()
            updated = await routes.patch_settings(111, {"custom_channel_id": target}, bot=bot)
            assert updated["channel_id"] == (target or "999")
            cog.aktiviere = AsyncMock(return_value={"ok": False})
            with pytest.raises(routes.HTTPException):
                await routes.patch_settings(111, {"custom_channel_id": "555"}, bot=bot)
            record = await cog.settings(111)
            assert record["channel_id"] == int(target or "999")
            assert record["custom_channel_id"] == (int(target) if target else None)
            assert record["message_id"] == 456 and record["enabled"]
        finally:
            await cog.cog_unload()
    asyncio.run(scenario())
