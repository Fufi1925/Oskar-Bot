"""
Was der Bot gegen einen Nutzer unternimmt.

Getrennt von ``user_lookup.py``: dort steht, was gespeichert wird, hier
was auf Discord passiert. Der Unterschied ist praktisch, nicht
akademisch -- die Speicherseite laesst sich ohne Discord pruefen, diese
nicht.

Zwei Massnahmen, und beide sind heikel genug, dass sie sich langsam
verhalten:

  * **Bann auf allen Servern.** Der Bot bannt die Person ueberall, wo er
    darf. Zwischen den Servern liegt eine kurze Pause, sonst laeuft er
    bei vierzig Servern in Discords Ratenbegrenzung.
  * **Warnung an die Inhaber.** Eine DM an jeden Server-Inhaber, ohne
    dass irgendjemand gebannt wird. Fuer den Fall "schaut euch den mal
    an" -- und weil eine Warnung, die man auch als Bann ausfuehren
    koennte, sonst nie benutzt wird.

Wer den Bann ueberlebt, ist Absicht: Server-Inhaber werden nie gebannt,
und wo der Bot in der Rollenordnung unter der Zielperson steht, kann er
ohnehin nichts tun. Beides wird gemeldet statt still uebergangen.
"""

from __future__ import annotations

import asyncio
import logging

import discord
from discord.ui import ActionRow, Button, Container, LayoutView, TextDisplay

from utils import user_lookup
from utils.emoji import ZBAN

logger = logging.getLogger(__name__)

# Discord erlaubt Baenne grosszuegig, aber nicht unbegrenzt. Ein Viertel
# Sekunde Pause kostet bei vierzig Servern zehn Sekunden und erspart die
# 429er, die sonst die Haelfte der Baenne verschlucken.
PAUSE = 0.25

FARBE_WARNUNG = discord.Color.from_rgb(232, 165, 71)


class WarnungsView(LayoutView):
    """Die DM an einen Server-Inhaber. Components V2, wie der Rest."""

    def __init__(self, *, titel: str, text: str, fusszeile: str,
                 profil_url: str | None = None):
        super().__init__(timeout=None)

        container = Container(accent_color=FARBE_WARNUNG)
        container.add_item(TextDisplay(f"### {titel}"))
        container.add_item(TextDisplay(text))
        container.add_item(TextDisplay(f"-# {fusszeile}"))

        # Der Knopf gehoert IN den Container -- eine ActionRow direkt in
        # der LayoutView rendert ausserhalb der Karte. test_v2_buttons.py
        # prueft das fuer das ganze Repo.
        if profil_url:
            container.add_item(
                ActionRow(
                    Button(
                        label="Profil ansehen",
                        url=profil_url,
                        style=discord.ButtonStyle.link,
                        emoji=ZBAN,
                    )
                )
            )
        self.add_item(container)


async def ban_everywhere(
    bot, user_id: int, *, reason: str, actor: str = "", dry_run: bool = False
) -> dict:
    """
    Die Person auf allen erreichbaren Servern bannen.

    ``dry_run`` fuehrt nichts aus und meldet nur, was passieren wuerde --
    damit die Oberflaeche eine ehrliche Zahl anzeigen kann, bevor
    jemand bestaetigt.
    """
    grund = (reason or "").strip()[:450] or "Kein Grund angegeben."
    voller_grund = f"Globaler Bann: {grund}"

    erfolg: list[dict] = []
    fehler: list[dict] = []
    uebersprungen: list[dict] = []

    for guild in list(bot.guilds):
        member = guild.get_member(user_id)
        if member is None:
            continue

        if guild.owner_id == user_id:
            uebersprungen.append({
                "guild_id": str(guild.id), "guild_name": guild.name,
                "reason": "Die Person ist Inhaber dieses Servers.",
            })
            continue

        me = guild.me
        if me is None or not me.guild_permissions.ban_members:
            uebersprungen.append({
                "guild_id": str(guild.id), "guild_name": guild.name,
                "reason": "Dem Bot fehlt das Recht, zu bannen.",
            })
            continue

        if me.top_role <= member.top_role:
            uebersprungen.append({
                "guild_id": str(guild.id), "guild_name": guild.name,
                "reason": "Die Rolle des Bots steht nicht ueber der der Person.",
            })
            continue

        if dry_run:
            erfolg.append({"guild_id": str(guild.id), "guild_name": guild.name})
            continue

        try:
            await guild.ban(discord.Object(id=user_id), reason=voller_grund,
                            delete_message_seconds=0)
            erfolg.append({"guild_id": str(guild.id), "guild_name": guild.name})
        except discord.Forbidden:
            fehler.append({
                "guild_id": str(guild.id), "guild_name": guild.name,
                "reason": "Discord hat es abgelehnt (fehlende Rechte).",
            })
        except discord.HTTPException as exc:
            fehler.append({
                "guild_id": str(guild.id), "guild_name": guild.name,
                "reason": f"Discord-Fehler: {exc}",
            })
        else:
            await asyncio.sleep(PAUSE)

    if not dry_run:
        await user_lookup.record_action(
            user_id, "ban_all", actor=actor, reason=grund,
            ok_count=len(erfolg), fail_count=len(fehler) + len(uebersprungen),
            detail="; ".join(g["guild_name"] for g in erfolg[:40]),
        )

    return {
        "banned": erfolg,
        "failed": fehler,
        "skipped": uebersprungen,
        "ok_count": len(erfolg),
        "fail_count": len(fehler),
        "skipped_count": len(uebersprungen),
        "dry_run": dry_run,
    }


async def warn_owners(
    bot, user_id: int, *, reason: str, actor: str = "", dry_run: bool = False
) -> dict:
    """
    Jeden Server-Inhaber per DM warnen, ohne etwas zu tun.

    Die Person selbst bekommt nichts -- eine Warnung, die den Gewarnten
    vorwarnt, waere sinnlos.
    """
    grund = (reason or "").strip()[:800] or "Kein Grund angegeben."

    user = bot.get_user(user_id)
    if user is None:
        try:
            user = await bot.fetch_user(user_id)
        except Exception:
            user = None
    name = str(user) if user else f"Unbekannt ({user_id})"

    # Ein Inhaber kann mehrere betroffene Server haben -- er bekommt
    # trotzdem nur eine DM, in der alle stehen.
    betroffen: dict[int, list[str]] = {}
    for guild in list(bot.guilds):
        if guild.get_member(user_id) is None:
            continue
        if guild.owner_id == user_id:
            # Den Inhaber vor sich selbst zu warnen ergibt keinen Sinn.
            continue
        betroffen.setdefault(guild.owner_id, []).append(guild.name)

    erfolg: list[dict] = []
    fehler: list[dict] = []

    for owner_id, server in betroffen.items():
        if dry_run:
            erfolg.append({"owner_id": str(owner_id), "guilds": server})
            continue

        owner = bot.get_user(owner_id)
        if owner is None:
            try:
                owner = await bot.fetch_user(owner_id)
            except Exception:
                fehler.append({"owner_id": str(owner_id),
                               "reason": "Inhaber nicht erreichbar."})
                continue

        liste = "\n".join(f"> {n}" for n in sorted(server)[:25])
        mehr = f"\n> … und {len(server) - 25} weitere" if len(server) > 25 else ""

        view = WarnungsView(
            titel="Hinweis zu einem Mitglied",
            text=(
                f"**{name}** (`{user_id}`) ist auf "
                f"{'deinem Server' if len(server) == 1 else 'deinen Servern'}:\n"
                f"{liste}{mehr}\n\n"
                f"**Grund des Hinweises:**\n{grund}\n\n"
                f"Das ist nur eine Information — es wurde nichts unternommen. "
                f"Ob du etwas tust, entscheidest du."
            ),
            fusszeile="University Bot • Hinweis an Server-Inhaber",
            profil_url=f"https://discord.com/users/{user_id}",
        )

        try:
            # Kein content= -- mit Components V2 lehnt Discord das mit
            # 50035 ab.
            await owner.send(view=view)
            erfolg.append({"owner_id": str(owner_id), "guilds": server})
        except discord.Forbidden:
            fehler.append({"owner_id": str(owner_id),
                           "reason": "Der Inhaber hat seine DMs geschlossen."})
        except discord.HTTPException as exc:
            fehler.append({"owner_id": str(owner_id), "reason": f"Discord: {exc}"})
        else:
            await asyncio.sleep(PAUSE)

    if not dry_run:
        await user_lookup.record_action(
            user_id, "warn_owners", actor=actor, reason=grund,
            ok_count=len(erfolg), fail_count=len(fehler),
            detail=f"{len(betroffen)} Inhaber",
        )

    return {
        "warned": erfolg,
        "failed": fehler,
        "ok_count": len(erfolg),
        "fail_count": len(fehler),
        "owner_count": len(betroffen),
        "dry_run": dry_run,
    }
