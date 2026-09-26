# ╔══════════════════════════════════════════════════════════════════╗
# ║                                                                  ║
# ║   ░█▀▀░█▀█░█▀▄░█▀▀░█░█   ░█▀▄░█▀▀░█░█░█▀▀                     ║
# ║   ░█░░░█░█░█░█░█▀▀░▄▀▄   ░█░█░█▀▀░▀▄▀░▀▀█                     ║
# ║   ░▀▀▀░▀▀▀░▀▀░░▀▀▀░▀░▀   ░▀▀░░▀▀▀░░▀░░▀▀▀                     ║
# ║                                                                  ║
# ║            © 2026 University Bot Devs — All Rights Reserved              ║
# ║                                                                  ║
# ║   discord  ──  https://discord.gg/F3TedBAVZT                      ║
# ║   youtube  ──  https://youtube.com/@UniversityBotDevs                   ║
# ║   github   ──  https://github.com/UniversityBot                        ║
# ║                                                                  ║
# ╚══════════════════════════════════════════════════════════════════╝

import os
from dotenv import load_dotenv

load_dotenv()

#: Der eine Name.
MARKE = "University Bot"

#: Schreibweisen, die nur Varianten des Namens sind. Sie werden nach
#: derselben Regel umgerechnet wie die Eingabe -- eine Menge mit Umlauten
#: würde sonst nie getroffen, weil die Eingabe vorher aufgelöst wird.
_MARKE_ROHVARIANTEN = (
    "UniversityBot", "Universitätsbot", "Universität-Bot", "University Bot",
    "Uni Bot", "UB", "Oskar Bot", "Oskar-Bot", "universitybot X",
)


def _schluessel(wert: str) -> str:
    return (
        (wert or "")
        .strip()
        .lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
        .replace("ß", "ss")
        .replace("-", "").replace(" ", "")
    )


_MARKE_VARIANTEN = {_schluessel(v) for v in _MARKE_ROHVARIANTEN}


def _marke(wert: str | None) -> str:
    """Eine Schreibweise des Namens auf den Namen zurueckfuehren.

    Leerzeichen, Bindestriche, Groessen und Umlaute sind nur Varianten
    desselben Namens, keine eigene Marke. Was ein wirklich anderer Name
    ist, bleibt stehen -- die Vorgabe ist aber immer der eine Name.
    """
    roh = (wert or "").strip()
    if not roh:
        return MARKE
    return MARKE if _schluessel(roh) in _MARKE_VARIANTEN else roh


TOKEN      = os.environ.get("TOKEN")
# Der Name des Bots. Er wird nicht uebersetzt -- "Universitaetsbot" ist
# eine Uebersetzung des Namens und damit ein zweiter Name fuer dasselbe.
# Die alte Vorgabe "universitybot X" war ein Rest einer Umbenennung und
# stand so in Hilfetexten, Einbettungen und den Cog-Meldungen.
BRAND_NAME = _marke(os.environ.get("BRAND_NAME") or os.environ.get("brand_name"))
NAME       = BRAND_NAME
BotName    = BRAND_NAME

server     = "https://discord.gg/F3TedBAVZT"
serverLink = "https://discord.gg/F3TedBAVZT"
ch         = "https://discord.com/channels/699587669059174461/1271825678710476911"

CMD_WEBHOOK_URL = os.getenv("CMD_WEBHOOK_URL")

# ── Owner / Staff IDs ─────────────────────────────────────────────────────────
# Edit OWNER_IDS in .env — comma-separated, no spaces needed.
# Example:  OWNER_IDS = 870179991462236170,767979794411028491,1432771000629596225

def _parse_ids(env_key: str, defaults: list[int]) -> list[int]:
    raw = os.getenv(env_key, "").strip()
    if not raw:
        return defaults
    ids = [int(p.strip()) for p in raw.split(",") if p.strip().isdigit()]
    return ids or defaults

OWNER_IDS:     list[int] = _parse_ids("OWNER_IDS",     [870179991462236170])
OWNER_IDS_STR: list[str] = [str(i) for i in OWNER_IDS]

# Aliases kept for backwards compatibility with files that import these names
BOT_OWNER_IDS     = OWNER_IDS
BOT_OWNER_IDS_STR = OWNER_IDS_STR
STAFF_IDS         = OWNER_IDS
STAFF_IDS_STR     = OWNER_IDS_STR