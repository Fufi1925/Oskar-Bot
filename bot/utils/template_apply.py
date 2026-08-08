"""
Eine Vorlage auf einen Server anwenden.

Das ist der gefaehrlichste Teil des Systems. Mit der Option "alles
loeschen" verschwinden Kanaele samt Inhalt -- unwiderruflich, Discord
kennt keinen Papierkorb. Entsprechend vorsichtig ist der Ablauf:

  1. **Erst pruefen, dann anfassen.** Fehlen dem Bot Rechte oder steht
     seine Rolle zu weit unten, wird gar nicht erst angefangen. Ein
     halb aufgesetzter Server ist schlimmer als keiner.
  2. **Nichts loeschen, was der Bot braucht.** Seine eigene Rolle, der
     Kanal, in dem er gerade spricht, und die Regelkanaele eines
     Community-Servers bleiben stehen -- Discord verbietet Letzteres
     ohnehin und wirft mitten im Lauf einen Fehler.
  3. **Weitermachen, wenn ein Schritt scheitert.** Ein Kanal, der
     nicht angelegt werden konnte, darf nicht die restlichen fuenfzig
     verhindern. Am Ende steht ein Bericht, was ging und was nicht.

Warum die Rollen zuerst kommen
------------------------------
Kanalrechte verweisen auf Rollen. Legt man die Kanaele zuerst an,
zeigen ihre Rechte ins Leere und muessten hinterher nachgetragen
werden -- zwei Durchlaeufe statt einem, und bei jedem Fehler ein
halber Zustand.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any, Callable

# Discords Grenzen. Sie werden vorher geprueft, damit die Meldung
# "500 Kanaele sind das Maximum" kommt statt eines HTTP-Fehlers nach
# dem 500. Kanal.
MAX_CHANNELS = 500
MAX_ROLES = 250

# Wie lange zwischen zwei Discord-Aufrufen gewartet wird.
#
# Discord bremst bei zu vielen Aenderungen und antwortet dann mit 429.
# discord.py wartet zwar selbst, aber ein kurzer eigener Abstand haelt
# den ganzen Lauf fluessiger, statt in immer laengere Zwangspausen zu
# geraten.
STEP_PAUSE = 0.35

_PLACEHOLDER = re.compile(r"\{(channel|role):([^}]{1,100})\}")


class Report:
    """Was beim Anwenden passiert ist.

    Sammelt statt zu werfen: ein einzelner Fehlschlag soll den Lauf
    nicht beenden, aber am Ende muss nachvollziehbar sein, was fehlt.
    """

    def __init__(self) -> None:
        self.created: list[str] = []
        self.deleted: list[str] = []
        self.skipped: list[str] = []
        self.errors: list[str] = []

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "deleted": self.deleted,
            "skipped": self.skipped,
            "errors": self.errors,
            "ok": not self.errors,
        }


def _perms_from_names(names: list[str]):
    """Rechte-Namen zurueck in ein Discord-Objekt.

    Unbekannte Namen werden uebersprungen. Discord benennt Rechte
    gelegentlich um; eine aeltere Vorlage soll deshalb nicht komplett
    scheitern.
    """

    import discord

    permissions = discord.Permissions.none()
    valid = {name for name, _ in discord.Permissions.none()}
    for name in names or []:
        if name in valid:
            setattr(permissions, name, True)
    return permissions


def _overwrite_from(entry: dict):
    import discord

    overwrite = discord.PermissionOverwrite()
    valid = {name for name, _ in discord.Permissions.none()}
    for name in entry.get("allow") or []:
        if name in valid:
            setattr(overwrite, name, True)
    for name in entry.get("deny") or []:
        if name in valid:
            setattr(overwrite, name, False)
    return overwrite


async def precheck(guild, payload: dict, *, wipe: bool) -> list[str]:
    """Was dem Bot fehlt, um das durchzuziehen.

    Leere Liste heisst: los geht's. Alles andere wird dem Nutzer
    gezeigt, **bevor** irgendetwas angefasst wird.
    """

    problems: list[str] = []
    me = getattr(guild, "me", None)

    if me is None:
        return ["Der Bot ist nicht auf diesem Server."]

    perms = me.guild_permissions
    if not perms.manage_channels:
        problems.append("Dem Bot fehlt das Recht »Kanäle verwalten«.")
    if not perms.manage_roles:
        problems.append("Dem Bot fehlt das Recht »Rollen verwalten«.")

    # Der Bot kann nur Rollen anlegen, die unter seiner eigenen
    # stehen. Ist seine Rolle ganz unten, geht gar nichts -- und das
    # merkt man sonst erst beim ersten Fehlschlag.
    top = getattr(me, "top_role", None)
    if top is not None and int(getattr(top, "position", 0)) <= 1:
        problems.append(
            "Die Rolle des Bots steht ganz unten. Sie muss über den Rollen "
            "stehen, die er anlegen soll — bitte in den Servereinstellungen "
            "nach oben ziehen."
        )

    roles = payload.get("roles") or []
    channels = payload.get("channels") or []
    categories = payload.get("categories") or []

    have_roles = len(getattr(guild, "roles", []))
    have_channels = len(getattr(guild, "channels", []))

    if not wipe:
        if have_roles + len(roles) > MAX_ROLES:
            problems.append(
                f"Der Server hätte danach mehr als {MAX_ROLES} Rollen — "
                "Discords Grenze. Bitte zuerst aufräumen oder »alles "
                "löschen« wählen."
            )
        if have_channels + len(channels) + len(categories) > MAX_CHANNELS:
            problems.append(
                f"Der Server hätte danach mehr als {MAX_CHANNELS} Kanäle — "
                "Discords Grenze."
            )

    return problems


def _protected_channels(guild) -> set[int]:
    """Kanaele, die nicht geloescht werden duerfen.

    Bei einem Community-Server verlangt Discord einen Regel- und einen
    Ankuendigungskanal. Der Versuch, sie zu loeschen, endet mit einem
    Fehler mitten im Lauf -- besser, sie gar nicht erst anzufassen.
    """

    keep: set[int] = set()
    for attribute in ("rules_channel", "public_updates_channel", "system_channel"):
        channel = getattr(guild, attribute, None)
        if channel is not None:
            keep.add(int(channel.id))
    return keep


async def wipe_server(guild, report: Report, log: Callable | None = None) -> set[int]:
    """Kanaele und Rollen entfernen. Gibt die geloeschten IDs zurueck.

    Was stehen bleibt:
      * die Rolle des Bots und alles darueber (kann er nicht loeschen)
      * von Discord verwaltete Rollen (Bot-Rollen, Booster)
      * @everyone
      * die Pflichtkanaele eines Community-Servers

    Warum die IDs zurueckkommen
    ---------------------------
    Das war ein echter Fehler, und zwar der schlimmste im ganzen
    System: `channel.delete()` schickt nur die Anfrage an Discord.
    Aus `guild.channels` verschwindet der Kanal erst, wenn das
    Gateway `CHANNEL_DELETE` zurueckmeldet -- ein eigener Frame, der
    Millisekunden bis Sekunden spaeter eintrifft, bei einem grossen
    Server auch deutlich spaeter.

    Der naechste Schritt, `apply_channels`, liest aber sofort:

        existing = {c.name for c in guild.channels}

    und ueberspringt jeden Namen, der dort steht. Bei »alles
    loeschen« standen dort noch **alle gerade geloeschten Namen** --
    also wurde geloescht und danach nichts wieder angelegt. Der
    Nutzer sass vor einem leeren Server.

    Reproduziert in `repro/bug_templates_wipe.py`. Die Loesung ist
    diese Rueckgabe: die Folgeschritte wissen damit, was trotz Cache
    nicht mehr existiert, statt sich auf den Cache zu verlassen.
    """

    me = getattr(guild, "me", None)
    my_top = int(getattr(getattr(me, "top_role", None), "position", 0))
    protected = _protected_channels(guild)
    gone: set[int] = set()

    for channel in list(getattr(guild, "channels", [])):
        if int(channel.id) in protected:
            report.skipped.append(f"Kanal {channel.name} (von Discord benötigt)")
            continue
        try:
            await channel.delete(reason="Vorlage: Server wird neu aufgesetzt")
            gone.add(int(channel.id))
            report.deleted.append(f"Kanal {channel.name}")
            if log:
                log(f"Kanal gelöscht: {channel.name}")
        except Exception as error:
            report.errors.append(f"Kanal {channel.name}: {error}")
        await asyncio.sleep(STEP_PAUSE)

    for role in list(getattr(guild, "roles", [])):
        if getattr(role, "is_default", lambda: False)():
            continue
        if getattr(role, "managed", False):
            continue
        if int(getattr(role, "position", 0)) >= my_top:
            report.skipped.append(f"Rolle {role.name} (steht über dem Bot)")
            continue
        try:
            await role.delete(reason="Vorlage: Server wird neu aufgesetzt")
            gone.add(int(role.id))
            report.deleted.append(f"Rolle {role.name}")
            if log:
                log(f"Rolle gelöscht: {role.name}")
        except Exception as error:
            report.errors.append(f"Rolle {role.name}: {error}")
        await asyncio.sleep(STEP_PAUSE)

    return gone


async def apply_roles(guild, payload: dict, report: Report,
                      log: Callable | None = None,
                      gone: set[int] | None = None) -> dict[str, Any]:
    """Rollen anlegen. Gibt Name -> Rolle zurueck.

    Die Zuordnung braucht der naechste Schritt: Kanalrechte verweisen
    ueber den Namen auf eine Rolle.

    `gone` sind die IDs, die `wipe_server` gerade geloescht hat. Sie
    stehen unter Umstaenden noch im Cache -- siehe die Erklaerung
    dort. Ohne diese Liste galt jede geloeschte Rolle als »gibt es
    schon« und wurde nicht neu angelegt.
    """

    import discord

    made: dict[str, Any] = {}
    dead = gone or set()

    # Bestehende gleichnamige Rollen wiederverwenden, statt ein
    # zweites "Moderator" anzulegen. Zwei Rollen mit demselben Namen
    # sind in Discord erlaubt und danach kaum auseinanderzuhalten.
    for role in getattr(guild, "roles", []):
        if int(getattr(role, "id", 0)) in dead:
            continue
        made.setdefault(role.name, role)

    for entry in payload.get("roles") or []:
        name = str(entry.get("name") or "").strip()
        if not name or name in made:
            continue

        colour = None
        raw = entry.get("colour")
        if isinstance(raw, str) and raw.startswith("#"):
            try:
                colour = discord.Colour(int(raw[1:], 16))
            except ValueError:
                colour = None

        try:
            role = await guild.create_role(
                name=name[:100],
                colour=colour or discord.Colour.default(),
                hoist=bool(entry.get("hoist")),
                mentionable=bool(entry.get("mentionable")),
                permissions=_perms_from_names(entry.get("permissions") or []),
                reason="Vorlage angewendet",
            )
            made[name] = role
            report.created.append(f"Rolle {name}")
            if log:
                log(f"Rolle angelegt: {name}")
        except Exception as error:
            report.errors.append(f"Rolle {name}: {error}")
        await asyncio.sleep(STEP_PAUSE)

    return made


def _build_overwrites(entries: list[dict], roles: dict[str, Any], guild):
    """Die Rechte-Tabelle eines Kanals zusammenbauen."""

    out = {}
    for entry in entries or []:
        label = str(entry.get("role") or "")
        target = (
            guild.default_role if label == "@everyone" else roles.get(label)
        )
        if target is None:
            continue
        out[target] = _overwrite_from(entry)
    return out


async def apply_channels(guild, payload: dict, roles: dict[str, Any],
                         report: Report, log: Callable | None = None,
                         gone: set[int] | None = None) -> dict:
    """Kategorien und Kanaele anlegen.

    `gone` sind die IDs aus `wipe_server` -- siehe die Erklaerung
    dort. Ohne sie hielt dieser Schritt jeden gerade geloeschten
    Kanal fuer bestehend und legte ihn nicht wieder an.
    """

    dead = gone or set()

    made_categories: dict[str, Any] = {}
    for category in getattr(guild, "categories", []):
        if int(getattr(category, "id", 0)) in dead:
            continue
        made_categories.setdefault(category.name, category)

    for entry in sorted(
        payload.get("categories") or [], key=lambda c: c.get("position", 0)
    ):
        name = str(entry.get("name") or "").strip()
        if not name or name in made_categories:
            continue
        try:
            created = await guild.create_category(
                name=name[:100],
                overwrites=_build_overwrites(entry.get("overwrites"), roles, guild),
                reason="Vorlage angewendet",
            )
            made_categories[name] = created
            report.created.append(f"Kategorie {name}")
            if log:
                log(f"Kategorie angelegt: {name}")
        except Exception as error:
            report.errors.append(f"Kategorie {name}: {error}")
        await asyncio.sleep(STEP_PAUSE)

    # Ein Kanal ist durch Name **und Kategorie** bestimmt, nicht durch
    # den Namen allein.
    #
    # Auch das war ein echter Fehler: Discord erlaubt zwei Kanaele mit
    # demselben Namen, solange sie in verschiedenen Kategorien liegen
    # -- »chat« unter »Team« und »chat« unter »Community« ist ein
    # voellig gewoehnlicher Aufbau. Verglichen wurde aber nur der
    # Name, also entstand nur der erste, und der zweite fiel
    # kommentarlos unter den Tisch.
    #
    # Reproduziert in `repro/bug_templates_dupnames.py`.
    existing = {
        (
            c.name,
            getattr(getattr(c, "category", None), "name", None),
        )
        for c in getattr(guild, "channels", [])
        if int(getattr(c, "id", 0)) not in dead
    }

    for entry in sorted(
        payload.get("channels") or [], key=lambda c: c.get("position", 0)
    ):
        name = str(entry.get("name") or "").strip()
        where = entry.get("category") or None
        if not name or (name, where) in existing:
            if name:
                report.skipped.append(
                    f"Kanal {name}"
                    + (f" in {where}" if where else "")
                    + " (gibt es schon)"
                )
            continue

        kind = entry.get("kind") or "text"
        category = made_categories.get(entry.get("category") or "")
        overwrites = _build_overwrites(entry.get("overwrites"), roles, guild)

        try:
            if kind == "voice":
                channel = await guild.create_voice_channel(
                    name=name[:100],
                    category=category,
                    overwrites=overwrites,
                    user_limit=int(entry.get("user_limit") or 0),
                    reason="Vorlage angewendet",
                )
            elif kind == "forum" and hasattr(guild, "create_forum"):
                channel = await guild.create_forum(
                    name=name[:100],
                    category=category,
                    overwrites=overwrites,
                    topic=str(entry.get("topic") or "")[:1024] or None,
                    reason="Vorlage angewendet",
                )
            elif kind == "stage" and hasattr(guild, "create_stage_channel"):
                channel = await guild.create_stage_channel(
                    name=name[:100],
                    category=category,
                    overwrites=overwrites,
                    reason="Vorlage angewendet",
                )
            else:
                channel = await guild.create_text_channel(
                    name=name[:100],
                    category=category,
                    overwrites=overwrites,
                    topic=str(entry.get("topic") or "")[:1024] or None,
                    nsfw=bool(entry.get("nsfw")),
                    slowmode_delay=int(entry.get("slowmode") or 0),
                    reason="Vorlage angewendet",
                )

            existing.add((name, where))
            report.created.append(f"Kanal {name}")
            if log:
                log(f"Kanal angelegt: {name}")
            _ = channel
        except Exception as error:
            report.errors.append(f"Kanal {name}: {error}")
        await asyncio.sleep(STEP_PAUSE)

    return made_categories


def resolve_placeholders(value, guild):
    """`{channel:name}` und `{role:name}` in echte IDs.

    Findet sich nichts, bleibt None stehen -- besser als eine ID von
    einem fremden Server, die hier auf irgendetwas zeigt.
    """

    if isinstance(value, dict):
        return {k: resolve_placeholders(v, guild) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve_placeholders(v, guild) for v in value]
    if not isinstance(value, str):
        return value

    match = _PLACEHOLDER.fullmatch(value.strip())
    if match:
        kind, name = match.group(1), match.group(2)
        if kind == "channel":
            found = next(
                (c for c in getattr(guild, "channels", []) if c.name == name), None
            )
        else:
            if name == "@everyone":
                found = guild.default_role
            else:
                found = next(
                    (r for r in getattr(guild, "roles", []) if r.name == name), None
                )
        return int(found.id) if found is not None else None

    # Platzhalter mitten im Text -- etwa in einer Willkommensnachricht.
    def _inline(m: re.Match) -> str:
        kind, name = m.group(1), m.group(2)
        if kind == "channel":
            found = next(
                (c for c in getattr(guild, "channels", []) if c.name == name), None
            )
            return f"<#{found.id}>" if found else f"#{name}"
        if name == "@everyone":
            return "@everyone"
        found = next((r for r in getattr(guild, "roles", []) if r.name == name), None)
        return f"<@&{found.id}>" if found else f"@{name}"

    return _PLACEHOLDER.sub(_inline, value)


async def apply_features(guild, payload: dict, wanted: dict[str, bool],
                         report: Report, log: Callable | None = None) -> None:
    """Die Dashboard-Einstellungen uebernehmen.

    Nur die ausgewaehlten. `wanted` kommt aus dem Reiter "Dashboard
    erweitert", wo jede Funktion einzeln an- und abgeschaltet werden
    kann.
    """

    import aiosqlite

    from utils import template_scan

    for key, block in (payload.get("features") or {}).items():
        if not wanted.get(key, False):
            continue

        spec = template_scan.FEATURE_TABLES.get(key)
        if spec is None:
            continue
        label, path, _tables = spec

        try:
            async with aiosqlite.connect(path) as db:
                for table, rows in (block.get("tables") or {}).items():
                    # Welche Spalten es in der ZIELtabelle wirklich
                    # gibt.
                    #
                    # Auch das war ein echter Fehler: das INSERT wurde
                    # aus den Spalten der Quelle gebaut. Kennt das Ziel
                    # eine davon nicht -- weil die Vorlage aus einer
                    # neueren Version stammt oder die Tabelle inzwischen
                    # anders aussieht --, warf SQLite »has no column
                    # named x« und der GANZE Block ging verloren, statt
                    # der einen unpassenden Spalte.
                    #
                    # Reproduziert in `repro/bug_templates_dupnames.py`.
                    try:
                        async with db.execute(
                            f"PRAGMA table_info({table})"
                        ) as cursor:
                            known = {r[1] for r in await cursor.fetchall()}
                    except Exception:
                        known = set()

                    if not known:
                        # Die Tabelle gibt es hier gar nicht. Das ist
                        # kein Fehler des Nutzers -- die Vorlage bringt
                        # eine Funktion mit, die dieser Bot (noch)
                        # nicht kennt.
                        report.skipped.append(
                            f"Einstellungen {label}: Tabelle {table} "
                            "gibt es hier nicht"
                        )
                        continue

                    dropped: set[str] = set()
                    written = 0

                    for row in rows:
                        clean = resolve_placeholders(dict(row), guild)
                        clean["guild_id"] = int(guild.id)
                        # Die Nummer aus der Quelldatenbank wuerde hier
                        # mit einer fremden Zeile kollidieren.
                        clean.pop("id", None)

                        dropped |= set(clean) - known
                        clean = {k: v for k, v in clean.items() if k in known}
                        if not clean:
                            continue

                        columns = ", ".join(clean)
                        marks = ", ".join("?" for _ in clean)
                        try:
                            await db.execute(
                                f"INSERT OR REPLACE INTO {table} ({columns}) "
                                f"VALUES ({marks})",
                                tuple(clean.values()),
                            )
                            written += 1
                        except Exception as error:
                            # Eine kaputte Zeile darf die anderen nicht
                            # mitnehmen.
                            report.errors.append(
                                f"Einstellungen {label} ({table}): {error}"
                            )

                    if dropped:
                        report.skipped.append(
                            f"Einstellungen {label}: "
                            f"{', '.join(sorted(dropped))} "
                            "(kennt dieser Bot nicht)"
                        )
                    _ = written
                await db.commit()
            report.created.append(f"Einstellungen: {label}")
            if log:
                log(f"Einstellungen übernommen: {label}")
        except Exception as error:
            report.errors.append(f"Einstellungen {label}: {error}")


async def apply_template(
    guild,
    payload: dict,
    options: dict,
    *,
    log: Callable | None = None,
) -> dict:
    """Alles zusammen. Gibt den Bericht zurueck.

    `options` steuert, was uebernommen wird:

        roles         Rollen anlegen
        channels      Kategorien und Kanaele
        permissions   Kanalrechte (ohne das: Kanaele ohne Sonderrechte)
        features      Dashboard-Einstellungen
        wipe          vorher alles loeschen
        feature_keys  welche Funktionen einzeln (Dict key -> bool)
    """

    report = Report()

    problems = await precheck(guild, payload, wipe=bool(options.get("wipe")))
    if problems:
        report.errors.extend(problems)
        return report.as_dict()

    # Was geloescht wurde, aber vielleicht noch im Cache steht. Ohne
    # diese Liste hielten die naechsten Schritte den geleerten Server
    # fuer voll und legten nichts an -- siehe `wipe_server`.
    gone: set[int] = set()
    if options.get("wipe"):
        if log:
            log("Server wird geleert …")
        gone = await wipe_server(guild, report, log)

    roles: dict[str, Any] = {}
    if options.get("roles", True):
        if log:
            log("Rollen werden angelegt …")
        roles = await apply_roles(guild, payload, report, log, gone)
    else:
        for role in getattr(guild, "roles", []):
            if int(getattr(role, "id", 0)) in gone:
                continue
            roles.setdefault(role.name, role)

    if options.get("channels", True):
        if log:
            log("Kanäle werden angelegt …")
        # Ohne Rechte-Übernahme die Overwrites vorher entfernen: so
        # entstehen die Kanäle mit den Serverstandards.
        working = payload
        if not options.get("permissions", True):
            working = dict(payload)
            working["categories"] = [
                {**c, "overwrites": []} for c in payload.get("categories") or []
            ]
            working["channels"] = [
                {**c, "overwrites": []} for c in payload.get("channels") or []
            ]
        await apply_channels(guild, working, roles, report, log, gone)

    if options.get("features", False):
        if log:
            log("Einstellungen werden übernommen …")
        await apply_features(
            guild, payload, options.get("feature_keys") or {}, report, log
        )

    return report.as_dict()
