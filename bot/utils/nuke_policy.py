"""
Die Regeln des Anti-Nuke-Systems -- an genau einer Stelle.

Warum diese Datei
-----------------
Bisher entschied jedes der siebzehn Module selbst, wann es meldet,
wann es eine DM schickt und wann es einen Kanal anlegt. Das Ergebnis
war Laerm: eine DM, weil dem Bot ein Recht fehlte. Ein neuer Kanal,
weil jemand eine Rolle vergeben hatte. Ein Alarm, obwohl das System
ausgeschaltet war und gar nichts getan wurde.

Hier steht jetzt in einem Stueck, was erlaubt ist. Die Module fragen
nach, statt selbst zu entscheiden.

Die fuenf Regeln
----------------
1. **Konnte der Bot nichts ausrichten, passiert gar nichts.**
   Kein Log, keine DM, kein Kanal. Wenn ihm das Recht fehlt oder er
   die Audit-Logs nicht lesen darf, hat er den Angriff nicht
   gestoppt -- und eine Meldung darueber ist nur Laerm in einem
   Moment, in dem ohnehin nichts geschuetzt wird.

2. **Wiederhergestellt wird nur nach einem echten Nuke.**
   Also: Kanaele wurden geloescht. Alles andere -- eine Rolle zu
   viel, ein Webhook, ein Bann -- ist ein Vorfall, aber kein Nuke,
   und rechtfertigt keinen Wiederaufbau.

3. **Die DM an den Inhaber kommt nur bei einem Nuke.**

4. **Ein Kanal wird nur angelegt, wenn wirklich genukt wurde.**
   Bei einer Rollenvergabe bleibt es beim Logeintrag.

5. **Die DM kommt nur, wenn jemand gebannt wurde.**
   Sie meldet eine Tat, keine Vermutung.

Regel 3 und 5 zusammen heissen: **DM nur, wenn ein echter Nuke lief
UND der Bot jemanden gebannt hat.** Beides muss zutreffen. Das ist
die engste der beiden Lesarten und die richtige: eine DM ist die
lauteste Meldung, die es gibt -- sie erreicht den Inhaber auch
nachts.
"""

from __future__ import annotations

import time

# ── Was ueberhaupt ein Nuke ist ──────────────────────────────────────
#
# Die Frage entscheidet fast alles hier, deshalb steht sie ganz oben.
#
# Ein Nuke zerstoert den Server so, dass er ohne Hilfe nicht
# zurueckkommt: Kanaele weg, Rollen weg, Mitglieder rausgeworfen. Das
# sind die Aktionen, bei denen Wiederaufbau und DM angebracht sind.
NUKE_ACTIONS = frozenset(
    {
        "channel_delete",   # der Klassiker
        "role_delete",
        "prune",            # Massenrauswurf
        "guild_update",     # Servername/Icon zerschossen
    }
)

# Alles andere ist ein Vorfall: bemerkenswert, protokollierenswert --
# aber kein Grund, den Server neu aufzubauen oder den Inhaber nachts
# zu wecken.
#
# `channel_create` steht bewusst NICHT bei den Nukes. Ein Angreifer
# legt beim Spammen hunderte Kanaele an, aber nichts geht dabei
# verloren; das Aufraeumen erledigt `clean_created_channels`.
INCIDENT_ONLY = frozenset(
    {
        "channel_create",
        "channel_update",
        "role_create",
        "role_update",
        "member_update",     # Rolle vergeben -- Punkt 4 des Nutzers
        "ban",
        "kick",
        "webhook_create",
        "webhook_delete",
        "webhook_update",
        "bot_add",
        "integration",
        "everyone",
    }
)


def is_nuke_action(action: str) -> bool:
    """Zerstoert diese Aktion etwas Unwiederbringliches?"""

    return action in NUKE_ACTIONS


# ── Was der Bot ausgerichtet hat ─────────────────────────────────────

# Er hat den Angriff gestoppt: Schaden behoben und/oder gebannt.
OUTCOME_STOPPED = "stopped"
# Schaden behoben, aber der Bann ging nicht durch.
OUTCOME_PARTIAL = "partial"
# Er hat es gesehen und konnte nichts tun.
OUTCOME_NO_PERMS = "no_perms"
# Er kann nicht einmal nachsehen, wer es war.
OUTCOME_BLIND = "blind"
# Das System ist ausgeschaltet.
OUTCOME_DISABLED = "disabled"

# Ergebnisse, bei denen der Bot NICHTS ausgerichtet hat.
#
# Genau hier setzt Punkt 1 an: bei diesen dreien laeuft der Angriff
# weiter, und alles, was das System jetzt noch tut -- Alarmkanal
# anlegen, DM schicken, Embed posten --, ist Laerm. Schlimmer: es
# kostet Zeit und Rate-Limit in dem Moment, in dem der Server
# tatsaechlich angegriffen wird.
POWERLESS = frozenset({OUTCOME_NO_PERMS, OUTCOME_BLIND, OUTCOME_DISABLED})


class Decision:
    """Was in diesem Fall geschehen darf.

    Ein Objekt statt vier lose Rueckgabewerte: die Felder gehoeren
    zusammen, und ein Aufrufer, der eines vergisst, faellt beim Lesen
    auf.
    """

    __slots__ = ("log", "post", "dm", "rebuild", "reason")

    def __init__(self, *, log=False, post=False, dm=False, rebuild=False,
                 reason=""):
        # In die Vorfallsliste schreiben (Dashboard, Verlauf).
        self.log = log
        # Ins Alarm-Kanal posten.
        self.post = post
        # Dem Inhaber eine DM schicken.
        self.dm = dm
        # Wiederherstellung anbieten / Backup-Kanal anlegen.
        self.rebuild = rebuild
        # Warum so entschieden wurde -- steht im Verlauf und macht
        # spaeter nachvollziehbar, warum es still blieb.
        self.reason = reason

    def __repr__(self) -> str:  # pragma: no cover - nur fuer Fehlersuche
        return (
            f"Decision(log={self.log}, post={self.post}, dm={self.dm}, "
            f"rebuild={self.rebuild}, reason={self.reason!r})"
        )

    def __eq__(self, other) -> bool:
        if not isinstance(other, Decision):
            return NotImplemented
        return (
            self.log == other.log
            and self.post == other.post
            and self.dm == other.dm
            and self.rebuild == other.rebuild
        )


# Ein Vorfall ohne jede Reaktion. Bewusst ein eigener Name statt
# `Decision()`: an der Aufrufstelle liest man sofort, dass hier
# absichtlich nichts passiert.
SILENT = Decision(reason="Der Bot konnte nichts ausrichten.")


def decide(
    action: str,
    outcome: str,
    *,
    banned: bool = False,
    enabled: bool = True,
    settings: dict | None = None,
) -> Decision:
    """Was darf in diesem Fall geschehen?

    `action`  was passiert ist (channel_delete, member_update, ...)
    `outcome` was der Bot ausgerichtet hat
    `banned`  ob wirklich jemand gebannt wurde
    `enabled` ob das System eingeschaltet ist

    Die Reihenfolge der Pruefungen ist Absicht: die schaerfste Regel
    zuerst. Wer nichts ausrichten konnte, schweigt -- unabhaengig
    davon, wie schlimm die Tat war.
    """

    settings = settings or {}

    # ── Regel 1: nichts ausgerichtet -> nichts tun ───────────────
    #
    # Das gilt auch fuer den Logeintrag. Ein Verlauf voller "konnte
    # nicht" ist kein Verlauf, sondern eine Fehlerliste -- und sie
    # verdeckt die Eintraege, auf die es ankommt.
    if outcome in POWERLESS:
        return SILENT

    if not enabled:
        return SILENT

    # ── Ein echter Nuke ──────────────────────────────────────────
    if is_nuke_action(action):
        return Decision(
            log=True,
            post=True,
            # Regel 3 + 5: DM nur bei einem Nuke UND nur, wenn
            # wirklich jemand gebannt wurde. Beides muss zutreffen.
            # Ein Nuke ohne Bann heisst, dass der Angreifer noch da
            # ist -- dann steht es im Kanal, aber die DM wartet, bis
            # der Bot durchgegriffen hat.
            dm=banned and bool(settings.get("dm_owner", True)),
            # Regel 2 + 4: Wiederherstellung und neuer Kanal nur hier.
            rebuild=bool(settings.get("offer_rebuild", True)),
            reason="Echter Nuke -- Schaden ist unwiederbringlich.",
        )

    # ── Regel 4, andere Haelfte: nur ein Logeintrag ──────────────
    #
    # Jemand hat eine Rolle vergeben, einen Webhook angelegt, jemanden
    # gebannt. Das gehoert in den Verlauf -- aber es rechtfertigt
    # keinen Kanal, keine DM und keinen Alarm.
    return Decision(
        log=True,
        post=bool(settings.get("post_incidents", False)),
        dm=False,
        rebuild=False,
        reason="Vorfall, kein Nuke -- nur im Verlauf vermerkt.",
    )


# ── Erkennung: laeuft gerade ein echter Nuke? ────────────────────────
#
# Ein einzelner geloeschter Kanal kann ein Versehen sein. Erst mehrere
# in kurzer Zeit sind ein Angriff. Das zaehlt hier mit, damit die
# Wiederherstellung nicht schon beim ersten Fehlklick anspringt.

# Wie viele zerstoerende Aktionen in `NUKE_WINDOW` Sekunden einen Nuke
# ausmachen.
#
# Zwei, nicht eine: ein einzelner geloeschter Kanal passiert im Alltag
# (jemand raeumt auf und greift daneben). Zwei innerhalb einer Minute
# sind kein Versehen mehr.
NUKE_THRESHOLD = 2
NUKE_WINDOW = 60.0

_recent: dict[int, list[tuple[float, str]]] = {}


def note_action(guild_id: int, action: str) -> int:
    """Eine zerstoerende Aktion vermerken. Gibt die Zahl im Fenster.

    Nur Nuke-Aktionen zaehlen: eine Rollenvergabe soll die Schwelle
    nicht mit erreichen helfen.
    """

    if not is_nuke_action(action):
        return 0

    now = time.time()
    entries = [
        entry for entry in _recent.get(guild_id, [])
        if now - entry[0] <= NUKE_WINDOW
    ]
    entries.append((now, action))
    _recent[guild_id] = entries
    return len(entries)


def is_under_attack(guild_id: int) -> bool:
    """Laeuft gerade ein echter Nuke?"""

    now = time.time()
    entries = [
        entry for entry in _recent.get(guild_id, [])
        if now - entry[0] <= NUKE_WINDOW
    ]
    _recent[guild_id] = entries
    return len(entries) >= NUKE_THRESHOLD


def attack_summary(guild_id: int) -> str:
    """Was in diesem Angriff bisher passiert ist -- kurz."""

    now = time.time()
    entries = [
        entry for entry in _recent.get(guild_id, [])
        if now - entry[0] <= NUKE_WINDOW
    ]
    if not entries:
        return ""

    counts: dict[str, int] = {}
    for _stamp, action in entries:
        counts[action] = counts.get(action, 0) + 1
    return ", ".join(f"{count}× {name}" for name, count in sorted(counts.items()))


def forget(guild_id: int) -> None:
    """Den Zaehler zuruecksetzen -- nach einem abgeschlossenen Angriff."""

    _recent.pop(guild_id, None)
