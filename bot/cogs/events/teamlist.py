# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/MG3rYnUZJV                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Haelt die Teamliste aktuell.

Zwei Wege, bewusst beide
------------------------
1. **Auf Ereignisse hoeren.** Bekommt jemand eine Rolle, wird die
   Liste ein paar Sekunden spaeter neu geschrieben. Das ist der
   schnelle Weg -- und der, der sich fuer den Nutzer nach "live"
   anfuehlt.

2. **Alle 15 Minuten nachsehen.** Nicht als Ersatz, sondern als Netz
   darunter. Ein Neustart mitten in einer Aenderung, ein verpasstes
   Gateway-Ereignis, ein Mitglied, das nicht im Zwischenspeicher war:
   dann stuende die Liste sonst dauerhaft falsch da, ohne dass es
   jemand merkt.

Warum auf mehrere Ereignisse gehoert wird
-----------------------------------------
`on_member_update` deckt den Hauptfall ab (Rolle bekommen oder
verloren). Aber:

  * `on_member_remove` -- wer den Server verlaesst, verschwindet ohne
    ein Update-Ereignis.
  * `on_guild_role_delete` -- eine geloeschte Rolle laesst eine leere
    Gruppe zurueck.
  * `on_guild_role_update` -- eine umbenannte Rolle braucht eine neue
    Ueberschrift, wenn die Gruppe keine eigene Beschriftung hat.

Ohne diese drei blieben genau die Faelle stehen, bei denen jemand
zusieht und sich fragt, warum sich nichts tut.
"""

import asyncio

import discord
from discord.ext import commands, tasks

from core import Cog, universitybot
from utils import teamlist_render as renderer
from utils import teamlist_store as store


class TeamList(Cog):
    def __init__(self, client: universitybot):
        self.client = client
        self.refresh_loop.start()

    def cog_unload(self):
        self.refresh_loop.cancel()

    # ── Der Hauptfall: eine Rolle kommt oder geht ────────────────

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Nur bei Rollenaenderungen. `on_member_update` feuert auch bei
        # Spitznamen, Zeitstrafen und Server-Avataren -- bei einem
        # grossen Server waeren das hunderte Aufrufe pro Minute, von
        # denen keiner die Teamliste betrifft.
        if set(before.roles) == set(after.roles):
            return

        await self._maybe_refresh(after.guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        # Wer den Server verlaesst, loest kein Update aus -- taucht
        # aber weiter in der Liste auf, bis jemand nachsieht.
        await self._maybe_refresh(member.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await self._maybe_refresh(role.guild)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        # Nur der Name zaehlt hier: eine Gruppe ohne eigene
        # Beschriftung zeigt ihn als Ueberschrift. Farbe oder Rechte
        # aendern nichts an der Liste.
        if before.name == after.name:
            return
        await self._maybe_refresh(after.guild)

    async def _maybe_refresh(self, guild) -> None:
        """Auffrischen -- aber nur, wenn dieser Server eine Liste hat.

        Die Pruefung ist billig (eine Zeile aus einer kleinen Tabelle)
        und spart bei allen anderen Servern den ganzen Aufbau.
        """

        if guild is None:
            return

        try:
            from api.db_manager import db_manager

            db = await db_manager.get_connection(store.DB_PATH)
            await store.ensure_schema(db)
            config = await store.get_config(db, int(guild.id))
        except Exception as error:
            print(f"[teamlist] Konnte Einstellungen nicht lesen: {error}")
            return

        if not config.get("enabled") or not config.get("channel_id"):
            return

        # `schedule` sammelt mehrere Aenderungen zu einer Auffrischung.
        renderer.schedule(self.client, int(guild.id))

    # ── Das Netz darunter ────────────────────────────────────────

    @tasks.loop(seconds=store.REFRESH_SECONDS)
    async def refresh_loop(self):
        """Alle eingeschalteten Teamlisten neu schreiben."""

        try:
            from api.db_manager import db_manager

            db = await db_manager.get_connection(store.DB_PATH)
            await store.ensure_schema(db)
            guild_ids = await store.all_enabled(db)
        except Exception as error:
            print(f"[teamlist] Auffrischungsrunde fehlgeschlagen: {error}")
            return

        for guild_id in guild_ids:
            try:
                await renderer.refresh_guild(self.client, guild_id)
            except Exception as error:
                # Ein Server, der nicht geht, darf die anderen nicht
                # aufhalten.
                print(f"[teamlist] {guild_id}: {error}")
            # Kurz Luft holen: bei fuenfzig Servern waeren fuenfzig
            # Bearbeitungen am Stueck ein Fall fuer Discords Bremse.
            await asyncio.sleep(1.0)

    @refresh_loop.before_loop
    async def before_refresh(self):
        # Ohne das laeuft die erste Runde, bevor der Bot seine Server
        # kennt -- und findet keinen einzigen.
        await self.client.wait_until_ready()


# Kein eigenes `setup()`: dieses Paket laedt seine Cogs ueber
# `cogs/__init__.py`, das jeden einzeln importiert und per `add_cog`
# anmeldet. Ein `setup()` hier waere tote Schnittstelle -- und der Cog
# waere trotzdem nicht geladen, weil discord.py nur das Paket
# `cogs` als Erweiterung kennt.
