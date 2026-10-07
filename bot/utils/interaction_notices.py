"""Private Components V2 responses for expired panels and disabled modules.

Wrap this bot's ViewStore, rather than discord.py globally. Registered views,
dynamic items and restart-safe listener panels keep their original dispatch.
"""
from __future__ import annotations

import asyncio

import discord

from utils import guild_modules
from utils.panels import StatusCard


def disabled_card(module: str) -> StatusCard:
    label = module.replace("-", " ").title()
    return StatusCard("Module disabled", f"Hey! **{label}** is disabled on this server.\n"
                      "Ask a server administrator to enable this module in the **dashboard**, then try again.",
                      tone="warning")


async def notify(interaction, module: str | None = None, *, delay: float = 0) -> None:
    if delay:
        await asyncio.sleep(delay)
    if interaction.response.is_done():
        return
    view = disabled_card(module) if module else StatusCard(
        "Panel expired", "Hey! This panel has expired. Please refresh it or send the panel again, then try again.",
        tone="warning",
    )
    try:
        await interaction.response.send_message(view=view, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())
    except (discord.HTTPException, discord.InteractionResponded):
        # A parallel handler may have acknowledged it, or Discord's token may
        # already have expired. Neither case should produce another error.
        return


def listener_module(custom_id: str) -> str | None:
    """Only IDs actually handled by on_interaction listeners after a restart."""
    if custom_id == "selfroles_pick":
        return "reactionroles"
    if custom_id.startswith("giveaway_join_"):
        return "giveaways"
    if custom_id.startswith(("app_accept_", "app_deny_")):
        return "applications"
    if custom_id.startswith("create_ticket_") or custom_id in {
        "t_lock", "t_unlock", "t_claim", "t_close", "c_reopen", "c_delete",
    }:
        return "tickets"
    return None


def install(bot) -> None:
    store = bot._connection._view_store
    if getattr(store, "_university_notices_installed", False):
        return
    original_view = store.dispatch_view
    original_modal = store.dispatch_modal

    def schedule(interaction, module=None, *, delay=0):
        store.add_task(asyncio.create_task(notify(interaction, module, delay=delay)))

    def blocked(interaction, module):
        if module and not guild_modules.is_enabled(interaction.guild_id, module):
            interaction.extras["university_module_blocked"] = True
            schedule(interaction, module)
            return True
        return False

    def dispatch_view(component_type, custom_id, interaction):
        message_id = getattr(interaction.message, "id", None)
        key = (component_type, custom_id)
        item = store._views.get(message_id, {}).get(key) or store._views.get(None, {}).get(key)
        dynamic = [cls for pattern, cls in store._dynamic_items.items() if pattern.fullmatch(custom_id)]
        module = listener_module(custom_id)
        if item is not None:
            module = (getattr(item, "_university_module", None)
                      or getattr(item.view, "_university_module", None)
                      or guild_modules.module_for_callable(item.callback)
                      or guild_modules.module_for_callable(type(item.view)) or module)
        if dynamic:
            module = guild_modules.module_for_callable(dynamic[0]) or module
        if blocked(interaction, module):
            return
        if item is not None and (item.view is None or item.view.is_finished()):
            schedule(interaction)
            return
        if item is not None or dynamic:
            return original_view(component_type, custom_id, interaction)
        listeners = bot.extra_events.get("on_interaction", [])
        if module and any(guild_modules.module_for_callable(callback) == module for callback in listeners):
            # Let the existing listener recover its persistent panel first.
            schedule(interaction, delay=2)
        else:
            schedule(interaction)

    def dispatch_modal(custom_id, interaction, *args, **kwargs):
        modal = store._modals.get(custom_id)
        if modal is None:
            schedule(interaction)
            return
        module = guild_modules.module_for_callable(type(modal))
        if not blocked(interaction, module):
            original_modal(custom_id, interaction, *args, **kwargs)

    store.dispatch_view = dispatch_view
    store.dispatch_modal = dispatch_modal
    store._university_notices_installed = True
