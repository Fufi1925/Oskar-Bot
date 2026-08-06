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
Reaktionen, wenn jemand erwaehnt wird.

Die beiden Besitzer stehen weiterhin fest im Code -- ausdruecklich so
gewollt: eine falsche Eingabe im Dashboard soll die eigene
Kennzeichnung nicht abschalten koennen.

Dazu kommt eine Liste, die sich im Admin-Panel pflegen laesst
(``utils/ping_reactions.py``). Steht dort jemand, bekommt seine
Erwaehnung dieselbe Behandlung.
"""

import asyncio

import discord
from discord.ext import commands

from utils.config import OWNER_IDS
from utils.emoji import ACTIVE_DEVELOPER, BLACKCROWN, MINGLE, STAFF

# Die fest verdrahteten Reaktionen der Besitzer.
#
# Als Konstante und nicht mehr inline, damit das Admin-Panel sie
# anzeigen kann: dort steht sonst eine Liste, in der die beiden
# wichtigsten Eintraege fehlen, und niemand versteht, warum der Bot
# trotzdem reagiert.
OWNER_EMOJIS = (BLACKCROWN, ACTIVE_DEVELOPER, STAFF, MINGLE)
CO_OWNER_EMOJIS = (BLACKCROWN, ACTIVE_DEVELOPER, STAFF)


def owner_reactions(user_id: int) -> tuple[str, ...]:
    """Was ein Besitzer bekommt -- oder nichts."""

    if not OWNER_IDS:
        return ()
    if user_id == OWNER_IDS[0]:
        return OWNER_EMOJIS
    if user_id in OWNER_IDS:
        return CO_OWNER_EMOJIS
    return ()


class React(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self._connection = None

    async def cog_load(self) -> None:
        import aiosqlite

        from utils import ping_reactions as store

        try:
            self._connection = await aiosqlite.connect(store.DB_PATH)
            await store.ensure_schema(self._connection)
            await store.load(self._connection, force=True)
        except Exception as exc:  # noqa: BLE001
            # Die eigene Liste ist eine Zugabe. Laesst sie sich nicht
            # oeffnen, reagiert der Bot eben nur auf die Besitzer --
            # das ist besser, als das Modul gar nicht zu laden.
            print(f"[react] Ping-Reaktionen nicht geladen: {exc}")

    async def cog_unload(self) -> None:
        from utils import ping_reactions as store

        store.reset()
        if self._connection is not None:
            await self._connection.close()

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        from utils import ping_reactions as store

        # Wen erwaehnt diese Nachricht?
        #
        # Frueher lief hier eine Schleife ueber alle Besitzer und suchte
        # `f"<@{owner}>"` im Text. Das uebersieht die zweite Schreibweise:
        # Discord schickt eine Erwaehnung als `<@123>` *oder* `<@!123>`,
        # je nachdem, ob die Person einen Servernamen gesetzt hat.
        # `message.mentions` kennt beide -- und ist ausserdem billiger
        # als eine Textsuche pro Eintrag.
        mentioned = {user.id for user in message.mentions}
        if not mentioned:
            return

        emojis: list[str] = []
        for user_id in mentioned:
            for emoji in owner_reactions(user_id):
                if emoji not in emojis:
                    emojis.append(emoji)
            for emoji in store.reactions_for(user_id):
                if emoji not in emojis:
                    emojis.append(emoji)

        if not emojis:
            return

        # Discord nimmt hoechstens zwanzig verschiedene Reaktionen pro
        # Nachricht. Werden mehrere Leute auf einmal erwaehnt, kaeme man
        # darueber -- und die letzten scheiterten einzeln mit einem
        # Fehler, den niemand sieht.
        emojis = emojis[: store.MAX_REACTIONS]

        try:
            for emoji in emojis:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    pass  # ignore if emoji is invalid or not accessible
        except discord.errors.RateLimited as exc:
            await asyncio.sleep(exc.retry_after)
        except Exception as exc:  # noqa: BLE001
            print(f"An unexpected error occurred Auto react owner mention: {exc}")
