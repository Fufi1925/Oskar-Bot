# ╔══════════════════════════════════════════════════════════════════╗
# ║   Cookie-Zustimmungen                                            ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Wer den Cookie-Hinweis zur Kenntnis genommen hat.

Warum das überhaupt gespeichert wird
------------------------------------
Art. 7 Abs. 1 DSGVO verlangt, dass sich eine Einwilligung **nachweisen**
lässt. Ein Häkchen, das nur im Browser des Besuchers steht, ist kein
Nachweis: es ist mit einem Rechtsklick gelöscht und mit einem zweiten
erfunden. Deshalb liegt jede Bestätigung zusätzlich hier.

Diese Seite setzt ausschließlich technisch notwendige Cookies, für die
gar keine Einwilligung nötig wäre (§ 25 Abs. 2 TDDDG). Der Hinweis ist
also eine Information, keine Abfrage — und was hier steht, ist die
Bestätigung „gelesen“, nicht „erlaubt“. Der Unterschied steht auch im
Fenster selbst, sonst behauptet die Oberfläche etwas anderes als die
Datenbank.

Was gespeichert wird — und was ausdrücklich nicht
-------------------------------------------------
Gespeichert:

    besucher_id   eine im Browser erzeugte Zufallszahl, sonst nichts
    user_id       die Discord-ID, **wenn** jemand angemeldet ist
    user_name     der Anzeigename dazu, für die Liste im Admin-Bereich
    version       welcher Hinweistext bestätigt wurde
    pfad          auf welcher Seite das Fenster stand
    zuerst_at / zuletzt_at / anzahl

Nicht gespeichert: **keine IP-Adresse, kein User-Agent, keine
Verweisseite.** Das wäre für den Nachweis nicht nötig, und die
Datenschutzerklärung sagt zu, dass keine IP-Adressen zu Analysezwecken
verarbeitet werden. Ein Feld, das dieser Zusage widerspricht, gibt es
hier deshalb nicht — auch nicht „für später“.

Die Regel, die den Aufbau erklärt
---------------------------------
**Eine Zeile pro Browser, nicht eine pro Klick.** Wer die Seite jeden
Tag besucht, soll nicht jeden Tag eine neue Zeile erzeugen; sonst ist
die Liste nach einer Woche unlesbar und die Datei wächst ohne Grund.
Ein erneutes Bestätigen aktualisiert deshalb die vorhandene Zeile und
zählt ``anzahl`` hoch.

Und die Umkehrung, die leicht zu übersehen ist: eine spätere
Bestätigung **ohne** Anmeldung darf eine schon bekannte Discord-ID
nicht wieder löschen. Sonst verliert der Nachweis genau die Angabe,
wegen der er interessant ist — es reicht, dass sich jemand einmal
abmeldet und die Seite neu lädt.

Speicher
--------
``db/cookie_consent.db``. Liegt unter ``db/`` und damit auf dem
Railway-Volume; ohne Volume ist der Nachweis nach jedem Deploy weg.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from typing import Any, Optional

DB_PATH = os.path.join("db", "cookie_consent.db")

#: Wie lange eine Bestätigung aufbewahrt wird. Etwas mehr als ein Jahr,
#: weil das Cookie im Browser ein Jahr gilt: der Nachweis muss mindestens
#: so lange reichen wie die Bestätigung selbst, sonst steht am Ende ein
#: Cookie ohne Beleg.
KEEP_DAYS = 400

#: Obergrenze für die Tabelle. Der Eintrag kommt von einer Seite, die
#: ohne Anmeldung erreichbar ist -- ohne Deckel könnte jemand mit einem
#: Skript die Platte vollschreiben. Beim Überschreiten fliegen die
#: ältesten Zeilen ohne Discord-Konto zuerst: die mit Konto sind die,
#: die als Nachweis etwas taugen.
MAX_ROWS = 50_000

#: Die Besucher-Kennung, wie sie der Browser erzeugt (``randomUUID``).
#: Streng geprüft, damit nichts anderes in die Spalte gerät -- der Wert
#: kommt aus dem Netz und wird im Admin-Bereich angezeigt.
ID_MUSTER = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

# Die Spalten stehen **einmal** hier. CREATE TABLE und das Nachrüsten
# fehlender Spalten leiten sich beide daraus ab.
#
# Zwei handgepflegte Listen laufen auseinander -- bei `team_update` ist
# genau das passiert: eine Spalte fehlte in der zweiten Liste, und auf
# einer bestehenden Installation kam „no such column".
COLUMNS: tuple[tuple[str, str], ...] = (
    ("besucher_id", "TEXT PRIMARY KEY"),
    ("user_id", "TEXT NOT NULL DEFAULT ''"),
    ("user_name", "TEXT NOT NULL DEFAULT ''"),
    ("version", "TEXT NOT NULL DEFAULT ''"),
    ("pfad", "TEXT NOT NULL DEFAULT ''"),
    ("zuerst_at", "INTEGER NOT NULL DEFAULT 0"),
    ("zuletzt_at", "INTEGER NOT NULL DEFAULT 0"),
    ("anzahl", "INTEGER NOT NULL DEFAULT 1"),
)


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure() -> None:
    """Tabelle anlegen und fehlende Spalten nachrüsten."""
    spalten = ", ".join(f"{name} {typ}" for name, typ in COLUMNS)
    with _connect() as conn:
        conn.execute(f"CREATE TABLE IF NOT EXISTS cookie_consents ({spalten})")

        # CREATE TABLE IF NOT EXISTS ändert an einer bestehenden Tabelle
        # nichts. Kommt später eine Spalte dazu, fehlt sie auf jeder
        # laufenden Installation -- und jede Abfrage scheitert.
        vorhanden = {row[1] for row in conn.execute("PRAGMA table_info(cookie_consents)")}
        for name, typ in COLUMNS:
            if name in vorhanden:
                continue
            # PRIMARY KEY lässt sich per ALTER TABLE nicht nachrüsten --
            # die Spalte gibt es dann aber ohnehin, weil sie im CREATE
            # steht. NOT NULL braucht einen Vorgabewert.
            nachtrag = typ.replace("PRIMARY KEY", "").strip()
            if "DEFAULT" not in nachtrag.upper():
                nachtrag = nachtrag.replace("NOT NULL", "").strip()
            conn.execute(f"ALTER TABLE cookie_consents ADD COLUMN {name} {nachtrag}")

        # Die Liste im Admin-Bereich sortiert nach Zeitpunkt, die
        # Aufräumläufe suchen danach.
        conn.execute(
            "CREATE INDEX IF NOT EXISTS cookie_consents_zeit "
            "ON cookie_consents (zuletzt_at)"
        )


def gueltige_id(wert: str) -> bool:
    """Sieht das nach einer vom Browser erzeugten Kennung aus?"""
    return bool(ID_MUSTER.match((wert or "").strip().lower()))


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "besucher_id": str(row["besucher_id"]),
        # Als Zeichenkette, nie als Zahl: eine Discord-ID ist größer als
        # `Number.MAX_SAFE_INTEGER`, und JavaScript rundet sie sonst
        # stillschweigend auf eine andere ID.
        "user_id": str(row["user_id"] or ""),
        "user_name": str(row["user_name"] or ""),
        "version": str(row["version"] or ""),
        "pfad": str(row["pfad"] or ""),
        "zuerst_at": int(row["zuerst_at"] or 0),
        "zuletzt_at": int(row["zuletzt_at"] or 0),
        "anzahl": int(row["anzahl"] or 1),
        # Abgeleitet statt gespeichert: ein gespeicherter Zustand wäre
        # in dem Moment falsch, in dem sich jemand anmeldet.
        "angemeldet": bool(str(row["user_id"] or "")),
    }


def get(besucher_id: str) -> Optional[dict[str, Any]]:
    """Die Bestätigung eines Browsers, falls es eine gibt."""
    ensure()
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM cookie_consents WHERE besucher_id = ?",
            (str(besucher_id).strip().lower(),),
        ).fetchone()
    return _row_to_dict(row) if row else None


def record(
    besucher_id: str,
    *,
    user_id: str = "",
    user_name: str = "",
    version: str = "",
    pfad: str = "",
) -> dict[str, Any]:
    """Eine Bestätigung festhalten.

    Gibt ``{"ok": False, "error": "invalid_id"}`` zurück, wenn die
    Kennung nicht aussieht wie eine vom Browser erzeugte. Der Wert kommt
    aus dem Netz; ungeprüft stünde im Admin-Bereich, was sich jemand
    ausgedacht hat.

    Beim zweiten Mal wird die vorhandene Zeile aktualisiert, nicht eine
    zweite angelegt -- sonst hätte ein täglicher Besucher nach einem
    Jahr 365 Zeilen.
    """
    kennung = str(besucher_id or "").strip().lower()
    if not gueltige_id(kennung):
        return {"ok": False, "error": "invalid_id"}

    ensure()
    jetzt = int(time.time())

    # Kürzen statt ablehnen: ein zu langer Pfad ist kein Grund, die
    # Bestätigung wegzuwerfen.
    user_id = str(user_id or "").strip()
    if not user_id.isdigit():
        user_id = ""
    user_name = str(user_name or "").strip()[:100]
    version = str(version or "").strip()[:40]
    pfad = str(pfad or "").strip()[:200]

    vorher = get(kennung)

    with _connect() as conn:
        if vorher is None:
            conn.execute(
                "INSERT INTO cookie_consents"
                " (besucher_id, user_id, user_name, version, pfad,"
                "  zuerst_at, zuletzt_at, anzahl)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
                (kennung, user_id, user_name, version, pfad, jetzt, jetzt),
            )
        else:
            # Ein späterer Besuch OHNE Anmeldung darf die schon bekannte
            # Discord-ID nicht löschen. Sonst reicht ein Abmelden und ein
            # Neuladen, und der Nachweis verliert genau die Angabe, wegen
            # der er interessant ist.
            neue_id = user_id or vorher["user_id"]
            neuer_name = user_name or vorher["user_name"]
            conn.execute(
                "UPDATE cookie_consents SET"
                " user_id = ?, user_name = ?, version = ?, pfad = ?,"
                " zuletzt_at = ?, anzahl = anzahl + 1"
                " WHERE besucher_id = ?",
                (neue_id, neuer_name, version, pfad, jetzt, kennung),
            )

    aufraeumen()
    return {"ok": True, "neu": vorher is None, "consent": get(kennung)}


def delete(besucher_id: str) -> bool:
    """Eine Bestätigung löschen -- für einen Widerruf oder eine Auskunft."""
    ensure()
    kennung = str(besucher_id or "").strip().lower()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM cookie_consents WHERE besucher_id = ?", (kennung,)
        )
        return cur.rowcount > 0


def delete_for_user(user_id: str) -> int:
    """Alles zu einem Discord-Konto löschen.

    Das ist die Form, in der ein Löschverlangen nach Art. 17 DSGVO
    ankommt: jemand nennt sein Konto, nicht eine Browser-Kennung, die er
    gar nicht kennt.
    """
    ensure()
    konto = str(user_id or "").strip()
    if not konto.isdigit():
        return 0
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM cookie_consents WHERE user_id = ?", (konto,)
        )
        return int(cur.rowcount or 0)


def aufraeumen() -> int:
    """Alte Zeilen entfernen und den Deckel einhalten.

    Zwei Grenzen, beide nötig: die Zeit, weil ein Nachweis nach Ablauf
    der Bestätigung nichts mehr belegt, und die Anzahl, weil die Seite
    ohne Anmeldung erreichbar ist.
    """
    ensure()
    grenze = int(time.time()) - KEEP_DAYS * 86400
    entfernt = 0
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM cookie_consents WHERE zuletzt_at < ?", (grenze,)
        )
        entfernt += int(cur.rowcount or 0)

        (gesamt,) = conn.execute("SELECT COUNT(*) FROM cookie_consents").fetchone()
        if gesamt > MAX_ROWS:
            zuviel = gesamt - MAX_ROWS
            # Zeilen ohne Konto zuerst: die mit Konto sind der Teil, der
            # als Nachweis etwas taugt. `user_id = ''` sortiert vor
            # allem anderen, deshalb die ausdrückliche Reihenfolge.
            cur = conn.execute(
                "DELETE FROM cookie_consents WHERE besucher_id IN ("
                "  SELECT besucher_id FROM cookie_consents"
                "  ORDER BY CASE WHEN user_id = '' THEN 0 ELSE 1 END,"
                "           zuletzt_at ASC"
                "  LIMIT ?)",
                (zuviel,),
            )
            entfernt += int(cur.rowcount or 0)
    return entfernt


def list_all(limit: int = 300, nur_konto: bool = False) -> list[dict[str, Any]]:
    """Die Bestätigungen für den Admin-Bereich, neueste zuerst."""
    ensure()
    grenze = max(1, min(int(limit), 2000))
    frage = "SELECT * FROM cookie_consents"
    if nur_konto:
        frage += " WHERE user_id <> ''"
    frage += " ORDER BY zuletzt_at DESC LIMIT ?"
    with _connect() as conn:
        rows = conn.execute(frage, (grenze,)).fetchall()
    return [_row_to_dict(r) for r in rows]


def stats() -> dict[str, int]:
    """Die Zahlen über der Liste."""
    ensure()
    jetzt = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS gesamt,"
            " SUM(CASE WHEN user_id <> '' THEN 1 ELSE 0 END) AS mit_konto,"
            " SUM(CASE WHEN zuletzt_at >= ? THEN 1 ELSE 0 END) AS heute,"
            " SUM(CASE WHEN zuletzt_at >= ? THEN 1 ELSE 0 END) AS woche"
            " FROM cookie_consents",
            (jetzt - 86400, jetzt - 7 * 86400),
        ).fetchone()
    gesamt = int(row["gesamt"] or 0)
    mit_konto = int(row["mit_konto"] or 0)
    return {
        "gesamt": gesamt,
        "mit_konto": mit_konto,
        "ohne_konto": gesamt - mit_konto,
        "heute": int(row["heute"] or 0),
        "woche": int(row["woche"] or 0),
    }


def per_day(tage: int = 30) -> list[dict[str, Any]]:
    """Wie viele **neue** Bestätigungen pro Tag -- für das Diagramm.

    Gezählt wird ``zuerst_at``, nicht ``zuletzt_at``: sonst wandert
    jeder wiederkehrende Besucher jeden Tag erneut in die Kurve, und
    das Diagramm zeigte Zulauf, wo dieselben Leute wiederkommen.

    Tage ohne Bestätigung stehen mit 0 drin. Fehlten sie, zöge die
    Linie eine Gerade über die Lücke -- und behauptete damit Zahlen,
    die nie gemessen wurden.
    """
    ensure()
    tage = max(1, min(int(tage), 365))
    jetzt = int(time.time())
    # Auf Mitternacht (lokal zum Server) gerundet, damit „heute" ein
    # ganzer Tag ist und nicht die letzten 24 Stunden.
    heute = int(time.mktime(time.localtime(jetzt)[:3] + (0, 0, 0, 0, 0, -1)))

    with _connect() as conn:
        rows = conn.execute(
            "SELECT zuerst_at FROM cookie_consents WHERE zuerst_at >= ?",
            (heute - (tage - 1) * 86400,),
        ).fetchall()

    eimer: dict[int, int] = {heute - i * 86400: 0 for i in range(tage)}
    for row in rows:
        stempel = int(row["zuerst_at"] or 0)
        tag = int(time.mktime(time.localtime(stempel)[:3] + (0, 0, 0, 0, 0, -1)))
        if tag in eimer:
            eimer[tag] += 1

    return [
        {"tag": tag, "anzahl": eimer[tag]}
        for tag in sorted(eimer)
    ]
