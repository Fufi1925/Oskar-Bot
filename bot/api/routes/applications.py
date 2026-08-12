"""
Bewerbungen -- Panels, Kategorien und Entscheidungen fuers Dashboard.

Die Panels selbst liegen in ``utils/application_store.py``; hier steht
nur, was ueber HTTP erreichbar ist. Eine Ausnahme ist ``send_panel``:
das Auswahlmenue kann nur der laufende Bot verschicken, weil die
Interaktion danach bei ihm ankommen muss.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import application_store as store
from utils import feature_audit

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()


@router.get("/{guild_id}/panels", summary="Alle Bewerbungs-Panels")
async def get_panels(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    panels = await store.list_panels(guild_id)
    offen = await store.list_applications(guild_id, status=store.STATUS_OPEN)

    return {
        "guild_id": str(guild_id),
        "panels": panels,
        "open_count": len(offen),
        "limits": {
            "panels": store.MAX_PANELS,
            "categories": store.MAX_CATEGORIES,
            "min_questions": store.MIN_QUESTIONS,
            "max_questions": store.MAX_QUESTIONS,
            "accept_roles": store.MAX_ACCEPT_ROLES,
        },
    }


@router.post("/{guild_id}/panels", summary="Panel anlegen")
async def create_panel(guild_id: int, data: dict | None = None):
    try:
        ergebnis = await store.create_panel(
            guild_id, str((data or {}).get("name", "Bewerbungen"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", **ergebnis}


@router.patch("/{guild_id}/panels/{panel_id}", summary="Panel bearbeiten")
async def update_panel(guild_id: int, panel_id: int, data: dict):
    await store.update_panel(guild_id, panel_id, data or {})
    return {"status": "success"}


@router.delete("/{guild_id}/panels/{panel_id}", summary="Panel loeschen")
async def delete_panel(guild_id: int, panel_id: int, actor: str = ""):
    if not await store.delete_panel(guild_id, panel_id):
        raise HTTPException(status_code=404, detail="Panel nicht gefunden.")
    await feature_audit.log_action(
        "application_panel_deleted", actor=actor, guild_id=guild_id,
        detail=f"Panel #{panel_id}",
    )
    return {"status": "success"}


@router.put("/{guild_id}/panels/{panel_id}/categories",
            summary="Kategorie anlegen oder bearbeiten")
async def upsert_category(guild_id: int, panel_id: int, data: dict):
    try:
        ergebnis = await store.upsert_category(guild_id, panel_id, data or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"status": "success", **ergebnis}


@router.delete("/{guild_id}/categories/{category_id}",
               summary="Kategorie loeschen")
async def delete_category(guild_id: int, category_id: int):
    if not await store.delete_category(guild_id, category_id):
        raise HTTPException(status_code=404, detail="Kategorie nicht gefunden.")
    return {"status": "success"}


@router.post("/{guild_id}/panels/{panel_id}/send", summary="Panel posten")
async def send_panel(
    guild_id: int,
    panel_id: int,
    data: dict | None = None,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Das Auswahlmenue in den Kanal schicken.

    Lehnt frueh und mit Begruendung ab, statt etwas Unbrauchbares zu
    posten: kein Kanal, keine Kategorien, keine Rechte.
    """
    import discord

    from cogs.commands.applications import ApplicationPanelView

    actor = str((data or {}).get("actor", "dashboard"))

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(status_code=404, detail="Der Bot ist nicht auf diesem Server.")

    panel = await store.get_panel(panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail="Panel nicht gefunden.")

    if not panel.get("channel_id"):
        raise HTTPException(
            status_code=400,
            detail="Für dieses Panel ist noch kein Kanal ausgewählt.",
        )
    if not panel.get("categories"):
        raise HTTPException(
            status_code=400,
            detail="Das Panel hat noch keine Kategorie — es gäbe nichts auszuwählen.",
        )

    # Ohne Ergebniskanal landet jede Bewerbung im Nichts. Das faellt
    # sonst erst auf, wenn die erste eingeht.
    ohne_ziel = [
        k["name"] for k in panel["categories"]
        if not k.get("results_channel_id") and not panel.get("results_channel_id")
    ]
    if ohne_ziel:
        raise HTTPException(
            status_code=400,
            detail=(
                "Für diese Kategorien fehlt der Kanal, in dem die Bewerbungen "
                f"ankommen sollen: {', '.join(ohne_ziel)}."
            ),
        )

    channel = guild.get_channel(int(panel["channel_id"]))
    if channel is None:
        raise HTTPException(status_code=404, detail="Der Kanal existiert nicht mehr.")

    rechte = channel.permissions_for(guild.me)
    if not (rechte.send_messages and rechte.view_channel):
        raise HTTPException(
            status_code=403,
            detail=f"Der Bot darf in #{channel.name} nicht schreiben.",
        )

    # Die alte Nachricht wegraeumen, sonst stehen zwei Panels da.
    if panel.get("message_id"):
        try:
            alt = await channel.fetch_message(int(panel["message_id"]))
            await alt.delete()
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

    embed = discord.Embed(
        title=panel.get("embed_title") or "Bewerbungen",
        description=panel.get("embed_description") or "",
        color=panel.get("embed_color") or 0x3B82F6,
    )
    if panel.get("embed_image_url"):
        embed.set_image(url=panel["embed_image_url"])
    if panel.get("embed_thumbnail_url"):
        embed.set_thumbnail(url=panel["embed_thumbnail_url"])

    from utils.panels import from_embed

    cog = bot.get_cog("Applications")
    view = ApplicationPanelView(cog, panel)

    try:
        nachricht = await channel.send(view=from_embed(embed, view))
    except discord.Forbidden:
        raise HTTPException(
            status_code=403, detail=f"Keine Schreibrechte in #{channel.name}."
        )
    except discord.HTTPException as exc:
        raise HTTPException(status_code=400, detail=f"Discord lehnte ab: {exc}")

    await store.set_message_id(panel_id, nachricht.id)
    try:
        bot.add_view(ApplicationPanelView(cog, panel), message_id=nachricht.id)
    except Exception:
        pass

    await feature_audit.log_action(
        "application_panel_sent", actor=actor, guild_id=guild_id,
        detail=f"#{channel.name}",
    )
    return {
        "status": "success",
        "channel": channel.name,
        "url": nachricht.jump_url,
        "result": f"Panel in #{channel.name} gepostet.",
    }


@router.get("/{guild_id}/entries", summary="Eingereichte Bewerbungen")
async def list_entries(
    guild_id: int,
    status: str = "",
    limit: int = 100,
    bot: "universitybot" = Depends(get_bot),
):
    eintraege = await store.list_applications(guild_id, status or None, limit)
    kategorien = {}
    for panel in await store.list_panels(guild_id):
        for kategorie in panel["categories"]:
            kategorien[kategorie["category_id"]] = kategorie["name"]

    guild = bot.get_guild(guild_id)
    for eintrag in eintraege:
        eintrag["category_name"] = kategorien.get(
            eintrag["category_id"], "Gelöschte Kategorie"
        )
        mitglied = guild.get_member(int(eintrag["user_id"])) if guild else None
        nutzer = mitglied or bot.get_user(int(eintrag["user_id"]))
        eintrag["username"] = str(nutzer) if nutzer else None
        eintrag["avatar"] = (
            str(nutzer.display_avatar.url) if nutzer else None
        )

    return {"entries": eintraege, "count": len(eintraege)}


@router.post("/{guild_id}/entries/{application_id}/decide",
             summary="Bewerbung annehmen oder ablehnen")
async def decide_entry(
    guild_id: int,
    application_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Entscheiden, ohne Discord zu öffnen.

    Ruft denselben Weg auf wie die Knoepfe im Kanal -- sonst gaebe es
    zwei Fassungen davon, was beim Annehmen passiert, und die eine
    vergisst irgendwann die Rolle.
    """
    import discord

    status = str(data.get("status", "")).strip()
    if status not in (store.STATUS_ACCEPTED, store.STATUS_DENIED):
        raise HTTPException(
            status_code=400, detail="status muss 'accepted' oder 'denied' sein."
        )

    grund = str(data.get("reason", "")).strip()
    if not grund:
        raise HTTPException(status_code=400, detail="Eine Begründung ist erforderlich.")

    actor = str(data.get("actor", "")).strip()
    if not actor.isdigit():
        raise HTTPException(status_code=400, detail="Kein angemeldeter Nutzer.")

    vorher = await store.get_application(application_id)
    if vorher is None or int(vorher["guild_id"]) != guild_id:
        raise HTTPException(status_code=404, detail="Bewerbung nicht gefunden.")
    if vorher["status"] != store.STATUS_OPEN:
        raise HTTPException(
            status_code=409, detail="Über diese Bewerbung wurde bereits entschieden."
        )

    bewerbung = await store.decide(application_id, status, int(actor), grund)
    if bewerbung is None:
        raise HTTPException(
            status_code=409, detail="Über diese Bewerbung wurde bereits entschieden."
        )

    guild = bot.get_guild(guild_id)
    kategorie = await store.get_category(bewerbung["category_id"])
    angenommen = status == store.STATUS_ACCEPTED

    # Rollen vergeben, wenn eingestellt -- ueber dieselbe Funktion, die
    # auch die Knoepfe in Discord benutzen. Zwei Fassungen davon liefen
    # frueher oder spaeter auseinander.
    rollen_hinweis = ""
    nicht_vergeben: list[str] = []
    if angenommen and guild and kategorie:
        mitglied = guild.get_member(int(bewerbung["user_id"]))
        vergeben, nicht_vergeben = await store.grant_accept_roles(
            guild, mitglied, kategorie
        )
        if vergeben:
            wort = "die Rolle" if len(vergeben) == 1 else "die Rollen"
            rollen_hinweis = f"\nDu hast {wort} **{', '.join(vergeben)}** bekommen."

        # Ins Team uebernehmen, wenn eingeschaltet -- ueber denselben
        # Dienst wie die Knoepfe in Discord. Zwei Fassungen davon
        # liefen frueher oder spaeter auseinander, und eine vergaesse
        # den Akteneintrag.
        try:
            from utils import team_update as team_service

            uebernahme = await team_service.from_application(
                bot, guild, mitglied, kategorie,
                actor_id=int(actor) if str(actor).isdigit() else None,
            )
            if uebernahme is not None and uebernahme.failed:
                nicht_vergeben = list(nicht_vergeben) + uebernahme.failed
        except Exception as exc:
            logger.warning(f"Team-Uebernahme fehlgeschlagen: {exc}")

    # Die Nachricht im Kanal entwerten, damit dort niemand mehr klickt.
    if bewerbung.get("message_id") and kategorie:
        kanal_id = kategorie.get("results_channel_id")
        if not kanal_id:
            panel = await store.get_panel(kategorie["panel_id"])
            kanal_id = (panel or {}).get("results_channel_id")
        kanal = bot.get_channel(int(kanal_id)) if kanal_id else None
        if kanal is not None:
            try:
                from cogs.commands.applications import DecisionView
                from utils.panels import from_embed

                nachricht = await kanal.fetch_message(int(bewerbung["message_id"]))
                alt = nachricht.embeds[0] if nachricht.embeds else None
                embed = discord.Embed(
                    title=(alt.title if alt else "Bewerbung"),
                    description=(alt.description if alt else ""),
                    color=0x22C55E if angenommen else 0xEF4444,
                )
                for feld in (alt.fields if alt else []):
                    embed.add_field(name=feld.name, value=feld.value,
                                    inline=feld.inline)
                embed.add_field(
                    name="Angenommen von" if angenommen else "Abgelehnt von",
                    value=f"<@{actor}> (Dashboard)\n{grund[:1000]}",
                    inline=False,
                )
                embed.set_footer(text=f"Bewerbung #{application_id}")
                cog = bot.get_cog("Applications")
                await nachricht.edit(
                    view=from_embed(embed, DecisionView(cog, entschieden=True))
                )
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass

    # Und die Person benachrichtigen.
    nutzer = bot.get_user(int(bewerbung["user_id"]))
    if nutzer is None:
        try:
            nutzer = await bot.fetch_user(int(bewerbung["user_id"]))
        except discord.HTTPException:
            nutzer = None

    zugestellt = False
    if nutzer is not None:
        from utils.cv2 import CV2

        name = kategorie["name"] if kategorie else "deine Bewerbung"
        server = guild.name if guild else "dem Server"
        try:
            if angenommen:
                await nutzer.send(view=CV2(
                    "Bewerbung angenommen",
                    f"Deine Bewerbung für **{name}** auf **{server}** wurde "
                    f"angenommen.{rollen_hinweis}\n\n**Begründung:**\n{grund}",
                ))
            else:
                await nutzer.send(view=CV2(
                    "Bewerbung abgelehnt",
                    f"Deine Bewerbung für **{name}** auf **{server}** wurde "
                    f"abgelehnt.\n\n**Begründung:**\n{grund}",
                ))
            zugestellt = True
        except (discord.Forbidden, discord.HTTPException):
            zugestellt = False

    await feature_audit.log_action(
        f"application_{status}", actor=actor, guild_id=guild_id,
        detail=f"#{application_id}: {grund[:200]}",
    )
    return {
        "status": "success",
        "dm_delivered": zugestellt,
        # Was nicht vergeben werden konnte, muss das Dashboard anzeigen --
        # sonst glaubt das Team, die Rollen seien durch.
        "roles_failed": nicht_vergeben,
        "application": bewerbung,
    }
