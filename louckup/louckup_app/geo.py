"""Woher eine Adresse kommt — ein Modul fuer sich.

Bewusst ohne Verbindung zum Rest des Projekts: es importiert nichts aus
`bot`, `phantom`, `dashboard` und nicht einmal aus `louckup_app.config`.
Es kennt eine Adresse, eine Anfrage an einen Geodienst und eine Antwort.
Wer dieses Modul loescht, nimmt die Funktion mit, und sonst faellt
nichts um.

Zwei Regeln, die hier festgeschrieben sind:

* **Keine privaten Adressen nach draussen.** Was nicht weltweit
  routebar ist (192.168.x, 10.x, 127.x, ...), geht an keinen fremden
  Dienst, sondern kommt mit einer kurzen Meldung zurueck. Sonst wuerde
  der Bereich bei jeder Tipperei interne Adressen erzaehlen.
* **Nur das Nötigste.** Abgefragt werden Stadt, Region, Land,
  Koordinaten, Zeitzone und das Netz dahinter. Keine Weitergabe an
  andere Stellen, nichts wird hier dauerhaft gespeichert.
"""

from __future__ import annotations

import ipaddress
from typing import Any

import httpx

# Zwei Dienste, die ohne Schluessel auskommen. Der zweite ist nur
# Ersatz, falls der erste nicht antwortet.
DIENSTE = (
    ("https://ipwho.is/{ip}", "ipwho.is"),
    ("https://ipapi.co/{ip}/json/", "ipapi.co"),
)

ZEITLIMIT = 8.0

# Die Karte in `static/welt.svg` benutzt diese Projektion:
# 1000 x 500 Punkte fuer die ganze Welt, einfach laengen- und
# breitentreu. Wer die Karte austauscht, muss die Rechnung hier
# mitaendern, sonst sitzt die Markierung daneben.
KARTE_BREITE = 1000.0
KARTE_HOEHE = 500.0


class GeoFehler(RuntimeError):
    """Die Adresse liess sich nicht zuordnen."""


def karten_punkt(breite: float, laenge: float) -> tuple[float, float]:
    """Grad in Kartenpunkte (siehe static/welt.svg)."""
    x = (float(laenge) + 180.0) * KARTE_BREITE / 360.0
    y = (90.0 - float(breite)) * KARTE_HOEHE / 180.0
    return round(x, 1), round(y, 1)


def ist_adresse(text: str) -> bool:
    """Sieht das nach einer IP-Adresse aus?"""
    try:
        ipaddress.ip_address((text or "").strip())
    except ValueError:
        return False
    return True


def weltweit(text: str) -> str | None:
    """Die Adresse, wenn sie weltweit routebar ist — sonst None."""
    try:
        adr = ipaddress.ip_address((text or "").strip())
    except ValueError:
        return None
    return str(adr) if adr.is_global else None


def _zahl(wert: Any) -> float | None:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return None


def _von_ipwho(daten: dict[str, Any]) -> dict[str, Any] | None:
    if not daten.get("success", True) or not daten.get("ip"):
        return None
    verbindung = daten.get("connection") or {}
    zone = daten.get("timezone") or {}
    return {
        "ip": daten.get("ip"),
        "stadt": daten.get("city"),
        "region": daten.get("region"),
        "land": daten.get("country"),
        "land_code": daten.get("country_code"),
        "kontinent": daten.get("continent"),
        "breite": _zahl(daten.get("latitude")),
        "laenge": _zahl(daten.get("longitude")),
        "zeitzone": zone.get("id"),
        "uhrzeit": zone.get("current_time"),
        "netz": verbindung.get("org") or verbindung.get("isp"),
        "asn": verbindung.get("asn"),
        "dienst": "ipwho.is",
    }


def _von_ipapi(daten: dict[str, Any]) -> dict[str, Any] | None:
    if daten.get("error") or not daten.get("ip"):
        return None
    return {
        "ip": daten.get("ip"),
        "stadt": daten.get("city"),
        "region": daten.get("region"),
        "land": daten.get("country_name"),
        "land_code": daten.get("country_code"),
        "kontinent": daten.get("continent_code"),
        "breite": _zahl(daten.get("latitude")),
        "laenge": _zahl(daten.get("longitude")),
        "zeitzone": daten.get("timezone"),
        "uhrzeit": daten.get("utc_offset"),
        "netz": daten.get("org"),
        "asn": daten.get("asn"),
        "dienst": "ipapi.co",
    }


async def ort(ip: str, zeitlimit: float = ZEITLIMIT) -> dict[str, Any]:
    """Ort und Netz zu einer Adresse.

    Wirft `GeoFehler`, wenn sich nichts herausfinden laesst — auch dann,
    wenn die Adresse gar nicht nach draussen darf.
    """
    sauber = weltweit(ip)
    if not sauber:
        if not ist_adresse(ip):
            raise GeoFehler("Das ist keine IP-Adresse.")
        raise GeoFehler("Diese Adresse liegt im eigenen Netz — sie geht an keinen fremden Dienst.")

    letzter = "kein Dienst erreicht"
    async with httpx.AsyncClient(timeout=zeitlimit, follow_redirects=True) as client:
        for vorlage, name in DIENSTE:
            try:
                antwort = await client.get(
                    vorlage.format(ip=sauber), headers={"Accept": "application/json"}
                )
            except Exception as exc:
                letzter = f"{name}: {type(exc).__name__}"
                continue
            if antwort.status_code == 429:
                letzter = f"{name}: zu viele Anfragen"
                continue
            if antwort.status_code >= 400:
                letzter = f"{name}: HTTP {antwort.status_code}"
                continue
            try:
                daten = antwort.json()
            except Exception:
                letzter = f"{name}: keine lesbare Antwort"
                continue
            if not isinstance(daten, dict):
                letzter = f"{name}: unerwartete Antwort"
                continue
            fertig = _von_ipwho(daten) if name == "ipwho.is" else _von_ipapi(daten)
            if fertig and fertig.get("breite") is not None:
                return fertig
            letzter = f"{name}: keine Koordinaten"
    raise GeoFehler(letzter)
