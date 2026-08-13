# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 UniversityBot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Schreibt den täglichen Verlauf jedes Servers mit.

Zwei Wege, und beide werden gebraucht
-------------------------------------
1. **Auf Ereignisse hören.** Jeder Beitritt und jeder Austritt wird
   sofort gezählt. Nur so lässt sich später sagen, ob ein Tag mit
   gleicher Mitgliederzahl ruhig war oder ob dreißig Leute kamen und
   dreißig gingen.

2. **Alle 30 Minuten nachmessen.** Nicht als Ersatz: als Korrektur.
   Ein verpasstes Gateway-Ereignis, ein Neustart, ein Server, der
   nach einem Ausfall neu geladen wird -- eine fortgeschriebene Summe
   liefe danach dauerhaft daneben, der gemessene Stand nicht.

Warum der Schnappschuss auch beim Start läuft
---------------------------------------------
Ohne ihn hätte ein Server, der heute keinen einzigen Beitritt hat,
für heute gar keine Zeile -- und das Diagramm zöge eine Lücke durch
den heutigen Tag, obwohl der Bot die ganze Zeit lief. Genau die
Verwechslung soll die Lücke ja verhindern.

Kosten
------
Ein UPDATE pro Beitritt und eine kleine Schleife alle 30 Minuten. Bei
52 Servern sind das 52 Zeilen pro halbe Stunde; die Datei wächst um
etwa 2 MB im Jahr.
"""

import asyncio

import discord
from discord.ext import commands, tasks

from core import Cog, universitybot
from utils import guild_history as store

# Wie oft nachgemessen wird. 30 Minuten sind fein genug für eine
# Tageskurve und grob genug, um nicht aufzufallen.
SNAPSHOT_MINUTEN = 30


class GuildHistory(Cog):
    def __init__(self, client: universitybot):
        self.client = client
        self.snapshot_loop.start()

    def cog_unload(self):
        self.snapshot_loop.cancel()

    # ── Die Ereignisse ───────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild is None:
            return
        try:
            await store.record_join(member.guild.id, _mitglieder(member.guild))
        except Exception as error:
            # Buchhaltung darf nie einen Beitritt stören.
            print(f"[guild_history] Beitritt nicht gezaehlt: {error}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.guild is None:
            return
        try:
            await store.record_leave(member.guild.id, _mitglieder(member.guild))
        except Exception as error:
            print(f"[guild_history] Austritt nicht gezaehlt: {error}")

    # ── Das Netz darunter ────────────────────────────────────────

    @tasks.loop(minutes=SNAPSHOT_MINUTEN)
    async def snapshot_loop(self):
        """Für jeden Server den aktuellen Stand festhalten."""
        for guild in list(self.client.guilds):
            try:
                await store.snapshot(guild.id, _mitglieder(guild))
            except Exception as error:
                print(f"[guild_history] Schnappschuss {guild.id}: {error}")
            # Bei vielen Servern nicht die Schleife blockieren.
            await asyncio.sleep(0)

        # Einmal pro Runde aufräumen ist oft genug -- die Grenze liegt
        # bei über einem Jahr, da kommt es auf eine halbe Stunde nicht an.
        try:
            await store.prune()
        except Exception:
            pass

    @snapshot_loop.before_loop
    async def vor_dem_start(self):
        # Vor `wait_until_ready` ist `client.guilds` leer, und der
        # erste Schnappschuss wäre eine Runde über nichts.
        await self.client.wait_until_ready()


def _mitglieder(guild) -> int:
    """Die belastbarste Mitgliederzahl, die gerade zu haben ist.

    `guild.member_count` kommt vom Gateway und ist direkt nach einem
    Neustart manchmal None. Dann ist die Länge der zwischen-
    gespeicherten Liste immer noch besser als eine Null im Diagramm.
    """
    if guild is None:
        return 0
    count = getattr(guild, "member_count", None)
    if count:
        return int(count)
    cached = len(getattr(guild, "members", ()) or ())
    if cached:
        return cached
    return int(getattr(guild, "approximate_member_count", 0) or 0)
