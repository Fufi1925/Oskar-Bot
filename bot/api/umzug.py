"""
Vollstaendiger Umzug: alles herunterladen, woanders wieder einspielen.

Warum es das zusaetzlich zu config_transfer.py gibt
---------------------------------------------------
`config_transfer` arbeitet auf **Zeilenebene**: es liest Tabellen aus,
schreibt JSON und spielt die Zeilen einzeln zurueck. Das ist richtig,
wenn man die Einstellungen EINES Servers auf einen ANDEREN kopieren
will -- dafuer wurde es gebaut.

Fuer einen Kontowechsel ist es der falsche Weg. Nachgemessen in
`repro/bug_umzug_leer.py` gegen ein frisches, leeres Volume:

    exportiert:  4 Zeilen aus 2 Datenbanken
    angekommen:  0 Zeilen
    uebersprungen:
      - tickets.db (no such database)
      - welcome.db (no such database)

Der Import meldete dabei **keinen Fehler**. Er sagt "fertig", und der
Server ist leer. Der Grund steht in config_transfer.py Zeile 507 und
520: fehlt die Datei oder die Tabelle, wird die Zeile still
uebersprungen. Auf einem neuen Railway-Konto fehlt aber genau alles,
was noch kein Cog angelegt hat.

Dazu kommt: `db/template_secret.key` ist ueberhaupt keine Datenbank.
Der Schluessel entschluesselt die gespeicherten Zugangscodes der
Community-Vorlagen. Ohne ihn sind die Codes nach dem Umzug
unbrauchbar -- auch das ist nachgemessen (`repro/bug_umzug.py`,
Posten "DATEI db/template_secret.key: 1 -> 0").

Was dieses Modul stattdessen macht
----------------------------------
Es kopiert die **Dateien selbst** in ein ZIP:

  * jede SQLite-Datei, egal wo sie liegt (auch rr.db und j2c_data.db
    ausserhalb von db/)
  * die JSON-Konfiguration
  * den Schluessel db/template_secret.key
  * alles unter phantom/ (eigener Ticket-Bot mit eigener Datenbank)

Beim Einspielen werden die Dateien zurueckgeschrieben. Damit ist
nichts "uebersprungen", weil nichts zeilenweise interpretiert wird:
eine Datenbankdatei enthaelt ihr Schema selbst. Offene Tickets,
Panel-Nachrichten, eigene Texte, XP, Warnungen -- alles ist Teil der
Datei und damit automatisch dabei.

Sicherheit beim Einspielen
--------------------------
Vor dem Ueberschreiben wird der aktuelle Stand in
`db/backups/vor-umzug-<zeit>/` gesichert. Geht etwas schief, ist der
Weg zurueck da.

Die Namen im Archiv werden streng geprueft: `..` oder ein absoluter
Pfad wuerden sonst Dateien ausserhalb des Datenordners
ueberschreiben (Zip-Slip). Das ist keine theoretische Sorge -- ein
Umzugsarchiv kommt per Upload ins System.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import time
import zipfile

# Wie das Archiv aufgebaut ist. Steht in der Datei selbst, damit ein
# spaeterer Stand ein aelteres Archiv noch lesen kann.
ARCHIV_VERSION = 1

#: Name der Beschreibungsdatei im Archiv.
INFO_NAME = "umzug-info.json"

#: Ordner, die vollstaendig mitgenommen werden (rekursiv).
ORDNER = (
    "db",
    "jsondb",
)

#: Einzelne Dateien ausserhalb dieser Ordner.
EINZELDATEIEN = (
    "rr.db",
    "j2c_data.db",
    "ignore.json",
    "channels.json",
)

#: Dateiendungen, die beim Sichern uebersprungen werden. Die
#: Journal-/WAL-Dateien gehoeren zu einer offenen Datenbank und sind
#: ohne sie wertlos; mitkopiert koennen sie eine gesunde Datei sogar
#: beschaedigen.
UEBERSPRINGEN = (".db-journal", ".db-wal", ".db-shm")

#: Unterordner, die nicht mitkommen. `backups` enthaelt alte Staende --
#: die wuerden das Archiv vervielfachen.
AUSGESCHLOSSEN = {"backups"}


def _daten_wurzel() -> str:
    """
    Der Ordner, in dem der Bot seine Daten haelt.

    Auf Railway zeigt DATA_DIR auf das gemountete Volume; lokal ist es
    das Arbeitsverzeichnis des Bots.
    """
    return os.getcwd()


def _ist_sicher(name: str) -> bool:
    """
    Darf dieser Name aus einem fremden Archiv geschrieben werden?

    Verhindert Zip-Slip: ein Eintrag wie `../../etc/passwd` oder
    `/etc/passwd` wuerde beim Entpacken ausserhalb des Datenordners
    landen. Ein Umzugsarchiv kommt per Upload herein, also wird hier
    nichts geglaubt.
    """
    if not name or name.endswith("/"):
        return False
    if os.path.isabs(name) or name.startswith("/") or name.startswith("\\"):
        return False
    # Windows-Laufwerksbuchstaben und UNC-Pfade.
    if len(name) > 1 and name[1] == ":":
        return False
    teile = name.replace("\\", "/").split("/")
    if any(t in ("..", "") for t in teile):
        return False
    return True


def sammle_dateien() -> list[str]:
    """
    Jede Datei, die zu einem vollstaendigen Umzug gehoert.

    Rueckgabe sind Pfade relativ zum Datenordner.
    """
    wurzel = _daten_wurzel()
    gefunden: list[str] = []

    for ordner in ORDNER:
        basis = os.path.join(wurzel, ordner)
        if not os.path.isdir(basis):
            continue
        for pfad, unterordner, dateien in os.walk(basis):
            # Alte Sicherungen nicht mit einpacken.
            unterordner[:] = [u for u in unterordner if u not in AUSGESCHLOSSEN]
            for name in dateien:
                if name.endswith(UEBERSPRINGEN):
                    continue
                voll = os.path.join(pfad, name)
                gefunden.append(os.path.relpath(voll, wurzel))

    for name in EINZELDATEIEN:
        voll = os.path.join(wurzel, name)
        if os.path.isfile(voll):
            gefunden.append(name)

    # Der eigene Ticket-Bot liegt eine Ebene hoeher neben bot/.
    phantom = os.path.join(os.path.dirname(wurzel), "phantom", "data")
    if os.path.isdir(phantom):
        for pfad, _u, dateien in os.walk(phantom):
            for name in dateien:
                if name.endswith(UEBERSPRINGEN):
                    continue
                voll = os.path.join(pfad, name)
                # Als "phantom/data/..." ablegen, damit der Weg zurueck
                # eindeutig ist.
                gefunden.append(
                    os.path.join(
                        "phantom", os.path.relpath(voll, os.path.dirname(phantom))
                    )
                )

    return sorted(set(gefunden))


def _voller_pfad(rel: str) -> str:
    """Wo eine Archivdatei im Dateisystem liegt."""
    wurzel = _daten_wurzel()
    if rel.startswith("phantom/"):
        return os.path.join(os.path.dirname(wurzel), rel)
    return os.path.join(wurzel, rel)


def _zaehle_zeilen(pfad: str) -> dict[str, int] | None:
    """
    Zeilen je Tabelle -- nur zur Anzeige.

    Gibt None zurueck, wenn die Datei keine lesbare SQLite-Datei ist.
    """
    try:
        conn = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True)
    except Exception:
        return None
    try:
        namen = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        ergebnis = {}
        for tab in namen:
            try:
                ergebnis[tab] = conn.execute(
                    f"SELECT COUNT(*) FROM [{tab}]"
                ).fetchone()[0]
            except Exception:
                continue
        return ergebnis
    except Exception:
        return None
    finally:
        conn.close()


def baue_uebersicht() -> dict:
    """
    Was wuerde ein Umzugsarchiv enthalten?

    Wird im Dashboard angezeigt, bevor jemand auf Herunterladen
    drueckt -- damit sichtbar ist, dass wirklich alles dabei ist.
    """
    dateien = sammle_dateien()
    eintraege = []
    gesamt_bytes = 0
    gesamt_zeilen = 0

    for rel in dateien:
        voll = _voller_pfad(rel)
        try:
            groesse = os.path.getsize(voll)
        except OSError:
            continue
        gesamt_bytes += groesse

        tabellen = _zaehle_zeilen(voll) if rel.endswith(".db") else None
        zeilen = sum(tabellen.values()) if tabellen else 0
        gesamt_zeilen += zeilen

        eintraege.append(
            {
                "pfad": rel,
                "bytes": groesse,
                "ist_datenbank": tabellen is not None,
                "tabellen": len(tabellen) if tabellen else 0,
                "zeilen": zeilen,
            }
        )

    eintraege.sort(key=lambda e: (-e["bytes"], e["pfad"]))

    return {
        "dateien": eintraege,
        "datei_anzahl": len(eintraege),
        "bytes_gesamt": gesamt_bytes,
        "zeilen_gesamt": gesamt_zeilen,
        "datenbanken": sum(1 for e in eintraege if e["ist_datenbank"]),
    }


def _info_block() -> dict:
    """Die Beschreibung, die oben ins Archiv gelegt wird."""
    uebersicht = baue_uebersicht()
    return {
        "archiv_version": ARCHIV_VERSION,
        "erstellt_am": int(time.time()),
        "erstellt_am_text": time.strftime("%d.%m.%Y %H:%M:%S"),
        "datei_anzahl": uebersicht["datei_anzahl"],
        "bytes_gesamt": uebersicht["bytes_gesamt"],
        "zeilen_gesamt": uebersicht["zeilen_gesamt"],
        "dateien": [e["pfad"] for e in uebersicht["dateien"]],
        "hinweis": (
            "Vollstaendiger Umzug. Enthaelt die Datenbankdateien selbst, "
            "nicht nur ausgelesene Zeilen -- damit sind offene Tickets, "
            "Panel-Nachrichten, eigene Texte und der Schluessel "
            "db/template_secret.key mit dabei."
        ),
    }


def schreibe_archiv_nach(ziel):
    """
    Das Umzugsarchiv in einen offenen Datei-/Pufferzeiger schreiben.

    Bewusst nicht als Rueckgabe eines fertigen bytes-Objekts: ein
    Archiv kann mehrere Gigabyte gross werden, und der Container hat
    davon nicht beliebig viel. So wandert es Datei fuer Datei hinein.
    """
    dateien = sammle_dateien()

    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archiv:
        archiv.writestr(
            INFO_NAME, json.dumps(_info_block(), ensure_ascii=False, indent=2)
        )
        for rel in dateien:
            voll = _voller_pfad(rel)
            if not os.path.isfile(voll):
                continue
            try:
                archiv.write(voll, rel)
            except Exception as exc:  # eine unlesbare Datei darf nicht alles kippen
                print(f"[umzug] uebersprungen {rel}: {exc}")

    return dateien


def pruefe_archiv_datei(pfad: str) -> dict:
    """
    Wie pruefe_archiv(), aber liest von der Platte statt aus dem
    Arbeitsspeicher.

    Das ist der Weg, den die API benutzt: ein Umzugsarchiv kann
    mehrere Gigabyte gross sein, und `zipfile` liest aus einer Datei
    ohnehin nur die Teile, die es gerade braucht.
    """
    try:
        archiv = zipfile.ZipFile(pfad)
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Das ist keine gueltige ZIP-Datei: {exc}") from exc
    return _pruefe_offenes_archiv(archiv)


def pruefe_archiv(rohdaten: bytes) -> dict:
    """
    Ein hochgeladenes Archiv ansehen, ohne etwas zu veraendern.

    Sagt, was drin ist und was beim Einspielen passieren wuerde.
    """
    try:
        archiv = zipfile.ZipFile(io.BytesIO(rohdaten))
    except zipfile.BadZipFile as exc:
        raise ValueError(f"Das ist keine gueltige ZIP-Datei: {exc}") from exc
    return _pruefe_offenes_archiv(archiv)


def _pruefe_offenes_archiv(archiv: zipfile.ZipFile) -> dict:
    """Die gemeinsame Auswertung -- egal, woher das Archiv kommt."""
    namen = [n for n in archiv.namelist() if not n.endswith("/")]

    info = {}
    if INFO_NAME in namen:
        try:
            info = json.loads(archiv.read(INFO_NAME).decode("utf-8"))
        except Exception:
            info = {}

    nutzdateien = [n for n in namen if n != INFO_NAME]
    unsicher = [n for n in nutzdateien if not _ist_sicher(n)]
    sicher = [n for n in nutzdateien if _ist_sicher(n)]

    if not sicher:
        raise ValueError(
            "Das Archiv enthaelt keine verwertbaren Dateien. "
            "Stammt es wirklich aus 'Alles herunterladen'?"
        )

    eintraege = []
    for name in sorted(sicher):
        eintrag = archiv.getinfo(name)
        vorhanden = os.path.isfile(_voller_pfad(name))
        eintraege.append(
            {
                "pfad": name,
                "bytes": eintrag.file_size,
                "ueberschreibt": vorhanden,
            }
        )

    archiv.close()

    return {
        "archiv_version": info.get("archiv_version"),
        "erstellt_am": info.get("erstellt_am"),
        "erstellt_am_text": info.get("erstellt_am_text"),
        "zeilen_gesamt": info.get("zeilen_gesamt"),
        "dateien": eintraege,
        "datei_anzahl": len(eintraege),
        "bytes_gesamt": sum(e["bytes"] for e in eintraege),
        "ueberschreibt_anzahl": sum(1 for e in eintraege if e["ueberschreibt"]),
        "abgelehnt": unsicher,
    }


def spiele_datei_ein(pfad: str, *, sicherung: bool = True) -> dict:
    """
    Wie spiele_archiv_ein(), aber von der Platte.

    Der Weg, den die API nimmt -- siehe pruefe_archiv_datei().
    """
    return _spiele_ein(zipfile.ZipFile(pfad), pruefe_archiv_datei(pfad),
                       sicherung=sicherung)


def spiele_archiv_ein(rohdaten: bytes, *, sicherung: bool = True) -> dict:
    """
    Ein Umzugsarchiv zurueckschreiben.

    Vorher wird der aktuelle Stand weggesichert, ausser das wird
    ausdruecklich abgeschaltet.
    """
    bericht = pruefe_archiv(rohdaten)  # prueft und wirft bei Unsinn
    return _spiele_ein(zipfile.ZipFile(io.BytesIO(rohdaten)), bericht,
                       sicherung=sicherung)


def _spiele_ein(archiv: zipfile.ZipFile, bericht: dict, *,
                sicherung: bool = True) -> dict:
    """Das eigentliche Zurueckschreiben -- gemeinsam fuer beide Wege."""

    sicherungs_ordner = ""
    if sicherung:
        stempel = time.strftime("%Y%m%d-%H%M%S")
        sicherungs_ordner = os.path.join("db", "backups", f"vor-umzug-{stempel}")
        ziel = os.path.join(_daten_wurzel(), sicherungs_ordner)
        os.makedirs(ziel, exist_ok=True)
        for rel in sammle_dateien():
            quelle = _voller_pfad(rel)
            if not os.path.isfile(quelle):
                continue
            abgelegt = os.path.join(ziel, rel.replace("/", "__"))
            try:
                shutil.copy2(quelle, abgelegt)
            except Exception as exc:
                print(f"[umzug] Sicherung von {rel} fehlgeschlagen: {exc}")

    geschrieben: list[str] = []
    fehlgeschlagen: list[str] = []

    for eintrag in bericht["dateien"]:
        name = eintrag["pfad"]
        ziel = _voller_pfad(name)
        try:
            ordner = os.path.dirname(ziel)
            if ordner:
                os.makedirs(ordner, exist_ok=True)
            # Erst daneben schreiben, dann umbenennen. Bricht der
            # Vorgang mittendrin ab, steht keine halbe Datenbankdatei
            # an der richtigen Stelle.
            vorlaeufig = f"{ziel}.umzug-neu"
            with archiv.open(name) as quelle, open(vorlaeufig, "wb") as senke:
                shutil.copyfileobj(quelle, senke, length=1024 * 1024)
            os.replace(vorlaeufig, ziel)
            geschrieben.append(name)
        except Exception as exc:
            fehlgeschlagen.append(f"{name}: {exc}")

    archiv.close()

    # Journal-Reste der ALTEN Datenbank wuerden sich ueber die frisch
    # eingespielte Datei legen und sie beschaedigen: SQLite spielt beim
    # naechsten Oeffnen ein vorgefundenes Journal zurueck, und das
    # gehoert dann zu einer Datei, die es nicht mehr gibt.
    for name in geschrieben:
        if not name.endswith(".db"):
            continue
        basis = _voller_pfad(name)
        for endung in ("-journal", "-wal", "-shm"):
            rest = basis + endung
            if os.path.exists(rest):
                try:
                    os.remove(rest)
                except OSError:
                    pass

    return {
        "geschrieben": len(geschrieben),
        "dateien": geschrieben,
        "fehlgeschlagen": fehlgeschlagen,
        "sicherung": sicherungs_ordner,
        "abgelehnt": bericht["abgelehnt"],
    }
