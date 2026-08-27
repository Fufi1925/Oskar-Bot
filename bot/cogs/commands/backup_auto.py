"""
Die automatische Sicherung.

Ein Durchlauf jede Viertelstunde: er fragt, welche Server faellig
sind, und legt fuer die eine Sicherung an. Der eingestellte Abstand
steht je Server in `guild_backup.backup_auto`.

Warum nicht ein Timer je Server
-------------------------------
Bei 154 Servern waeren das 154 Tasks, die 23 Stunden am Tag schlafen.
Ein Durchlauf, der eine Liste abfragt, kostet nichts und kennt keine
verwaisten Timer nach einem Neustart.

Warum jede Viertelstunde
------------------------
Der kuerzeste einstellbare Abstand ist sechs Stunden. Eine
Viertelstunde Ungenauigkeit faellt dabei nicht auf, und der Durchlauf
laeuft 96-mal am Tag statt 1440-mal.
"""

from __future__ import annotations

import asyncio
import logging

from discord.ext import commands, tasks

from utils import backup_runner
from utils import guild_backup as store

LOGGER = logging.getLogger("universitybot.backup")


class BackupAuto(commands.Cog):
    """Legt automatische Sicherungen an."""

    def __init__(self, bot):
        self.bot = bot
        self.durchlauf.start()

    def cog_unload(self):
        self.durchlauf.cancel()

    @tasks.loop(minutes=15)
    async def durchlauf(self):
        try:
            faellig = store.auto_faellige()
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Automatik: Liste nicht lesbar: %s", exc)
            return

        for eintrag in faellig:
            guild_id = int(eintrag["guild_id"])
            guild = self.bot.get_guild(guild_id)

            if guild is None:
                # Der Bot ist nicht mehr drauf. Den Zeitpunkt trotzdem
                # vermerken, sonst versucht es jeder Durchlauf erneut.
                store.auto_lauf_vermerkt(
                    guild_id, fehler="Der Bot ist nicht mehr auf dem Server."
                )
                continue

            await self._sichere(guild, eintrag)

            # Zwischen zwei Servern eine Pause: mehrere Sicherungen
            # gleichzeitig waeren eine Anfragewelle an Discord.
            await asyncio.sleep(2)

    async def _sichere(self, guild, eintrag: dict) -> None:
        guild_id = int(guild.id)
        try:
            # Ist das Fach voll? Dann entweder aufraeumen oder
            # aussetzen -- je nach Einstellung.
            #
            # Premium wird hier NICHT erneut geprueft: die Automatik
            # laesst sich nur mit Premium einschalten, und wer sie
            # eingeschaltet hat, soll nicht mitten in der Nacht
            # stillschweigend aufhoeren, weil eine Lizenz auslaeuft.
            # Die Grenze greift trotzdem.
            grenze = store.MAX_PREMIUM
            if store.anzahl(guild_id) >= grenze:
                if not eintrag.get("alte_loeschen"):
                    store.auto_lauf_vermerkt(
                        guild_id,
                        fehler=(
                            f"Alle {grenze} Plätze belegt. Schalte "
                            "„älteste löschen“ ein oder räum auf."
                        ),
                    )
                    return
                store.loesche_aelteste(guild_id, behalte=grenze - 1)

            inhalt = await backup_runner.erstelle(
                self.bot, guild,
                mit_nachrichten=bool(eintrag.get("mit_nachrichten")),
                max_nachrichten=store.MAX_NACHRICHTEN,
            )
            gespeichert = store.speichere(
                guild_id, inhalt,
                erstellt_von="auto",
                quelle="auto",
                mit_nachrichten=bool(eintrag.get("mit_nachrichten")),
                notiz="Automatisch",
            )
            store.auto_lauf_vermerkt(guild_id)
            LOGGER.info(
                "Automatische Sicherung für %s: %s",
                guild_id, gespeichert["kennung"],
            )
        except Exception as exc:  # noqa: BLE001
            # Der Zeitpunkt wird AUCH bei einem Fehler vermerkt.
            # Sonst versucht die Automatik es alle 15 Minuten erneut
            # und laeuft bei einem dauerhaften Problem gegen die Wand.
            store.auto_lauf_vermerkt(guild_id, fehler=str(exc)[:300])
            LOGGER.warning("Automatische Sicherung für %s: %s", guild_id, exc)

    @durchlauf.before_loop
    async def warte_auf_bot(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(BackupAuto(bot))
