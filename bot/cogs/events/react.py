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

# Die mitgelieferten Reaktionen der Besitzer.
#
# Sie sind der **Standard**, nicht mehr das letzte Wort: seit dem
# Admin-Reiter laesst sich jede davon ueberschreiben, abschalten und
# wieder auf diesen Stand zuruecksetzen.
#
# Im Code bleiben sie trotzdem, und zwar aus einem Grund: eine leere
# oder verlorene Datenbank soll nicht dazu fuehren, dass die
# Kennzeichnung stillschweigend verschwindet. Ohne gespeicherte
# Aenderung gilt genau das hier.
OWNER_EMOJIS = (BLACKCROWN, ACTIVE_DEVELOPER, STAFF, MINGLE)
CO_OWNER_EMOJIS = (BLACKCROWN, ACTIVE_DEVELOPER, STAFF)


def default_owner_reactions(user_id: int) -> tuple[str, ...]:
    """Der mitgelieferte Stand fuer diese ID -- ohne Ruecksicht auf das Panel.

    Braucht das Dashboard, um "zuruecksetzen" anbieten zu koennen: es
    muss zeigen koennen, worauf zurueckgesetzt wird.
    """

    if not OWNER_IDS:
        return ()
    if user_id == OWNER_IDS[0]:
        return OWNER_EMOJIS
    if user_id in OWNER_IDS:
        return CO_OWNER_EMOJIS
    return ()


def owner_reactions(user_id: int) -> tuple[str, ...]:
    """Was ein Besitzer *jetzt* bekommt -- Panel schlaegt Code.

    Die drei Faelle von ``override_for`` bedeuten Verschiedenes und
    duerfen nicht zusammenfallen:

      ``None``  nichts gespeichert -> der mitgelieferte Stand.
      ``[]``    gespeichert, aber pausiert -> ausdruecklich nichts.
      Liste     genau diese Emojis.

    Wuerde hier nur auf "ist die Liste leer" geprueft, waere das
    Pausieren einer Besitzer-Regel wirkungslos: der Code-Standard kaeme
    sofort zurueck, und im Panel saehe es aus, als haette der Schalter
    nicht funktioniert.
    """

    from utils import ping_reactions as store

    override = store.override_for(user_id)
    if override is not None:
        return tuple(override)

    return default_owner_reactions(user_id)


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
        # Eine Quelle pro Person, nicht zwei.
        #
        # `owner_reactions()` liest die Ueberschreibung selbst und
        # faellt nur ohne gespeicherte Zeile auf den Code-Stand zurueck.
        # Zusaetzlich noch `reactions_for()` abzufragen wuerde dieselben
        # Emojis ein zweites Mal einsammeln -- und bei einem pausierten
        # Besitzer waere die Reihenfolge der beiden Aufrufe plötzlich
        # entscheidend. Deshalb hier genau ein Aufruf.
        for user_id in mentioned:
            wanted = owner_reactions(user_id)
            if not wanted:
                wanted = store.reactions_for(user_id)
            for emoji in wanted:
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
