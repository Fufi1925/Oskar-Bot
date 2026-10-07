"""Exercise real discord.py dispatch without opening a Discord connection."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
from discord.ui.view import ViewStore

from utils import guild_modules, interaction_notices


def interaction(custom_id="old", guild_id=123):
    response = SimpleNamespace(is_done=lambda: False, send_message=AsyncMock())
    return SimpleNamespace(guild_id=guild_id, guild=SimpleNamespace(id=guild_id), _state=None,
                           message=SimpleNamespace(id=42), extras={},
                           data={"custom_id": custom_id}, response=response)


def bot_and_store():
    store = ViewStore(None)
    bot = SimpleNamespace(_connection=SimpleNamespace(_view_store=store), extra_events={})
    interaction_notices.install(bot)
    return bot, store


async def drain(store):
    while store._ViewStore__tasks:
        await asyncio.gather(*tuple(store._ViewStore__tasks))


def text_of(view):
    return "\n".join(item.content for item in view.walk_children() if isinstance(item, discord.ui.TextDisplay))


def assert_private_card(inter, phrase):
    kwargs = inter.response.send_message.call_args.kwargs
    assert kwargs["ephemeral"] is True
    assert isinstance(kwargs["view"], discord.ui.LayoutView)
    assert kwargs["view"].has_components_v2()
    assert phrase in text_of(kwargs["view"])
    assert "<:" in text_of(kwargs["view"]), "use the bot's custom status emoji"
    assert "content" not in kwargs and "embed" not in kwargs


def test_expired_button_and_missing_modal_are_private():
    async def run():
        _, store = bot_and_store()
        button = interaction()
        modal = interaction()
        store.dispatch_view(2, "old", button)
        store.dispatch_modal("old", modal, [], {})
        await drain(store)
        for inter in [button, modal]:
            assert_private_card(inter, "This panel has expired")
    asyncio.run(run())


def test_active_button_runs_then_disabled_module_blocks_same_panel(monkeypatch):
    async def run():
        _, store = bot_and_store()
        calls = []

        class TicketView(discord.ui.View):
            @discord.ui.button(label="Close", custom_id="t_close")
            async def close_ticket(self, inter, button):
                calls.append(inter)

        TicketView.close_ticket.__module__ = "cogs.commands.ticket"
        view = TicketView(timeout=None)
        store.add_view(view, 42)
        monkeypatch.setattr(guild_modules, "_disabled", set())
        first = interaction("t_close")
        store.dispatch_view(2, "t_close", first)
        await drain(store)
        assert calls == [first]
        first.response.send_message.assert_not_called()
        # Toggle AFTER posting the panel: old callbacks must stop immediately.
        guild_modules._disabled.add((123, "tickets"))
        second = interaction("t_close")
        store.dispatch_view(2, "t_close", second)
        await drain(store)
        assert calls == [first]
        assert second.extras["university_module_blocked"]
        assert_private_card(second, "enable this module in the **dashboard**")
        view.stop()
    asyncio.run(run())


def test_restart_listener_keeps_its_panel_and_disabled_listener_gets_notice(monkeypatch):
    async def run():
        bot, store = bot_and_store()
        async def listener(inter):
            pass
        listener.__module__ = "cogs.events.selfroles"
        bot.extra_events["on_interaction"] = [listener]
        monkeypatch.setattr(guild_modules, "_disabled", set())
        acknowledged = False
        inter = interaction("selfroles_pick")
        inter.response.is_done = lambda: acknowledged
        store.dispatch_view(3, "selfroles_pick", inter)
        acknowledged = True
        await drain(store)
        inter.response.send_message.assert_not_called()
        guild_modules._disabled.add((123, "reactionroles"))
        denied = interaction("selfroles_pick")
        store.dispatch_view(3, "selfroles_pick", denied)
        await drain(store)
        assert denied.extras["university_module_blocked"]
        assert_private_card(denied, "Module disabled")
    asyncio.run(run())


def test_decorated_callback_still_maps_after_being_moved_into_generic_panel():
    async def run():
        class SettingsView(discord.ui.View):
            @discord.ui.button(label="Save")
            async def save(self, inter, button):
                pass
        # The class itself is generic, but the actual callback is in a cog.
        SettingsView.save.__module__ = "cogs.commands.automod"
        view = SettingsView()
        callback = view.children[0].callback
        assert guild_modules.module_for_callable(callback) == "automod"
        view.stop()
    asyncio.run(run())


def test_prefix_denial_is_private_dm_and_hybrid_denial_is_ephemeral(monkeypatch):
    async def callback():
        pass
    callback.__module__ = "cogs.commands.ticket"
    monkeypatch.setattr(guild_modules, "_disabled", {(123, "tickets")})
    async def run():
        ctx = SimpleNamespace(guild=SimpleNamespace(id=123), command=SimpleNamespace(callback=callback),
                              author=SimpleNamespace(send=AsyncMock()), interaction=None)
        assert await guild_modules.command_check(ctx) is False
        assert "Module disabled" in text_of(ctx.author.send.call_args.kwargs["view"])
        ctx.interaction = interaction()
        assert await guild_modules.command_check(ctx) is False
        assert_private_card(ctx.interaction, "Module disabled")
    asyncio.run(run())


def test_already_acknowledged_interaction_never_receives_another_response():
    async def run():
        inter = interaction()
        inter.response.is_done = lambda: True
        await interaction_notices.notify(inter)
        inter.response.send_message.assert_not_called()
    asyncio.run(run())


def test_registered_modal_is_preserved_and_module_off_blocks_submission(monkeypatch):
    async def run():
        _, store = bot_and_store()
        calls = []
        class ApplicationModal(discord.ui.Modal, title="Application"):
            async def on_submit(self, inter):
                calls.append(inter)
        ApplicationModal.__module__ = "cogs.commands.applications"
        monkeypatch.setattr(guild_modules, "_disabled", set())
        modal = ApplicationModal(custom_id="application_form")
        store.add_view(modal)
        first = interaction("application_form")
        store.dispatch_modal("application_form", first, [], {})
        await drain(store)
        assert calls == [first]
        first.response.send_message.assert_not_called()
        # A modal stops after a successful submit; register another instance.
        modal = ApplicationModal(custom_id="application_form")
        store.add_view(modal)
        guild_modules._disabled.add((123, "applications"))
        denied = interaction("application_form")
        store.dispatch_modal("application_form", denied, [], {})
        await drain(store)
        assert calls == [first]
        assert_private_card(denied, "Module disabled")
        modal.stop()
    asyncio.run(run())


def test_dynamic_components_keep_dispatch_and_obey_module_switch(monkeypatch):
    async def run():
        _, store = bot_and_store()
        class DynamicTicket(discord.ui.DynamicItem[discord.ui.Button], template=r"ticket_dynamic_[0-9]+"):
            def __init__(self):
                super().__init__(discord.ui.Button(label="Open", custom_id="ticket_dynamic_1"))
            @classmethod
            async def from_custom_id(cls, inter, item, match):
                return cls()
        DynamicTicket.__module__ = "cogs.commands.ticket"
        store.add_dynamic_items(DynamicTicket)
        # Preserve the real dispatch selection without constructing a full
        # cached Discord Message needed by the dynamic callback reconstruction.
        dispatch = []
        store.dispatch_dynamic_items = lambda *args: dispatch.append(args)
        monkeypatch.setattr(guild_modules, "_disabled", set())
        first = interaction("ticket_dynamic_1")
        store.dispatch_view(2, "ticket_dynamic_1", first)
        assert len(dispatch) == 1
        first.response.send_message.assert_not_called()
        guild_modules._disabled.add((123, "tickets"))
        denied = interaction("ticket_dynamic_1")
        store.dispatch_view(2, "ticket_dynamic_1", denied)
        await drain(store)
        assert len(dispatch) == 1
        assert_private_card(denied, "Module disabled")
    asyncio.run(run())


def test_generic_custom_command_buttons_keep_the_originating_module(monkeypatch):
    from utils.custom_command_messages import build_view
    async def run():
        _, store = bot_and_store()
        calls = []
        async def dispatch(inter, actions, private):
            calls.append(inter)
        dispatch.__module__ = "cogs.events.custom_commands_service"
        view = build_view({"components_v2": True}, [{"label": "Run", "actions": []}], [], dispatch)
        button = next(item for item in view.walk_children() if isinstance(item, discord.ui.Button))
        # Items may be moved into a shared panel; preserve their origin even
        # when the new view no longer has the builder's metadata.
        from utils.panels import Panel
        view = Panel("Command", buttons=[button])
        store.add_view(view, 42)
        monkeypatch.setattr(guild_modules, "_disabled", {(123, "custom-commands")})
        inter = interaction(button.custom_id)
        store.dispatch_view(2, button.custom_id, inter)
        await drain(store)
        assert calls == []
        assert_private_card(inter, "Module disabled")
        view.stop()
    asyncio.run(run())
