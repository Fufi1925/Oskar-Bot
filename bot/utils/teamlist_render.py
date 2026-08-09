"""
Die Teamliste aus einem echten Server zusammenstellen und senden.

Getrennt vom Speicher (`teamlist_store`), weil hier Discord-Objekte
angefasst werden: Rollen, Mitglieder, Kanaele. Der Speicher bleibt so
ohne discord.py testbar.

Zwei Fallen, die hier geloest sind
----------------------------------
1. **`role.members` ist unzuverlaessig.** discord.py filtert dort
   still ueber den Mitglieder-Zwischenspeicher: wer nicht drin ist,
   fehlt. Bei grossen Servern ohne ``members``-Intent oder direkt nach
   dem Start ist die Liste dann kurz -- und die Teamliste zeigt drei
   Moderatoren statt zwoelf. Deshalb wird geprueft, ob der
   Zwischenspeicher ueberhaupt gefuellt ist, und notfalls nachgeladen.

2. **Bearbeiten statt neu senden.** Eine Teamliste soll oben im Kanal
   stehen bleiben. Bei jeder Aenderung eine neue Nachricht zu schicken
   waere nach einer Woche ein Kanal voller Teamlisten.
"""

from __future__ import annotations

import asyncio


# Wie ein Status angezeigt wird, wenn die Anzeige eingeschaltet ist.
#
# Discord liefert den Status nur mit dem ``presences``-Intent. Fehlt
# er, ist er bei jedem "offline" -- dann waere die Anzeige eine Reihe
# grauer Punkte und schlechter als gar keine. `member_status` gibt
# deshalb None zurueck, wenn der Intent fehlt.
STATUS_EMOJI = {
    "online": "🟢",
    "idle": "🟡",
    "dnd": "🔴",
    "offline": "⚫",
}


def _members_of(guild, role):
    """Die Mitglieder einer Rolle -- so verlaesslich wie moeglich.

    `role.members` geht ueber den Zwischenspeicher. Ist der leer, wird
    ueber `guild.members` gesucht; das ist derselbe Speicher, aber der
    Umweg deckt Faelle ab, in denen discord.py die Rollenzuordnung noch
    nicht aufgebaut hat.
    """

    found = list(getattr(role, "members", []) or [])
    if found:
        return found

    out = []
    for member in getattr(guild, "members", []) or []:
        ids = {int(getattr(r, "id", 0)) for r in getattr(member, "roles", [])}
        if int(role.id) in ids:
            out.append(member)
    return out


def member_status(guild, member) -> str | None:
    """Das Status-Zeichen, oder None wenn es keine Aussage gibt."""

    raw = getattr(member, "status", None)
    if raw is None:
        return None

    # Ohne presences-Intent meldet discord.py fuer alle "offline".
    intents = getattr(getattr(guild, "_state", None), "intents", None)
    if intents is not None and not getattr(intents, "presences", False):
        return None

    return STATUS_EMOJI.get(str(getattr(raw, "value", raw)), None)


def collect(guild, groups: list[dict], want_status: bool = False) -> dict:
    """Wer steckt in welcher Gruppe.

    Gibt Rollen-ID (als Text) -> Liste von Mitgliedern. Jeder Eintrag
    hat `mention`, `name` und ggf. `status`.

    Bots werden ausgelassen: eine Teamliste zaehlt Menschen. Steht der
    Bot selbst in der Moderatorenrolle, gehoert er nicht in die
    Aufzaehlung.

    Sortiert wird nach dem Anzeigenamen, damit die Reihenfolge nicht
    davon abhaengt, in welcher Reihenfolge Discord die Mitglieder
    ausliefert -- sonst springt die Liste bei jeder Auffrischung
    durcheinander.
    """

    out: dict[str, list[dict]] = {}

    for group in groups:
        try:
            role_id = int(group["role_id"])
        except (TypeError, ValueError, KeyError):
            continue

        role = None
        for candidate in getattr(guild, "roles", []) or []:
            if int(getattr(candidate, "id", 0)) == role_id:
                role = candidate
                break

        if role is None:
            # Die Rolle wurde geloescht. Kein Fehler -- die Gruppe
            # bleibt leer und faellt (je nach Einstellung) heraus.
            out[str(role_id)] = []
            continue

        entries = []
        for member in _members_of(guild, role):
            if getattr(member, "bot", False):
                continue
            entry = {
                "mention": f"<@{int(member.id)}>",
                "name": getattr(member, "display_name", "") or "",
                "id": str(int(member.id)),
            }
            if want_status:
                mark = member_status(guild, member)
                if mark:
                    entry["status"] = mark
            entries.append(entry)

        entries.sort(key=lambda item: item["name"].lower())
        out[str(role_id)] = entries

    return out


def role_names(guild, groups: list[dict]) -> dict[str, str]:
    """Rollen-ID -> Name, fuer Gruppen ohne eigene Beschriftung."""

    names: dict[str, str] = {}
    for role in getattr(guild, "roles", []) or []:
        names[str(int(role.id))] = role.name

    return {
        str(group["role_id"]): names.get(str(group["role_id"]), "Gelöschte Rolle")
        for group in groups
        if group.get("role_id")
    }


def build(guild, config: dict, groups: list[dict]) -> str:
    """Den fertigen Text bauen."""

    from utils import teamlist_store as store

    names = role_names(guild, groups)
    filled = [
        {**group, "role_name": names.get(str(group["role_id"]), "")}
        for group in groups
    ]
    members = collect(guild, groups, want_status=bool(config.get("show_status")))
    return store.build_lines(config, filled, members)


def build_embed(guild, config: dict, groups: list[dict]):
    """Dasselbe als Embed, wenn so eingestellt."""

    import discord

    text = build(guild, config, groups)

    colour = discord.Colour.blurple()
    raw = str(config.get("colour") or "").strip()
    if raw.startswith("#"):
        try:
            colour = discord.Colour(int(raw[1:], 16))
        except ValueError:
            pass

    embed = discord.Embed(
        title=str(config.get("title") or "Unser Team")[:256],
        description=text[:4096],
        colour=colour,
    )
    return embed


async def publish(bot, guild, config: dict, groups: list[dict]) -> dict:
    """Die Nachricht schreiben oder bearbeiten.

    Gibt `{"ok": bool, "reason": str, "message_id": str}`.

    Warum hier nichts geworfen wird
    -------------------------------
    Die Auffrischung laeuft im Hintergrund fuer viele Server. Wirft
    einer, stuende die Schleife -- und alle anderen bekaemen keine
    Aktualisierung mehr. Ein Bericht je Server ist die richtige Form.
    """

    import discord

    channel_id = config.get("channel_id")
    if not channel_id:
        return {"ok": False, "reason": "Kein Kanal eingestellt.", "message_id": ""}

    try:
        channel = guild.get_channel(int(channel_id))
    except (TypeError, ValueError):
        channel = None

    if channel is None:
        return {
            "ok": False,
            "reason": "Den eingestellten Kanal gibt es nicht mehr.",
            "message_id": "",
        }

    me = getattr(guild, "me", None)
    if me is not None:
        perms = channel.permissions_for(me)
        if not perms.send_messages:
            return {
                "ok": False,
                "reason": f"Dem Bot fehlt »Nachrichten senden« in #{channel.name}.",
                "message_id": "",
            }
        if config.get("use_embed") and not perms.embed_links:
            return {
                "ok": False,
                "reason": f"Dem Bot fehlt »Links einbetten« in #{channel.name}.",
                "message_id": "",
            }

    use_embed = bool(config.get("use_embed"))
    content = None if use_embed else build(guild, config, groups)
    embed = build_embed(guild, config, groups) if use_embed else None

    # Niemanden anpingen. Die Liste besteht fast nur aus Erwaehnungen
    # -- ohne diese Sperre bekaeme das halbe Team bei jeder
    # Auffrischung eine Benachrichtigung.
    silent = discord.AllowedMentions.none()

    message_id = config.get("message_id")
    if message_id:
        try:
            existing = await channel.fetch_message(int(message_id))
            await existing.edit(
                content=content, embed=embed, allowed_mentions=silent
            )
            return {"ok": True, "reason": "", "message_id": str(existing.id)}
        except discord.NotFound:
            # Jemand hat die Nachricht geloescht. Kein Fehler -- eine
            # neue schicken und die neue ID merken.
            pass
        except discord.Forbidden:
            return {
                "ok": False,
                "reason": "Der Bot darf die Nachricht nicht bearbeiten.",
                "message_id": "",
            }
        except Exception as error:
            return {"ok": False, "reason": str(error), "message_id": ""}

    try:
        sent = await channel.send(
            content=content, embed=embed, allowed_mentions=silent
        )
        return {"ok": True, "reason": "", "message_id": str(sent.id)}
    except discord.Forbidden:
        return {
            "ok": False,
            "reason": f"Der Bot darf in #{channel.name} nicht schreiben.",
            "message_id": "",
        }
    except Exception as error:
        return {"ok": False, "reason": str(error), "message_id": ""}


async def refresh_guild(bot, guild_id: int) -> dict:
    """Eine Teamliste neu schreiben. Holt sich alles selbst."""

    from api.db_manager import db_manager
    from utils import teamlist_store as store

    guild = bot.get_guild(int(guild_id))
    if guild is None:
        return {"ok": False, "reason": "Bot ist nicht auf dem Server.",
                "message_id": ""}

    db = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(db)

    config = await store.get_config(db, guild_id)
    if not config.get("enabled"):
        return {"ok": False, "reason": "Die Teamliste ist ausgeschaltet.",
                "message_id": ""}

    groups = await store.get_groups(db, guild_id)
    result = await publish(bot, guild, config, groups)

    if result["ok"] and result["message_id"] != str(config.get("message_id") or ""):
        await store.set_message(
            db, guild_id, config.get("channel_id"), result["message_id"]
        )

    return result


# ── Sammelpause ──────────────────────────────────────────────────────
#
# Wer fuenf Leuten nacheinander eine Rolle gibt, loest fuenf Ereignisse
# aus. Ohne Sammelpause schriebe der Bot fuenfmal -- und liefe in
# Discords Bearbeitungsgrenze.

_pending: dict[int, asyncio.Task] = {}


def schedule(bot, guild_id: int) -> None:
    """Eine Auffrischung anstossen, fruehestens in ein paar Sekunden.

    Laeuft schon eine, wird sie verworfen und neu angesetzt: die
    letzte Aenderung bestimmt, wann geschrieben wird.

    Warum der Eintrag im `finally` geprueft wird
    --------------------------------------------
    Das war ein echter Fehler, und ein unauffaelliger: bricht man den
    alten Task ab, laeuft dessen `finally` NICHT sofort, sondern erst
    beim naechsten Durchlauf der Ereignisschleife -- also nachdem der
    neue Task schon in `_pending` steht. Ein blindes
    `_pending.pop(guild_id)` loeschte dann den Eintrag des *neuen*
    Tasks. Der naechste Aufruf fand nichts zum Abbrechen, setzte
    einen zweiten Task an, und aus fuenf Aenderungen wurden drei
    Schreibvorgaenge statt einem.

    Gemessen in `repro/`: fuenf Aenderungen ergaben verlaesslich drei
    Auffrischungen, unabhaengig von den Zeitabstaenden. Genau die
    Bearbeitungsgrenze, die die Sammelpause vermeiden sollte.
    """

    from utils import teamlist_store as store

    guild_id = int(guild_id)

    old = _pending.get(guild_id)
    if old is not None and not old.done():
        old.cancel()

    async def later(task_holder: dict) -> None:
        try:
            await asyncio.sleep(store.DEBOUNCE_SECONDS)
            await refresh_guild(bot, guild_id)
        except asyncio.CancelledError:
            # Eine neue Aenderung kam dazwischen. Kein Fehler.
            pass
        except Exception as error:
            print(f"[teamlist] Auffrischen fuer {guild_id} fehlgeschlagen: {error}")
        finally:
            # Nur aufraeumen, wenn WIR noch der eingetragene Task
            # sind. Sonst loescht ein abgebrochener Vorgaenger den
            # Eintrag seines Nachfolgers.
            if _pending.get(guild_id) is task_holder.get("task"):
                _pending.pop(guild_id, None)

    holder: dict = {}
    coro = later(holder)

    loop = getattr(bot, "loop", None)
    if loop is not None and not loop.is_closed():
        task = loop.create_task(coro)
    else:  # Tests ohne laufenden Bot
        task = asyncio.ensure_future(coro)

    holder["task"] = task
    _pending[guild_id] = task
