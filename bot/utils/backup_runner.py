"""
Sichern und Wiederherstellen -- der Teil, der Discord anfasst.

Getrennt von `guild_backup.py`: dort steht der Speicher, hier die
Arbeit. Der Speicher laesst sich damit ohne laufenden Bot testen.

Discord-Grenzen
---------------
Die Schnittstelle bremst. Kanaele und Rollen anzulegen kostet je einen
Aufruf, Nachrichten kommen in Hundertergruppen. Deshalb:

* Zwischen den Schritten wird gewartet (:data:`PAUSE`). Ohne das
  antwortet Discord irgendwann mit 429 und einer Sperre von mehreren
  Sekunden -- die Gesamtdauer wird dadurch laenger, nicht kuerzer.
* `discord.py` haelt sich selbst an die Grenzen, aber nur je Route.
  Eine eigene Pause zusaetzlich ist die guenstigere Versicherung.
* Nachrichten laufen im Hintergrund, nie im Web-Aufruf: 500 Stueck bei
  50 Kanaelen sind 250 Anfragen, und kein Browser wartet so lange.

Was beim Wiederherstellen NICHT geht
------------------------------------
Nachrichten lassen sich nicht als ihr urspruenglicher Autor
wiederherstellen -- Discord erlaubt das keinem Bot. Sie werden per
Webhook mit Name und Bild des Autors neu gepostet. Das sieht aus wie
vorher, ist aber eine neue Nachricht mit neuem Datum. Genau so steht
es auch in der Oberflaeche.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

LOGGER = logging.getLogger("universitybot.backup")

#: Pause zwischen zwei schreibenden Aufrufen.
PAUSE = 0.35

#: Pause zwischen zwei Nachrichten-Bloecken beim Lesen.
PAUSE_LESEN = 0.25

#: Pause zwischen zwei per Webhook geposteten Nachrichten.
#:
#: Webhooks haben ein eigenes Limit (5 je 2 Sekunden je Webhook).
#: 0,45 s liegt sicher darunter und laesst Luft fuer Schwankungen.
PAUSE_WEBHOOK = 0.45


async def erstelle(bot, guild, *, mit_nachrichten: bool = False,
                   max_nachrichten: int = 500,
                   fortschritt: Optional[Callable[[str], None]] = None) -> dict:
    """Den Server einlesen.

    Struktur und Einstellungen kommen aus `template_scan` -- es gibt
    keinen zweiten Scanner. Nachrichten nur auf Wunsch.
    """
    from utils import template_scan

    def melde(text: str) -> None:
        if fortschritt:
            try:
                fortschritt(text)
            except Exception:  # noqa: BLE001 - eine Anzeige darf nichts kippen
                pass

    melde("Aufbau und Einstellungen werden gelesen")
    inhalt = await template_scan.build_payload(guild, include_features=True)

    # Der Servername gehoert dazu: beim Wiederherstellen auf einen
    # leeren Server will man ihn zurueck.
    inhalt["guild"] = {
        "name": getattr(guild, "name", ""),
        "icon": str(guild.icon.url) if getattr(guild, "icon", None) else None,
    }

    if not mit_nachrichten:
        return inhalt

    melde("Nachrichten werden gelesen — das dauert")
    inhalt["messages"] = await _lies_nachrichten(
        guild, max_nachrichten, melde
    )
    return inhalt


async def _lies_nachrichten(guild, grenze: int, melde) -> dict:
    """Die letzten `grenze` Nachrichten je Textkanal.

    Fehler je Kanal werden uebersprungen, nicht hochgereicht: ein
    Kanal ohne Leserecht darf nicht die ganze Sicherung verhindern.
    """
    import discord

    ergebnis: dict[str, list[dict]] = {}
    kanaele = [
        k for k in getattr(guild, "text_channels", [])
        if k.permissions_for(guild.me).read_message_history
    ]

    for nummer, kanal in enumerate(kanaele, 1):
        melde(f"Nachrichten {nummer}/{len(kanaele)}: #{kanal.name}")
        gesammelt: list[dict] = []
        try:
            async for nachricht in kanal.history(limit=grenze):
                # Systemnachrichten („X ist beigetreten") lassen sich
                # nicht nachbauen und waeren beim Wiederherstellen
                # nur Rauschen.
                if nachricht.type is not discord.MessageType.default:
                    continue
                if not nachricht.content and not nachricht.attachments:
                    continue

                gesammelt.append({
                    "autor": nachricht.author.display_name,
                    "autor_id": str(nachricht.author.id),
                    "avatar": (
                        str(nachricht.author.display_avatar.url)
                        if nachricht.author.display_avatar else ""
                    ),
                    "inhalt": (nachricht.content or "")[:1900],
                    "zeit": int(nachricht.created_at.timestamp()),
                    # Nur die Adressen: die Dateien selbst mitzunehmen
                    # waere ein Vielfaches an Speicher, und Discord
                    # loescht sie ohnehin mit dem Kanal.
                    "anhaenge": [a.url for a in nachricht.attachments][:5],
                })
        except discord.Forbidden:
            LOGGER.info("Kanal #%s: kein Leserecht, uebersprungen", kanal.name)
            continue
        except discord.HTTPException as exc:
            LOGGER.warning("Kanal #%s: %s", kanal.name, exc)
            continue

        if gesammelt:
            # Umgekehrt: `history` liefert neueste zuerst, gepostet
            # wird spaeter in Leserichtung.
            ergebnis[kanal.name] = list(reversed(gesammelt))

        await asyncio.sleep(PAUSE_LESEN)

    return ergebnis


# ══════════════════════════════════════════════════════════════════════
#  Wiederherstellen
# ══════════════════════════════════════════════════════════════════════


class Bericht:
    """Was beim Wiederherstellen passiert ist.

    Fehler werden gesammelt statt geworfen: ein Kanal, den der Bot
    nicht anlegen darf, soll die uebrigen neunundvierzig nicht
    verhindern.
    """

    def __init__(self) -> None:
        self.geloescht = {"kanaele": 0, "rollen": 0}
        self.erstellt = {"kategorien": 0, "kanaele": 0, "rollen": 0}
        self.nachrichten = 0
        self.einstellungen = False
        self.fehler: list[str] = []

    def fehler_merken(self, text: str) -> None:
        LOGGER.warning("Wiederherstellen: %s", text)
        if len(self.fehler) < 50:
            self.fehler.append(text)

    def als_dict(self) -> dict[str, Any]:
        return {
            "geloescht": self.geloescht,
            "erstellt": self.erstellt,
            "nachrichten": self.nachrichten,
            "einstellungen": self.einstellungen,
            "fehler": self.fehler,
            "fehler_gesamt": len(self.fehler),
        }


async def stelle_wieder_her(bot, guild, inhalt: dict, *,
                            alles_loeschen: bool = False,
                            mit_einstellungen: bool = True,
                            mit_nachrichten: bool = False,
                            fortschritt: Optional[Callable[[str], None]] = None
                            ) -> dict:
    """Eine Sicherung zurueckspielen.

    Reihenfolge mit Absicht: erst loeschen, dann Rollen, dann
    Kategorien, dann Kanaele. Rechte-Ueberschreibungen zeigen auf
    Rollen -- gaebe es die Rollen noch nicht, liefen sie ins Leere.
    """
    import discord

    def melde(text: str) -> None:
        if fortschritt:
            try:
                fortschritt(text)
            except Exception:  # noqa: BLE001
                pass

    bericht = Bericht()

    if alles_loeschen:
        melde("Alte Kanäle und Rollen werden entfernt")
        await _raeume_auf(guild, bericht, melde)

    # ── Rollen ────────────────────────────────────────────────────
    #
    # Von unten nach oben: Discord legt neue Rollen ganz unten an,
    # und die gespeicherte Reihenfolge bleibt so erhalten.
    rollen_nach_name: dict[str, Any] = {
        r.name: r for r in getattr(guild, "roles", [])
    }

    melde("Rollen werden angelegt")
    for eintrag in reversed(inhalt.get("roles") or []):
        name = str(eintrag.get("name") or "").strip()
        if not name or name == "@everyone":
            continue
        if name in rollen_nach_name:
            continue

        try:
            # `template_scan` speichert NAMEN, keine Bitmaske:
            # `["send_messages", "read_messages"]`. Ein
            # `Permissions(int(...))` haette hier immer 0 ergeben und
            # jede Rolle rechtlos angelegt. Nachgesehen, nicht geraten.
            rechte = discord.Permissions(**{
                name: True
                for name in (eintrag.get("permissions") or [])
                if hasattr(discord.Permissions, name)
            })
            farbe = eintrag.get("colour") or eintrag.get("color")
            rolle = await guild.create_role(
                name=name[:100],
                permissions=rechte,
                colour=(
                    discord.Colour(int(str(farbe).lstrip("#"), 16))
                    if farbe else discord.Colour.default()
                ),
                hoist=bool(eintrag.get("hoist")),
                mentionable=bool(eintrag.get("mentionable")),
                reason="Sicherung wiederhergestellt",
            )
            rollen_nach_name[name] = rolle
            bericht.erstellt["rollen"] += 1
        except discord.Forbidden:
            bericht.fehler_merken(f"Rolle „{name}“: keine Berechtigung")
        except discord.HTTPException as exc:
            bericht.fehler_merken(f"Rolle „{name}“: {exc.text or exc}")
        await asyncio.sleep(PAUSE)

    # ── Kategorien ────────────────────────────────────────────────
    kategorien: dict[str, Any] = {
        k.name: k for k in getattr(guild, "categories", [])
    }

    melde("Kategorien werden angelegt")
    for eintrag in sorted(inhalt.get("categories") or [],
                          key=lambda e: int(e.get("position") or 0)):
        name = str(eintrag.get("name") or "").strip()
        if not name or name in kategorien:
            continue
        try:
            kategorie = await guild.create_category(
                name=name[:100],
                overwrites=_baue_rechte(guild, eintrag, rollen_nach_name),
                reason="Sicherung wiederhergestellt",
            )
            kategorien[name] = kategorie
            bericht.erstellt["kategorien"] += 1
        except discord.Forbidden:
            bericht.fehler_merken(f"Kategorie „{name}“: keine Berechtigung")
        except discord.HTTPException as exc:
            bericht.fehler_merken(f"Kategorie „{name}“: {exc.text or exc}")
        await asyncio.sleep(PAUSE)

    # ── Kanäle ────────────────────────────────────────────────────
    vorhandene = {k.name for k in getattr(guild, "channels", [])}
    neue_kanaele: dict[str, Any] = {}

    liste = sorted(inhalt.get("channels") or [],
                   key=lambda e: int(e.get("position") or 0))
    for nummer, eintrag in enumerate(liste, 1):
        name = str(eintrag.get("name") or "").strip()
        if not name or name in vorhandene:
            continue

        melde(f"Kanal {nummer}/{len(liste)}: {name}")
        art = str(eintrag.get("kind") or "text")
        kategorie = kategorien.get(eintrag.get("category") or "")
        rechte = _baue_rechte(guild, eintrag, rollen_nach_name)

        try:
            if art == "voice":
                kanal = await guild.create_voice_channel(
                    name=name[:100], category=kategorie, overwrites=rechte,
                    user_limit=int(eintrag.get("user_limit") or 0),
                    reason="Sicherung wiederhergestellt",
                )
            elif art == "forum" and hasattr(guild, "create_forum"):
                kanal = await guild.create_forum(
                    name=name[:100], category=kategorie, overwrites=rechte,
                    reason="Sicherung wiederhergestellt",
                )
            elif art == "stage" and hasattr(guild, "create_stage_channel"):
                kanal = await guild.create_stage_channel(
                    name=name[:100], category=kategorie, overwrites=rechte,
                    reason="Sicherung wiederhergestellt",
                )
            else:
                kanal = await guild.create_text_channel(
                    name=name[:100], category=kategorie, overwrites=rechte,
                    topic=(eintrag.get("topic") or None),
                    nsfw=bool(eintrag.get("nsfw")),
                    slowmode_delay=int(eintrag.get("slowmode") or 0),
                    reason="Sicherung wiederhergestellt",
                )
            neue_kanaele[name] = kanal
            bericht.erstellt["kanaele"] += 1
        except discord.Forbidden:
            bericht.fehler_merken(f"Kanal „{name}“: keine Berechtigung")
        except discord.HTTPException as exc:
            bericht.fehler_merken(f"Kanal „{name}“: {exc.text or exc}")
        await asyncio.sleep(PAUSE)

    # ── Einstellungen ─────────────────────────────────────────────
    if mit_einstellungen and inhalt.get("features"):
        melde("Dashboard-Einstellungen werden zurückgespielt")
        try:
            await _spiele_einstellungen_ein(guild, inhalt["features"])
            bericht.einstellungen = True
        except Exception as exc:  # noqa: BLE001
            bericht.fehler_merken(f"Einstellungen: {exc}")

    # ── Nachrichten ───────────────────────────────────────────────
    if mit_nachrichten and inhalt.get("messages"):
        melde("Nachrichten werden zurückgeschrieben — das dauert")
        bericht.nachrichten = await _schreibe_nachrichten(
            guild, inhalt["messages"], neue_kanaele, bericht, melde
        )

    return bericht.als_dict()


async def _raeume_auf(guild, bericht: Bericht, melde) -> None:
    """Kanaele und Rollen entfernen, soweit erlaubt.

    Der Kanal, in dem der Bot gerade arbeitet, und Rollen oberhalb
    seiner eigenen bleiben stehen -- beides kann er ohnehin nicht
    anfassen, und ein Versuch kostet nur Zeit.
    """
    import discord

    for kanal in list(getattr(guild, "channels", [])):
        try:
            await kanal.delete(reason="Sicherung: alles zurücksetzen")
            bericht.geloescht["kanaele"] += 1
        except discord.Forbidden:
            bericht.fehler_merken(f"#{kanal.name} ließ sich nicht löschen")
        except discord.HTTPException as exc:
            bericht.fehler_merken(f"#{kanal.name}: {exc.text or exc}")
        await asyncio.sleep(PAUSE)

    eigene = getattr(guild.me, "top_role", None)
    for rolle in list(getattr(guild, "roles", [])):
        if rolle.is_default() or getattr(rolle, "managed", False):
            continue
        if eigene is not None and rolle >= eigene:
            continue
        try:
            await rolle.delete(reason="Sicherung: alles zurücksetzen")
            bericht.geloescht["rollen"] += 1
        except discord.Forbidden:
            bericht.fehler_merken(f"Rolle „{rolle.name}“ ließ sich nicht löschen")
        except discord.HTTPException as exc:
            bericht.fehler_merken(f"Rolle „{rolle.name}“: {exc.text or exc}")
        await asyncio.sleep(PAUSE)


def _baue_rechte(guild, eintrag: dict, rollen: dict) -> dict:
    """Die gespeicherten Rechte-Ueberschreibungen zurueckuebersetzen.

    Ueberschreibungen fuer Rollen, die es nicht mehr gibt, fallen
    weg -- sie wuerden sonst auf None zeigen und einen Fehler
    ausloesen.
    """
    import discord

    ergebnis = {}
    for ueber in eintrag.get("overwrites") or []:
        name = str(ueber.get("role") or ueber.get("name") or "")
        ziel = guild.default_role if name == "@everyone" else rollen.get(name)
        if ziel is None:
            continue

        # Auch hier NAMEN, keine Bitmaske -- siehe `_overwrites` in
        # `template_scan`: `{"role": ..., "allow": [...], "deny": [...]}`.
        felder: dict[str, bool] = {}
        for schluessel in (ueber.get("deny") or []):
            if hasattr(discord.Permissions, str(schluessel)):
                felder[str(schluessel)] = False
        for schluessel in (ueber.get("allow") or []):
            if hasattr(discord.Permissions, str(schluessel)):
                felder[str(schluessel)] = True

        if felder:
            ergebnis[ziel] = discord.PermissionOverwrite(**felder)

    return ergebnis


async def _spiele_einstellungen_ein(guild, features: dict) -> None:
    """Die Dashboard-Einstellungen zurueck in ihre Tabellen.

    Nutzt denselben Weg wie der Speedrun (`template_scan.FEATURE_TABLES`):
    dieselbe Liste, die beim Lesen benutzt wurde, auch beim Schreiben.
    Zwei Listen liefen auseinander.
    """
    import aiosqlite

    from utils import template_scan

    for schluessel, inhalt in (features or {}).items():
        eintrag = template_scan.FEATURE_TABLES.get(schluessel)
        if eintrag is None:
            continue
        _label, pfad, tabellen = eintrag

        async with aiosqlite.connect(pfad) as db:
            for tabelle, zeilen in (inhalt or {}).items():
                # Nur Tabellen, die auch beim Lesen erlaubt waren.
                if tabelle not in tabellen:
                    continue
                for zeile in zeilen or []:
                    if not isinstance(zeile, dict) or not zeile:
                        continue
                    # `guild_id` auf DIESEN Server umbiegen: eine
                    # Sicherung kann auf einem anderen Server
                    # eingespielt werden.
                    daten = dict(zeile)
                    if "guild_id" in daten:
                        daten["guild_id"] = int(guild.id)

                    spalten = ", ".join(daten)
                    platzhalter = ", ".join("?" for _ in daten)
                    try:
                        await db.execute(
                            f"INSERT OR REPLACE INTO {tabelle} "
                            f"({spalten}) VALUES ({platzhalter})",
                            tuple(daten.values()),
                        )
                    except Exception:  # noqa: BLE001 - eine Zeile darf nicht alles kippen
                        continue
            await db.commit()


async def _schreibe_nachrichten(guild, nachrichten: dict, neue_kanaele: dict,
                                bericht: Bericht, melde) -> int:
    """Nachrichten per Webhook zurueckschreiben.

    Warum Webhook: Discord laesst keinen Bot als jemand anderes
    posten. Ein Webhook darf Name und Bild je Nachricht setzen -- das
    kommt dem Original am naechsten. Es bleibt eine NEUE Nachricht mit
    neuem Datum; die Oberflaeche sagt das auch.
    """
    import discord

    gesamt = 0
    nach_name = {k.name: k for k in getattr(guild, "text_channels", [])}
    nach_name.update(neue_kanaele)

    for kanal_name, eintraege in (nachrichten or {}).items():
        kanal = nach_name.get(kanal_name)
        if kanal is None or not isinstance(kanal, discord.TextChannel):
            continue

        try:
            webhook = await kanal.create_webhook(name="Wiederherstellung")
        except discord.Forbidden:
            bericht.fehler_merken(
                f"#{kanal_name}: kein Recht für Webhooks — "
                "Nachrichten übersprungen"
            )
            continue
        except discord.HTTPException as exc:
            bericht.fehler_merken(f"#{kanal_name}: {exc.text or exc}")
            continue

        melde(f"Nachrichten in #{kanal_name}")
        try:
            for eintrag in eintraege or []:
                text = str(eintrag.get("inhalt") or "")
                anhaenge = eintrag.get("anhaenge") or []
                if anhaenge:
                    text = (text + "\n" + "\n".join(anhaenge)).strip()
                if not text:
                    continue

                try:
                    await webhook.send(
                        content=text[:2000],
                        username=str(eintrag.get("autor") or "Unbekannt")[:80],
                        avatar_url=eintrag.get("avatar") or None,
                        # Keine Erwähnungen auslösen: sonst pingt eine
                        # Wiederherstellung den halben Server.
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                    gesamt += 1
                except discord.HTTPException as exc:
                    bericht.fehler_merken(f"#{kanal_name}: {exc.text or exc}")
                    break

                await asyncio.sleep(PAUSE_WEBHOOK)
        finally:
            # Den Webhook wieder abraeumen -- er bliebe sonst als
            # dauerhafter Schreibzugang zurueck.
            try:
                await webhook.delete(reason="Wiederherstellung beendet")
            except Exception:  # noqa: BLE001
                pass

    return gesamt
