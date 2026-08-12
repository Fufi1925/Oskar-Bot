# ╔══════════════════════════════════════════════════════════════════╗
# ║   Team-Update: der Ablauf                                        ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Was bei einer Team-Aktion wirklich passiert.

``team_update_store`` weiss, was eingestellt ist. Hier steht, was
damit geschieht: Rollen umstecken, ankuendigen, DM schicken, in die
Akte eintragen.

Warum das nicht im Cog steht
----------------------------
Drei Wege loesen dieselbe Aktion aus:

  1. die Slash-Befehle
  2. eine angenommene Bewerbung (der Bot nimmt jemanden ins Team)
  3. die Verwarnungs-Automatik (zu viele Verwarnungen -> Rueckstufung)

Drei Fassungen desselben Ablaufs liefen frueher oder spaeter
auseinander -- eine vergisst die Ankuendigung, die naechste den
Akteneintrag. Hier gibt es eine.

Die Reihenfolge beim Rollentausch
---------------------------------
**Erst die neue Rolle geben, dann die alte nehmen.** Scheitert der
erste Schritt, steht die Person noch dort, wo sie vorher war.
Andersherum haette ein halber Fehlschlag jemanden ohne jede Rolle
zurueckgelassen -- genau in dem Moment, in dem er befoerdert werden
sollte.

Was nie einen Abbruch ausloest
------------------------------
Die Ankuendigung und die DM sind Beiwerk. Ein Kanal, in den der Bot
nicht schreiben darf, oder geschlossene DMs duerfen nicht dazu
fuehren, dass die Rollen nicht gesetzt werden. Beides wird gemeldet,
nicht geworfen.
"""

from __future__ import annotations

import logging

from utils import team_update_store as store

logger = logging.getLogger(__name__)


class Result:
    """
    Was eine Team-Aktion bewirkt hat.

    Absichtlich ausfuehrlich: der Befehl, das Dashboard und das
    Protokoll zeigen alle dieselbe Antwort, und "hat nicht geklappt"
    ohne Grund ist keine Antwort.
    """

    __slots__ = (
        "ok", "action", "user_id", "given", "removed", "failed",
        "announced", "channel_id", "dm_sent", "event_id", "warn_count",
        "followup", "note",
    )

    def __init__(self, action: str, user_id: int):
        self.ok = True
        self.action = action
        self.user_id = int(user_id)
        self.given: list[str] = []
        self.removed: list[str] = []
        self.failed: list[str] = []
        self.announced = False
        self.channel_id = ""
        self.dm_sent = False
        self.event_id = 0
        self.warn_count = 0
        self.followup = store.FOLLOWUP_NONE
        self.note = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "action": self.action,
            "user_id": str(self.user_id),
            "given": self.given,
            "removed": self.removed,
            "failed": self.failed,
            "announced": self.announced,
            "channel_id": self.channel_id,
            "dm_sent": self.dm_sent,
            "event_id": self.event_id,
            "warn_count": self.warn_count,
            "followup": self.followup,
            "note": self.note,
        }


# ── Rollen ───────────────────────────────────────────────────────────


def _blocked(guild, role) -> str:
    """
    Warum der Bot diese Rolle nicht anfassen kann -- oder "".

    Vorher pruefen statt hinterher einen 403 auffangen: Discord nennt
    im Fehler nicht, welche der beiden Ursachen es war, und der Grund
    steht am Ende nur im Log statt in der Antwort.
    """
    if role is None:
        return "Die Rolle gibt es nicht mehr."
    ich = getattr(guild, "me", None)
    if ich is None:
        return ""
    if getattr(role, "managed", False):
        return f"{role.name} wird von Discord verwaltet (Bot- oder Booster-Rolle)."
    oben = getattr(ich, "top_role", None)
    if oben is not None and role >= oben:
        return f"{role.name} steht über der Rolle des Bots."
    rechte = getattr(ich, "guild_permissions", None)
    if rechte is not None and not getattr(rechte, "manage_roles", False):
        return "Dem Bot fehlt das Recht »Rollen verwalten«."
    return ""


async def swap_roles(guild, member, *, add=None, remove=None, reason: str = ""):
    """
    Rollen tauschen: erst geben, dann nehmen.

    Gibt ``(vergeben, entfernt, gescheitert)`` zurueck -- drei Listen
    von Namen. Was scheitert, wird nicht verschwiegen: das muss
    jemand von Hand nachtragen, und dafuer muss er davon wissen.
    """
    import discord

    vergeben: list[str] = []
    entfernt: list[str] = []
    gescheitert: list[str] = []

    if guild is None or member is None:
        return vergeben, entfernt, gescheitert

    hat = {int(getattr(r, "id", 0)) for r in getattr(member, "roles", []) or []}

    # 1. Geben.
    verlangt = 0
    geglueckt = 0
    for rolle in add or []:
        if rolle is None:
            continue
        verlangt += 1
        grund = _blocked(guild, rolle)
        if grund:
            gescheitert.append(grund)
            continue
        if int(rolle.id) in hat:
            # Schon da -- kein Fehlschlag, das Ziel ist erreicht.
            geglueckt += 1
            continue
        try:
            await member.add_roles(rolle, reason=reason[:400] or "Team-Update")
            vergeben.append(rolle.name)
            geglueckt += 1
        except discord.Forbidden:
            gescheitert.append(f"{rolle.name} (keine Berechtigung)")
        except discord.HTTPException as exc:
            gescheitert.append(f"{rolle.name} ({exc})")

    # 1b. Hat das Geben nicht vollstaendig geklappt, wird NICHTS
    #     entfernt.
    #
    # Nachgemessen, nicht vermutet: das Repro-Skript hat genau hier
    # zugeschlagen. Die Reihenfolge "erst geben, dann nehmen" allein
    # schuetzt gar nichts -- sie sorgt nur dafuer, dass der Fehlschlag
    # frueh bekannt ist. Ohne diesen Abbruch lief die Schleife
    # darunter trotzdem durch, und wer wegen einer zu hohen Rolle
    # nicht befoerdert werden konnte, verlor stattdessen die Rolle,
    # die er hatte. Aus einer gescheiterten Befoerderung wurde ein
    # stiller Rauswurf.
    if verlangt and geglueckt < verlangt:
        gescheitert.append(
            "Die alte Rolle wurde deshalb nicht entfernt — der bisherige "
            "Stand bleibt bestehen."
        )
        return vergeben, entfernt, gescheitert

    # 2. Nehmen. Erst jetzt -- siehe Modul-Docstring.
    for rolle in remove or []:
        if rolle is None:
            continue
        # Eine Rolle, die gleichzeitig gegeben werden sollte, nicht
        # sofort wieder abziehen. Passiert, wenn jemand versehentlich
        # dieselbe Rolle als alte und neue angibt.
        if any(getattr(r, "id", None) == rolle.id for r in add or []):
            continue
        grund = _blocked(guild, rolle)
        if grund:
            gescheitert.append(grund)
            continue
        if int(rolle.id) not in hat:
            continue
        try:
            await member.remove_roles(rolle, reason=reason[:400] or "Team-Update")
            entfernt.append(rolle.name)
        except discord.Forbidden:
            gescheitert.append(f"{rolle.name} (keine Berechtigung)")
        except discord.HTTPException as exc:
            gescheitert.append(f"{rolle.name} ({exc})")

    return vergeben, entfernt, gescheitert


def team_roles_of(guild, member, settings: dict) -> list:
    """Welche der eingestellten Teamrollen die Person wirklich hat."""

    gewuenscht = {int(r) for r in settings.get("team_roles") or []}
    # Ohne eigene Liste zaehlen die Rollen, die entscheiden duerfen:
    # ein Server, der nur »Wer darf die Befehle nutzen« gefuellt hat,
    # soll bei /teamkick nicht mit leeren Haenden dastehen.
    if not gewuenscht:
        gewuenscht = {int(r) for r in settings.get("staff_roles") or []}
    if not gewuenscht or member is None:
        return []
    return [
        rolle for rolle in getattr(member, "roles", []) or []
        if int(getattr(rolle, "id", 0)) in gewuenscht
    ]


# ── Text ─────────────────────────────────────────────────────────────


def build_values(
    guild, member, *, old_role=None, new_role=None, reason: str = "",
    signers: list[int] | None = None, actor_id: int | None = None,
    warn_count: int = 0,
) -> dict:
    """Die Platzhalter fuer die Vorlage."""

    import time as _time

    def name_of(rolle) -> str:
        return getattr(rolle, "name", "") if rolle is not None else ""

    def mention_of(rolle) -> str:
        return rolle.mention if rolle is not None else "—"

    return {
        "user": getattr(member, "mention", f"<@{getattr(member, 'id', 0)}>"),
        "user_name": getattr(member, "display_name", "")
        or getattr(member, "name", ""),
        "user_id": str(getattr(member, "id", "")),
        "alt": mention_of(old_role),
        "alt_name": name_of(old_role) or "—",
        "neu": mention_of(new_role),
        "neu_name": name_of(new_role) or "—",
        "grund": reason or "—",
        "unterschriften": store.signature_line(signers or []) or "—",
        "actor": f"<@{actor_id}>" if actor_id else "—",
        "server": getattr(guild, "name", ""),
        "anzahl": str(warn_count),
        # Discords eigener Zeitstempel: er zeigt jedem seine eigene
        # Zeitzone an, statt die des Servers.
        "datum": f"<t:{int(_time.time())}:F>",
    }


# ── Ankuendigung ─────────────────────────────────────────────────────


async def announce(bot, guild, action: str, settings: dict, templates: dict,
                   values: dict, *, ping_ids: list[int] | None = None):
    """
    Die Ankuendigung senden.

    Gibt ``(gesendet, kanal_id, hinweis)`` zurueck. Ein Fehlschlag ist
    kein Abbruch: die Rollen sind zu dem Zeitpunkt schon gesetzt, und
    daran soll ein fehlendes Schreibrecht nichts aendern.
    """
    import discord

    from utils.panels import Panel

    vorlage = templates.get(action) or {}
    if not vorlage.get("enabled", True):
        return False, "", "Die Ankündigung ist für diese Aktion ausgeschaltet."

    kanal_id = store.channel_for(settings, action)
    if not kanal_id:
        return False, "", "Es ist kein Kanal eingestellt."

    kanal = guild.get_channel(int(kanal_id)) if guild else None
    if kanal is None:
        return False, kanal_id, "Der eingestellte Kanal existiert nicht mehr."

    ich = getattr(guild, "me", None)
    if ich is not None:
        try:
            rechte = kanal.permissions_for(ich)
            if not (rechte.view_channel and rechte.send_messages):
                return False, kanal_id, f"Keine Schreibrechte in #{kanal.name}."
        except Exception:
            pass

    text = store.render(vorlage.get("body", ""), values)
    titel = store.render(vorlage.get("title", ""), values)

    # Erwaehnungen muessen IN die Karte.
    #
    # `Panel` ist eine LayoutView (Components V2). Discord lehnt eine
    # Nachricht mit `content=` UND einer LayoutView mit Fehler 50035
    # ab -- ein Ping neben der Karte ist also nicht nur haesslich,
    # sondern verhindert das Senden ganz.
    if ping_ids:
        erwaehnungen = " ".join(f"<@{int(i)}>" for i in ping_ids if str(i).isdigit())
        if erwaehnungen:
            text = f"{erwaehnungen}\n\n{text}"

    karte = Panel(
        titel,
        text,
        accent=int(vorlage.get("colour") or store.DEFAULT_COLOURS.get(action, 0x3B82F6)),
    )

    # Nur die Person, um die es geht, darf gepingt werden -- keine
    # Rollen, kein @everyone, auch wenn im Text von Hand eines steht.
    erlaubt = discord.AllowedMentions(
        everyone=False,
        roles=False,
        users=[discord.Object(id=int(i)) for i in (ping_ids or [])
               if str(i).isdigit()] or False,
    )

    try:
        await kanal.send(view=karte, allowed_mentions=erlaubt)
        return True, kanal_id, ""
    except discord.Forbidden:
        return False, kanal_id, f"Keine Schreibrechte in #{kanal.name}."
    except discord.HTTPException as exc:
        logger.warning(f"[team_update] Ankündigung fehlgeschlagen: {exc}")
        return False, kanal_id, f"Discord lehnte ab: {exc}"


async def send_dm(bot, guild, member, action: str, templates: dict, values: dict):
    """Die DM an die betroffene Person. Geschlossene DMs sind kein Fehler."""

    import discord

    from utils.cv2 import CV2

    vorlage = templates.get(action) or {}
    text = store.render(vorlage.get("dm_body", ""), values)
    if not text.strip():
        return False

    titel = store.render(vorlage.get("title", ""), values) or "Team-Update"

    nutzer = member
    if nutzer is None:
        return False
    try:
        await nutzer.send(view=CV2(titel, text))
        return True
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        return False


# ── Die Aktionen ─────────────────────────────────────────────────────


async def run_action(
    bot,
    guild,
    member,
    action: str,
    *,
    old_role=None,
    new_role=None,
    reason: str = "",
    signers: list[int] | None = None,
    actor_id: int | None = None,
    source: str = "command",
    settings: dict | None = None,
    templates: dict | None = None,
) -> Result:
    """
    Eine Team-Aktion vollstaendig ausfuehren.

    Rollen, Ankuendigung, DM, Akte, Protokoll -- in dieser
    Reihenfolge. Die Rollen zuerst, weil alles andere sie beschreibt:
    eine Ankuendigung ueber eine Befoerderung, die gar nicht
    stattgefunden hat, waere schlimmer als gar keine.
    """
    ergebnis = Result(action, getattr(member, "id", 0))

    if settings is None:
        settings = await store.get_settings(guild.id)
    if templates is None:
        templates = await store.get_templates(guild.id)

    unterschriften = list(signers or [])
    if actor_id and int(actor_id) not in [int(s) for s in unterschriften]:
        unterschriften.insert(0, int(actor_id))
    unterschriften = unterschriften[:store.MAX_SIGNERS]

    # 1. Rollen.
    geben, nehmen = [], []
    if action == store.ACTION_UPRANK or action == store.ACTION_DOWNRANK:
        if new_role is not None:
            geben.append(new_role)
        if old_role is not None:
            nehmen.append(old_role)
    elif action == store.ACTION_JOIN:
        if new_role is not None:
            geben.append(new_role)
    elif action == store.ACTION_KICK:
        nehmen.extend(team_roles_of(guild, member, settings))
        if old_role is not None and old_role not in nehmen:
            nehmen.append(old_role)
    # Bei einer Verwarnung bleibt die Rollenlage unberuehrt -- die
    # etwaige Folge laeuft als eigene Aktion.

    if geben or nehmen:
        vergeben, entfernt, gescheitert = await swap_roles(
            guild, member, add=geben, remove=nehmen,
            reason=f"{store.ACTION_LABELS.get(action, action)}: {reason}"[:400],
        )
        ergebnis.given = vergeben
        ergebnis.removed = entfernt
        ergebnis.failed = gescheitert

    # 2. Verwarnung zaehlen -- vor der Ankuendigung, weil die Zahl
    #    darin vorkommt.
    if action == store.ACTION_WARN:
        await store.add_warn(
            guild.id, member.id, reason,
            actor_id=actor_id, signers=unterschriften,
        )
        ergebnis.warn_count = await store.count_warns(
            guild.id, member.id,
            expire_days=int(settings.get("warn_expire_days") or 0),
        )
        ergebnis.followup = store.followup_due(settings, ergebnis.warn_count)

    # 3. Akte.
    if action in (store.ACTION_UPRANK, store.ACTION_DOWNRANK, store.ACTION_JOIN):
        await store.set_member(
            guild.id, member.id,
            int(new_role.id) if new_role is not None else None,
            source=source,
        )
    elif action == store.ACTION_KICK:
        await store.remove_member(guild.id, member.id)

    # 4. Ereignis eintragen.
    ergebnis.event_id = await store.add_event(
        guild.id, member.id, action,
        old_role_id=int(old_role.id) if old_role is not None else None,
        new_role_id=int(new_role.id) if new_role is not None else None,
        reason=reason, signers=unterschriften, actor_id=actor_id,
        source=source,
    )

    # 5. Ankuendigung.
    werte = build_values(
        guild, member, old_role=old_role, new_role=new_role, reason=reason,
        signers=unterschriften, actor_id=actor_id,
        warn_count=ergebnis.warn_count,
    )
    ping = [int(member.id)] if settings.get("ping_user") else []
    gesendet, kanal_id, hinweis = await announce(
        bot, guild, action, settings, templates, werte, ping_ids=ping
    )
    ergebnis.announced = gesendet
    ergebnis.channel_id = kanal_id
    if hinweis:
        ergebnis.note = hinweis

    # 6. DM.
    if settings.get("dm_user"):
        ergebnis.dm_sent = await send_dm(
            bot, guild, member, action, templates, werte
        )

    return ergebnis


async def apply_followup(bot, guild, member, settings, templates, result: Result,
                         *, actor_id: int | None = None) -> Result | None:
    """
    Die Folge nach zu vielen Verwarnungen ausfuehren.

    Getrennt vom Verwarnen selbst, damit beide Ereignisse einzeln in
    der Akte stehen: "verwarnt" und "deshalb zurueckgestuft" sind
    zwei Vorgaenge, und wer spaeter nachliest, will beide sehen.
    """
    if result.followup == store.FOLLOWUP_NONE:
        return None

    grund = (
        f"Automatisch: {result.warn_count} Verwarnungen "
        f"(Schwelle {settings.get('warn_threshold')})"
    )

    if result.followup == store.FOLLOWUP_KICK:
        return await run_action(
            bot, guild, member, store.ACTION_KICK,
            reason=grund, actor_id=actor_id, source="auto",
            settings=settings, templates=templates,
        )

    # Rueckstufung: die aktuelle Teamrolle runter, die eingestellte
    # Zielrolle drauf. Ohne Zielrolle bleibt es beim Entfernen -- das
    # ist immer noch eine Rueckstufung, nur eben auf nichts.
    aktuell = team_roles_of(guild, member, settings)
    ziel_id = str(settings.get("warn_downrank_role_id") or "")
    ziel = guild.get_role(int(ziel_id)) if ziel_id.isdigit() else None
    # Die Zielrolle nicht gleich wieder abziehen, falls sie schon da ist.
    alt = next((r for r in aktuell if ziel is None or r.id != ziel.id), None)

    return await run_action(
        bot, guild, member, store.ACTION_DOWNRANK,
        old_role=alt, new_role=ziel,
        reason=grund, actor_id=actor_id, source="auto",
        settings=settings, templates=templates,
    )


# ── Bruecke zu den Bewerbungen ───────────────────────────────────────


async def from_application(bot, guild, member, category: dict, *,
                           actor_id: int | None = None) -> Result | None:
    """
    Eine angenommene Bewerbung ins Team uebernehmen.

    Wird von beiden Wegen aufgerufen, die eine Bewerbung annehmen
    koennen: den Knoepfen in Discord und dem Dashboard.

    Gibt ``None`` zurueck, wenn nichts zu tun ist -- die Uebernahme
    ist aus, oder es ist kein Server bzw. Mitglied da. Das ist der
    Normalfall und kein Fehler.

    Die Rollen selbst vergibt weiterhin ``application_store``: sie
    stehen in der Kategorie, koennen bis zu fuenf sein, und dieses
    Modul soll die Zustaendigkeit nicht an sich ziehen. Hier kommt
    dazu: Akteneintrag, Ankuendigung und DM.
    """
    if guild is None or member is None:
        return None

    settings = await store.get_settings(guild.id)
    if not settings.get("enabled") or not settings.get("app_enabled"):
        return None

    # Welche Rolle in der Ankuendigung steht: die erste der Rollen,
    # die die Kategorie beim Annehmen vergibt.
    rollen = [r for r in (category or {}).get("accept_roles") or []
              if str(r).isdigit()]
    neue = guild.get_role(int(rollen[0])) if rollen else None

    templates = await store.get_templates(guild.id)
    ergebnis = await run_action(
        bot, guild, member, store.ACTION_JOIN,
        new_role=neue,
        reason=f"Bewerbung angenommen: {(category or {}).get('name', '')}".strip(),
        actor_id=actor_id, source="application",
        settings=settings, templates=templates,
    )
    return ergebnis
