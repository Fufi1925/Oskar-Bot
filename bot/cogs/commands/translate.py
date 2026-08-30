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

import discord
from discord.ext import commands
import httpx
from discord.ui import LayoutView, TextDisplay, Separator, Container
from utils.cv2 import CV2, build_container

# Hinglish -> Englisch.
#
# Bis hierher lief das ueber das Paket `deep-translator`. Fuer dessen
# gemeldete Luecke (PYSEC-2022-252) gibt es keinen gepatchten Release --
# 1.11.4 ist die neueste Version, die es gibt --, und Sicherheitswarnungen,
# die man nicht schliessen kann, bleiben fuer immer rot. Also ist das
# Paket rausgeflogen und der Aufruf geht direkt an denselben Endpunkt,
# den es benutzt hat. httpx ist ohnehin eine Abhaengigkeit des Bots.
GOOGLE_TRANSLATE = "https://translate.googleapis.com/translate_a/single"

# Ohne Browser-Kennung antwortet der Endpunkt aus Rechenzentren
# regelmaessig mit 429. deep-translator hat denselben Trick benutzt.
KENNUNG = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

# Google mag keine endlos langen GET-Requests, darum in Haeppchen.
TEIL_LAENGE = 450


def _teilen(text: str) -> list[str]:
    """Text in Stuecke von hoestens TEIL_LAENGE Zeichen zerlegen."""
    stuecke, aktuell = [], ""
    for wort in text.split():
        if len(aktuell) + len(wort) + 1 > TEIL_LAENGE:
            if aktuell:
                stuecke.append(aktuell)
            aktuell = wort
        else:
            aktuell = f"{aktuell} {wort}".strip()
    if aktuell:
        stuecke.append(aktuell)
    return stuecke or [text]


async def uebersetzen(text: str, ziel: str = "en") -> str:
    """Uebersetzt ueber den oeffentlichen Google-Endpunkt.

    Wirft bei Netzwerk- oder Antwortfehlern -- der Aufrufer faengt das
    und zeigt die gewohnte Fehlermeldung.
    """
    ergebnis = []
    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": KENNUNG}) as client:
        for teil in _teilen(text):
            antwort = await client.get(
                GOOGLE_TRANSLATE,
                params={"client": "gtx", "sl": "auto", "tl": ziel, "dt": "t", "q": teil},
            )
            if antwort.status_code == 429:
                # Kein Fehler im Code, sondern Google wehrt sich gegen zu
                # viele Anfragen von dieser Adresse. Dem Nutzer hilft
                # nur: spaeter nochmal.
                raise RuntimeError("Google blockt gerade Anfragen (429). Bitte spaeter nochmal.")
            antwort.raise_for_status()
            daten = antwort.json()
            zeilen = daten[0] if isinstance(daten, list) and daten else []
            ergebnis.append(
                "".join(
                    st[0]
                    for st in zeilen
                    if isinstance(st, list) and st and isinstance(st[0], str)
                )
            )
    return "".join(ergebnis).strip() or text


class TranslateSuccess(LayoutView):
    def __init__(self, original, translated, author):
        super().__init__(timeout=None)
        self.add_item(
            build_container(
                TextDisplay("🌐 **Translation Complete**"),
                Separator(visible=True),
                TextDisplay(f"**Original (Hinglish):**\n{original}"),
                Separator(visible=True),
                TextDisplay(f"**Translated (English):**\n{translated}"),
                Separator(visible=True),
                TextDisplay(f"Requested by **{author.display_name}**")
            )
        )

class TranslateError(LayoutView):
    def __init__(self, error_msg):
        super().__init__(timeout=None)
        self.add_item(
            build_container(
                TextDisplay("❌ **Translation Failed**"),
                Separator(visible=True),
                TextDisplay(f"`{error_msg}`")
            )
        )

class TranslateCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Prefix-only: Hinglish to English has no audience on a German
    # server, so it does not earn a slot in the slash menu. !hinglish
    # still works for anyone who wants it.
    @commands.command(
        name="hinglish",
        help="Translate informal Hinglish to proper English.",
        usage="!hinglish chlo udhr chat active krlo idhr nai"
    )
    async def hinglish(self, ctx: commands.Context, *, text: str = None):
        if not text:
            return await ctx.reply(
                "⚠️ Please provide some Hinglish text to translate.",
                ephemeral=True if ctx.interaction else False
            )

        msg = await ctx.reply(
            "🔄 Translating Hinglish...",
            ephemeral=True if ctx.interaction else False
        )

        try:
            # Uebersetzung direkt ueber Google (siehe uebersetzen())
            translated = await uebersetzen(text, "en")
            
            view = TranslateSuccess(text, translated, ctx.author)
            await msg.edit(content=None, view=view, embed=None)

        except Exception as e:
            view = TranslateError(str(e))
            await msg.edit(content=None, view=view, embed=None)

async def setup(bot):
    await bot.add_cog(TranslateCog(bot))
