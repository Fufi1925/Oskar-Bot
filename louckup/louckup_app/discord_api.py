"""Die paar Discord-Endpunkte, die der Bereich braucht.

Alles hier laeuft mit **Bot-Tokens**. Das ist der entscheidende Punkt
fuer die Suche: ein Bot-Token sieht oeffentliche Profile und, fuer die
eigenen Server, die Mitgliedschaft samt Rollen. Es sieht **keine**
E-Mail-Adressen und keine Server, in denen der Bot nicht ist — dafuer
brauchte es das OAuth-Token der betroffenen Person, und das ruehren wir
nicht an.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

DISCORD_API = "https://discord.com/api/v10"

# Bekannte Abzeichen aus public_flags. Nur die, die man auch zeigen kann.
ABZEICHEN = (
    (1 << 0, "Discord-Mitarbeiter"),
    (1 << 1, "Partner"),
    (1 << 2, "HypeSquad"),
    (1 << 3, "Bug-Jäger"),
    (1 << 6, "HypeSquad Bravery"),
    (1 << 7, "HypeSquad Brilliance"),
    (1 << 8, "HypeSquad Balance"),
    (1 << 9, "Früher Supporter"),
    (1 << 16, "Verifizierter Bot"),
    (1 << 17, "Verifizierter Entwickler"),
    (1 << 18, "Zertifizierter Moderator"),
    (1 << 22, "Aktiver Entwickler"),
)


def abzeichen(flags: int | None) -> list[str]:
    if not flags:
        return []
    return [name for bit, name in ABZEICHEN if flags & bit]


def kontostand_aus_snowflake(user_id: int):
    """Erstellungsdatum eines Kontos aus seiner ID."""
    import datetime

    try:
        ms = (int(user_id) >> 22) + 1420070400000
        return datetime.datetime.fromtimestamp(ms / 1000)
    except Exception:
        return None


class AnfrageFehler(RuntimeError):
    def __init__(self, status: int, text: str = ""):
        super().__init__(f"HTTP {status} {text}".strip())
        self.status = status


def _kopf(token: str) -> dict[str, str]:
    # Bot-Tokens brauchen das Praefix "Bot ", sonst 401.
    sauber = token.strip()
    if not sauber.lower().startswith("bot "):
        sauber = f"Bot {sauber}"
    return {"Authorization": sauber, "User-Agent": "Louckup (self-hosted)"}


async def _hole(token: str, pfad: str, zeitlimit: float = 12.0) -> Any:
    async with httpx.AsyncClient(timeout=zeitlimit) as client:
        antwort = await client.get(f"{DISCORD_API}{pfad}", headers=_kopf(token))
        if antwort.status_code == 429:
            raise AnfrageFehler(429, "von Discord gebremst (429)")
        if antwort.status_code >= 400:
            raise AnfrageFehler(antwort.status_code, antwort.text[:120])
        if antwort.status_code == 204:
            return None
        return antwort.json()


async def bot_selbst(token: str, zeitlimit: float = 12.0) -> dict[str, Any] | None:
    """/users/@me — zeigt, ob der Token ueberhaupt funktioniert."""
    return await _hole(token, "/users/@me", zeitlimit)


async def anwendung(token: str, zeitlimit: float = 12.0) -> dict[str, Any] | None:
    """/oauth2/applications/@me — der Name der Application."""
    try:
        return await _hole(token, "/oauth2/applications/@me", zeitlimit)
    except AnfrageFehler:
        return None


async def profil(token: str, user_id: int, zeitlimit: float = 12.0) -> dict[str, Any] | None:
    """/users/{id} — oeffentliches Profil. Keine E-Mail, bewusst."""
    try:
        return await _hole(token, f"/users/{user_id}", zeitlimit)
    except AnfrageFehler as fehler:
        if fehler.status == 404:
            return None
        raise


async def bot_server(token: str, zeitlimit: float = 12.0) -> list[dict[str, Any]]:
    """/users/@me/guilds — die Server, in denen der Bot steckt."""
    daten = await _hole(token, "/users/@me/guilds", zeitlimit)
    return daten if isinstance(daten, list) else []


async def mitglied(
    token: str, guild_id: int, user_id: int, zeitlimit: float = 12.0
) -> dict[str, Any] | None:
    """/guilds/{gid}/members/{uid} — Mitgliedschaft mit Rollen."""
    try:
        return await _hole(token, f"/guilds/{guild_id}/members/{user_id}", zeitlimit)
    except AnfrageFehler as fehler:
        if fehler.status == 404:  # nicht auf diesem Server — kein Fehler
            return None
        raise


async def rollen(token: str, guild_id: int, zeitlimit: float = 12.0) -> dict[int, str]:
    """/guilds/{gid}/roles — Rollennamen fuer die Anzeige."""
    try:
        daten = await _hole(token, f"/guilds/{guild_id}/roles", zeitlimit)
    except AnfrageFehler:
        return {}
    if not isinstance(daten, list):
        return {}
    return {int(r["id"]): r.get("name", "?") for r in daten if r.get("id")}


async def avatar_url(user: dict[str, Any]) -> str | None:
    avatar = user.get("avatar")
    if not avatar:
        return None
    endung = "gif" if str(avatar).startswith("a_") else "png"
    return f"https://cdn.discordapp.com/avatars/{user.get('id')}/{avatar}.{endung}?size=128"
