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

import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import time
import zipfile

# Wie das Archiv aufgebaut ist. Steht in der Datei selbst, damit ein
# spaeterer Stand ein aelteres Archiv noch lesen kann.
ARCHIV_VERSION = 2

#: Name der Beschreibungsdatei im Archiv.
INFO_NAME = "umzug-info.json"

#: Ordner, die vollstaendig mitgenommen werden (rekursiv).
ORDNER = (
    "db",
    "jsondb",
    "logs",
    "instructions",
)

#: Persistente Dateien direkt im Bot-Arbeitsordner. Nicht als feste
#: Namensliste: eine neue Funktion mit neuer DB wird dadurch automatisch
#: erfasst, ohne dass der Umzug spaeter nachgezogen werden muss.
PERSISTENTE_ENDUNGEN = (
    ".db", ".sqlite", ".sqlite3", ".json", ".jsonl", ".key", ".enc", ".dat"
)

#: Daten der mitgelieferten Schwester-Dienste. Nur deren Datenordner,
#: niemals Quellcode oder statische Assets.
GESCHWISTER_ORDNER = (
    "phantom/data",
    "louckup/data",
    "lbost-shop/data",
)
GESCHWISTER_DATEI_ORDNER = ("statusbot",)

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

    # Alles Persistente direkt neben db/. Dadurch sind auch neue Root-DBs,
    # Konfigurationen und verschluesselte Dateien ohne Registry-Aenderung da.
    if os.path.isdir(wurzel):
        for name in os.listdir(wurzel):
            voll = os.path.join(wurzel, name)
            if os.path.isfile(voll) and name.lower().endswith(PERSISTENTE_ENDUNGEN):
                if not name.endswith(UEBERSPRINGEN):
                    gefunden.append(name)

    projekt = os.path.dirname(wurzel)
    for relativ in GESCHWISTER_ORDNER:
        basis = os.path.join(projekt, relativ)
        if not os.path.isdir(basis):
            continue
        for pfad, _u, dateien in os.walk(basis):
            for name in dateien:
                if name == ".gitkeep" or name.endswith(UEBERSPRINGEN):
                    continue
                voll = os.path.join(pfad, name)
                gefunden.append(os.path.relpath(voll, projekt))

    # Statusbot schreibt seine JSON-Zustaende direkt in seinen Dienstordner.
    for relativ in GESCHWISTER_DATEI_ORDNER:
        basis = os.path.join(projekt, relativ)
        if not os.path.isdir(basis):
            continue
        for name in os.listdir(basis):
            voll = os.path.join(basis, name)
            if os.path.isfile(voll) and name.lower().endswith(PERSISTENTE_ENDUNGEN):
                gefunden.append(os.path.relpath(voll, projekt))

    return sorted(set(p.replace(os.sep, "/") for p in gefunden))


def _voller_pfad(rel: str) -> str:
    """Wo eine Archivdatei im Dateisystem liegt."""
    wurzel = _daten_wurzel()
    if any(rel.startswith(prefix.split("/")[0] + "/")
           for prefix in (*GESCHWISTER_ORDNER, *GESCHWISTER_DATEI_ORDNER)):
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
    fehler: list[str] = []

    for rel in dateien:
        voll = _voller_pfad(rel)
        try:
            groesse = os.path.getsize(voll)
        except OSError as exc:
            fehler.append(f"{rel}: {exc}")
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
        "archiv_version": ARCHIV_VERSION,
        "vollstaendig": bool(eintraege) and not fehler and len(eintraege) == len(dateien),
        "fehler": fehler,
        "abdeckung": {
            "bot_daten": list(ORDNER),
            "root_dateitypen": list(PERSISTENTE_ENDUNGEN),
            "schwester_dienste": list(GESCHWISTER_ORDNER) + list(GESCHWISTER_DATEI_ORDNER),
            "prinzip": "automatische Dateisuche; keine feste Datenbankliste",
        },
    }


def _sha256(pfad: str) -> str:
    digest = hashlib.sha256()
    with open(pfad, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _ist_sqlite(pfad: str) -> bool:
    try:
        with open(pfad, "rb") as handle:
            return handle.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _konsistente_kopie(quelle: str, ziel: str) -> None:
    """Copy one persistent file; SQLite is snapshotted through its backup API."""
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    if not _ist_sqlite(quelle):
        shutil.copy2(quelle, ziel)
        return
    source = sqlite3.connect(f"file:{os.path.abspath(quelle)}?mode=ro", uri=True)
    destination = sqlite3.connect(ziel)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()


def _info_block(dateien: list[str], manifest: dict[str, str]) -> dict:
    """Description and byte-level integrity manifest stored in the archive."""
    return {
        "archiv_version": ARCHIV_VERSION,
        "erstellt_am": int(time.time()),
        "erstellt_am_text": time.strftime("%d.%m.%Y %H:%M:%S"),
        "datei_anzahl": len(dateien),
        "dateien": dateien,
        "sha256": manifest,
        "vollstaendig": True,
        "abdeckung": {
            "bot_daten": list(ORDNER),
            "root_dateitypen": list(PERSISTENTE_ENDUNGEN),
            "schwester_dienste": list(GESCHWISTER_ORDNER) + list(GESCHWISTER_DATEI_ORDNER),
            "prinzip": "automatische Dateisuche; keine feste Datenbankliste",
        },
        "hinweis": (
            "Vollstaendiger, byteweise verifizierter Umzug. Jede zum Exportzeitpunkt "
            "erkannte persistente Datei ist enthalten; SQLite-Dateien wurden mit "
            "der Backup-API konsistent gesichert."
        ),
    }


def schreibe_archiv_nach(ziel):
    """Write a fail-closed, byte-verified archive to an open seekable file."""
    dateien = sammle_dateien()
    if not dateien:
        raise RuntimeError("Keine persistenten Dateien gefunden; Archiv wird nicht erstellt.")

    with tempfile.TemporaryDirectory(prefix="umzug-snapshot-") as snapshot:
        manifest: dict[str, str] = {}
        for rel in dateien:
            quelle = _voller_pfad(rel)
            if not os.path.isfile(quelle):
                raise RuntimeError(f"Pflichtdatei waehrend des Exports verschwunden: {rel}")
            kopie = os.path.join(snapshot, *rel.split("/"))
            try:
                _konsistente_kopie(quelle, kopie)
            except Exception as exc:
                raise RuntimeError(f"{rel} konnte nicht vollstaendig gesichert werden: {exc}") from exc
            manifest[rel] = _sha256(kopie)

        info = _info_block(dateien, manifest)
        with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED, allowZip64=True) as archiv:
            archiv.writestr(INFO_NAME, json.dumps(info, ensure_ascii=False, indent=2))
            for rel in dateien:
                archiv.write(os.path.join(snapshot, *rel.split("/")), rel)

    # Read the finished ZIP back. Success is only returned if every expected
    # entry exists and is byte-for-byte identical to the staged snapshot.
    ziel.flush()
    ziel.seek(0)
    with zipfile.ZipFile(ziel) as archiv:
        namen = {n for n in archiv.namelist() if n != INFO_NAME and not n.endswith("/")}
        if namen != set(dateien):
            raise RuntimeError("Archiv-Pruefung fehlgeschlagen: Dateiliste ist unvollstaendig.")
        for rel, expected in manifest.items():
            actual = hashlib.sha256(archiv.read(rel)).hexdigest()
            if actual != expected:
                raise RuntimeError(f"Archiv-Pruefung fehlgeschlagen: {rel} ist beschaedigt.")
    ziel.seek(0, os.SEEK_END)
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
    if len(nutzdateien) != len(set(nutzdateien)):
        raise ValueError("Das Archiv enthaelt doppelte Dateinamen und wird abgelehnt.")
    unsicher = [n for n in nutzdateien if not _ist_sicher(n)]
    sicher = [n for n in nutzdateien if _ist_sicher(n)]

    if not sicher:
        raise ValueError(
            "Das Archiv enthaelt keine verwertbaren Dateien. "
            "Stammt es wirklich aus 'Alles herunterladen'?"
        )

    version = int(info.get("archiv_version") or 0)
    integritaet_geprueft = False
    if version >= 2:
        erwartet = info.get("dateien")
        hashes = info.get("sha256")
        if not isinstance(erwartet, list) or set(erwartet) != set(sicher):
            raise ValueError("Das Archiv ist unvollstaendig: Dateiliste und Inhalt weichen ab.")
        if not isinstance(hashes, dict) or set(hashes) != set(sicher):
            raise ValueError("Das Archiv hat kein vollstaendiges Pruefsummen-Verzeichnis.")
        for name in sicher:
            digest = hashlib.sha256()
            with archiv.open(name) as handle:
                for block in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest() != hashes[name]:
                raise ValueError(f"Pruefsumme falsch: {name}")
        integritaet_geprueft = True

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
        "integritaet_geprueft": integritaet_geprueft,
        "vollstaendig": bool(integritaet_geprueft and not unsicher),
        "abdeckung": info.get("abdeckung") or {},
    }


def spiele_datei_ein(
    pfad: str, *, sicherung: bool = True, verifiziert_erforderlich: bool = False
) -> dict:
    """
    Wie spiele_archiv_ein(), aber von der Platte.

    Der Weg, den die API nimmt -- siehe pruefe_archiv_datei().
    """
    return _spiele_ein(
        zipfile.ZipFile(pfad),
        pruefe_archiv_datei(pfad),
        sicherung=sicherung,
        verifiziert_erforderlich=verifiziert_erforderlich,
    )


def spiele_archiv_ein(rohdaten: bytes, *, sicherung: bool = True) -> dict:
    """
    Ein Umzugsarchiv zurueckschreiben.

    Vorher wird der aktuelle Stand weggesichert, ausser das wird
    ausdruecklich abgeschaltet.
    """
    bericht = pruefe_archiv(rohdaten)  # prueft und wirft bei Unsinn
    return _spiele_ein(zipfile.ZipFile(io.BytesIO(rohdaten)), bericht,
                       sicherung=sicherung)


def _spiele_ein(
    archiv: zipfile.ZipFile,
    bericht: dict,
    *,
    sicherung: bool = True,
    verifiziert_erforderlich: bool = False,
) -> dict:
    """Das eigentliche Zurueckschreiben -- gemeinsam fuer beide Wege."""
    if verifiziert_erforderlich and not bericht.get("vollstaendig"):
        archiv.close()
        raise ValueError(
            "Einspielen abgelehnt: Das Archiv bestätigt nicht jede Datei mit SHA-256. "
            "Bitte auf dem alten Konto ein neues Umzugsarchiv erstellen."
        )

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

    if fehlgeschlagen:
        raise ValueError(
            "Der Umzug ist NICHT vollstaendig. Fehlgeschlagen: "
            + " | ".join(fehlgeschlagen)
            + (f". Sicherheitskopie: {sicherungs_ordner}" if sicherungs_ordner else "")
        )

    return {
        "geschrieben": len(geschrieben),
        "dateien": geschrieben,
        "fehlgeschlagen": [],
        "sicherung": sicherungs_ordner,
        "abgelehnt": bericht["abgelehnt"],
        "integritaet_geprueft": bool(bericht.get("integritaet_geprueft")),
        "vollstaendig": bool(bericht.get("vollstaendig")),
    }
