"""
Bot-Logs: eine Uebersicht ueber alles, was der Bot protokolliert.

Das Problem, das dieser Reiter loest
------------------------------------
Die Protokollierung war ueber das ganze Dashboard verstreut. Wer
wissen wollte, wohin der Bot eigentlich schreibt, musste durch acht
Seiten klicken:

    /logging        neun Discord-Kategorien
    /verification   eigener Log-Kanal
    /honeypot       eigener Log-Kanal
    /automod        eigener Log-Kanal
    /anonchat       eigener Log-Kanal
    /vanityroles    eigener Log-Kanal
    /jail           eigener Log-Kanal
    /antinuke       eigener Meldekanal

Acht Stellen, acht Auswahlfelder, und nirgends eine Antwort auf die
einfachste Frage: *wohin schreibt der Bot gerade ueberall?* Genau die
beantwortet dieser Reiter.

Was hier NICHT hineingehoert
----------------------------
Bewerbungen. Ausdrueckliche Vorgabe -- sie sind kein Protokoll,
sondern ein Vorgang mit Rueckfragen und Entscheidungen, und sie haben
eine eigene Seite mit eigenen Ansichten.

Warum eine Registrierung und keine neunte Tabelle
-------------------------------------------------
Jedes Modul speichert seinen Log-Kanal weiterhin selbst. Alles hierher
zu kopieren hiesse, zwei Wahrheiten zu haben -- und die laufen
auseinander, sobald jemand eine der alten Seiten benutzt. Diese Datei
weiss nur, **wo** die Wahrheit steht, und liest sie beim Aufruf frisch.

Deshalb ist QUELLEN auch die einzige Stelle, an der ein neues Modul
eingetragen werden muss.
"""

from __future__ import annotations

from typing import Any

import aiosqlite


#: Alle Protokoll-Quellen des Bots.
#:
#: Jeder Eintrag beschreibt, wo ein Modul seinen Log-Kanal ablegt --
#: Datenbank, Tabelle, Spalte -- und wie er im Dashboard heisst.
#:
#: `seite` ist der Pfad unter /dashboard/guild/<id>/, auf den der
#: Reiter verlinkt. `abschnitt` benennt den Bereich, der dort
#: hervorgehoben wird, wenn man aus einem anderen Reiter herkommt.
QUELLEN: tuple[dict[str, Any], ...] = (
    {
        "key": "honeypot",
        "label": "Honeypot",
        "beschreibung": (
            "Wer in den Köder-Kanal geschrieben hat und softgebannt wurde."
        ),
        "db": "db/honeypot.db",
        "tabelle": "honeypot",
        "spalte": "log_channel_id",
        "schalter": "enabled",
        "seite": "honeypot",
        "abschnitt": "log",
        "gruppe": "Schutz",
    },
    {
        "key": "verification",
        "label": "Verifizierung",
        "beschreibung": "Wer sich verifiziert hat und wer daran gescheitert ist.",
        "db": "db/verification.db",
        "tabelle": "verification_config",
        "spalte": "log_channel_id",
        "schalter": "enabled",
        "seite": "verification",
        "abschnitt": "log",
        "gruppe": "Schutz",
    },
    {
        "key": "automod",
        "label": "Automod",
        "beschreibung": "Gelöschte Nachrichten und verhängte Strafen.",
        "db": "db/automod.db",
        "tabelle": "automod_logging",
        "spalte": "log_channel",
        "schalter": None,
        "seite": "automod",
        "abschnitt": "log",
        "gruppe": "Schutz",
    },
    {
        "key": "anonchat",
        "label": "Anonymer Chat",
        "beschreibung": "Wer welche anonyme Nachricht geschrieben hat.",
        "db": "db/anonchat.db",
        "tabelle": "anon_channels",
        "spalte": "log_channel_id",
        "schalter": None,
        "seite": "anonchat",
        "abschnitt": "log",
        "gruppe": "Kanäle",
    },
    {
        "key": "vanity",
        "label": "Vanity-Rollen",
        "beschreibung": "Wer eine Rolle für seinen Status bekommen oder verloren hat.",
        "db": "db/vanity.db",
        "tabelle": "vanity_roles",
        "spalte": "log_channel_id",
        "schalter": "enabled",
        "seite": "vanityroles",
        "abschnitt": "log",
        "gruppe": "Rollen",
    },
    {
        "key": "jail",
        "label": "Jail",
        "beschreibung": "Wer eingesperrt und wieder freigelassen wurde.",
        "db": "db/jail.db",
        "tabelle": "jail_settings",
        "spalte": "log_channel",
        "schalter": None,
        # Jail speichert guild_id als TEXT, nicht als INTEGER
        # (extras_store.jail_ensure).
        #
        # Korrektur meiner ersten Begruendung: eine Abfrage mit einer
        # Zahl findet die Zeile TROTZDEM. SQLite hat "type affinity" --
        # bei einer TEXT-Spalte wird die Zahl vor dem Vergleich
        # umgewandelt. Nachgemessen:
        #
        #   Spalte TEXT,    gespeichert '123', gesucht 123  -> gefunden
        #   Spalte INTEGER, gespeichert 123,   gesucht '123' -> gefunden
        #   Spalte OHNE Typ, gespeichert '123', gesucht 123  -> NICHT
        #
        # Die Angabe bleibt trotzdem stehen: sie trifft den
        # gespeicherten Typ, und bei einer Spalte ohne Typangabe --
        # die es in diesem Projekt gibt -- waere sie der Unterschied
        # zwischen "findet" und "findet nicht".
        "id_als_text": True,
        "seite": "jail",
        "abschnitt": "log",
        "gruppe": "Schutz",
    },
)


#: Was ausdruecklich NICHT hier auftaucht.
#:
#: Steht als Liste da, damit die Entscheidung nachlesbar ist und nicht
#: als Vergessen missverstanden wird.
AUSGENOMMEN: tuple[tuple[str, str], ...] = (
    (
        "Bewerbungen",
        "Kein Protokoll, sondern ein Vorgang mit Rückfragen und "
        "Entscheidungen. Eigene Seite unter Bewerbungen.",
    ),
)


async def _lies_kanal(quelle: dict, guild_id: int) -> tuple[int | None, bool]:
    """Den eingestellten Kanal und den Schalterzustand eines Moduls holen.

    Rueckgabe: (kanal_id oder None, ist_eingeschaltet).

    Faengt alles ab: fehlt die Datenbank oder die Tabelle, ist das
    Modul auf diesem Server schlicht nie benutzt worden. Das ist kein
    Fehler, sondern der Normalfall -- und darf die Uebersicht nicht
    zum Absturz bringen, nur weil ein Modul unbenutzt ist.
    """
    try:
        async with aiosqlite.connect(quelle["db"]) as db:
            db.row_factory = aiosqlite.Row

            spalten = [quelle["spalte"]]
            if quelle.get("schalter"):
                spalten.append(quelle["schalter"])

            auswahl = ", ".join(f"[{s}]" for s in spalten)

            # Den Schluessel im gespeicherten Typ abfragen.
            #
            # Bei einer Spalte MIT Typangabe wandelt SQLite selbst um
            # (type affinity) -- da waere es egal. Bei einer Spalte
            # OHNE Typangabe nicht: dort findet 123 die Zeile '123'
            # nicht, und zwar ohne Fehlermeldung. Solche Spalten gibt
            # es in diesem Projekt, deshalb wird der Typ hier
            # ausdruecklich getroffen statt darauf zu vertrauen.
            schluessel = str(guild_id) if quelle.get("id_als_text") else guild_id

            async with db.execute(
                f"SELECT {auswahl} FROM [{quelle['tabelle']}] WHERE guild_id = ?",
                (schluessel,),
            ) as cursor:
                zeile = await cursor.fetchone()
    except Exception:  # noqa: BLE001 - Datei/Tabelle/Spalte fehlt
        return None, False

    if zeile is None:
        return None, False

    roh = zeile[quelle["spalte"]]
    kanal = int(roh) if roh else None

    an = True
    if quelle.get("schalter"):
        an = bool(zeile[quelle["schalter"]])

    return kanal, an


async def uebersicht(guild_id: int, guild=None) -> list[dict]:
    """Jede Quelle mit ihrem aktuellen Stand.

    `guild` ist freiwillig; ist es da, kommt der Kanalname mit -- eine
    nackte ID sagt niemandem etwas.
    """
    ergebnis = []

    for quelle in QUELLEN:
        kanal_id, an = await _lies_kanal(quelle, guild_id)

        name = None
        fehlt = False
        if kanal_id and guild is not None:
            kanal = guild.get_channel(kanal_id)
            if kanal is not None:
                name = kanal.name
            else:
                # Eingestellt, aber es gibt ihn nicht mehr. Das ist der
                # haeufigste Grund fuer "es kommt nichts an", und man
                # sieht es der Einstellung sonst nicht an.
                fehlt = True

        ergebnis.append({
            "key": quelle["key"],
            "label": quelle["label"],
            "beschreibung": quelle["beschreibung"],
            "gruppe": quelle["gruppe"],
            "seite": quelle["seite"],
            "abschnitt": quelle["abschnitt"],
            # Als Zeichenkette: eine Discord-ID ist groesser als das,
            # was JavaScript als Zahl noch genau darstellen kann.
            "channel_id": str(kanal_id) if kanal_id else None,
            "channel_name": name,
            "channel_missing": fehlt,
            "enabled": an,
            "aktiv": bool(kanal_id) and an and not fehlt,
        })

    return ergebnis
