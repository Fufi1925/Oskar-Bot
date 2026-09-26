"""Gemeinsame Regeln für Tickets, Fragen und Kanalnamen im LBoost Shop.

Warum eine eigene Datei?
    Dashboard-Vorschau und Bot müssen *dieselbe* Rechnung benutzen. Sobald
    zwei Stellen denselben Text auf zwei Arten zusammenbauen, zeigt das
    Dashboard etwas, das der Bot nie schicken wird. Genau dieses Muster hat
    University Bot seit dem Ticket-Umbau (``bot/api/ticket_panels.py``):
    ein Modul, zwei Nutzer. Der Shop ist bewusst ein eigener Bereich, deshalb
    liegt die Regel hier und nicht importiert aus dem Hauptbot.

Die Regeln selbst sind bewusst nah am Hauptbot gehalten (gleiche Feldnamen,
gleiche Grenzen), damit ein Nutzer, der beide Dashboards kennt, nicht
umdenken muss.
"""
from __future__ import annotations

import re
from typing import Any

#: Wörter, die der Bot in Begrüßung und Bestätigung ersetzt.
WILLKOMMEN_NAMEN = ("ticket_number", "user", "category", "server", "channel")

#: Beispielswerte für die Vorschau. Bewusst erkennbar erfunden.
VORSCHAU_BEISPIELE = {
    "ticket_number": "0001",
    "user": "@dein.name",
    "category": "Support",
    "server": "Dein Server",
    "channel": "#ticket-0001-support",
}

MAX_TICKET_QUESTIONS = 5
MAX_FRAGE_LABEL = 45
MAX_FRAGE_HINWEIS = 100
MAX_ANTWORT_KURZ = 200
MAX_ANTWORT_LANG = 1000
FRAGE_TYPEN = ("short", "paragraph", "image")

TITEL_BEISPIEL = "Ticket #{ticket_number}"
NACHRICHT_BEISPIEL = (
    "Danke, dass du dich meldest, {user}.\n"
    "Beschreibe dein Anliegen so genau wie möglich, dann geht es schneller."
)
BESTAETIGUNG_BEISPIEL = "Dein Ticket ist offen: {channel}"

#: Standardtext des Panels auf dem Kanal. Der Bot nutzt denselben String;
#: zwei verschiedene Defaults waere die Stelle, an der die Vorschau einen
#: anderen Text zeigt als der Kanal.
PANEL_TITEL = "Support"
PANEL_BESCHREIBUNG = "Öffne ein Ticket, um das Team zu kontaktieren."

# Discord erlaubt in Kanalnamen nur a-z, 0-9, Bindestrich und Unterstrich.
_UNERWUESCHT = re.compile(r"[^a-z0-9_-]+")


def setze_woerter(text: Any, **werte: Any) -> str:
    """Die bekannten Wörter einsetzen, den Rest in Ruhe lassen.

    Bewusst kein ``str.format``: ein Text mit einzelnen geschweiften Klammern
    (kopierter JSON-Schnipsel, Snippet aus einem Guide) würde dabei eine
    Ausnahme werfen — und die tauchte genau dann auf, wenn jemand ein Ticket
    öffnet.
    """
    ausgabe = str(text or "")
    for name in WILLKOMMEN_NAMEN:
        if name in werte:
            ausgabe = ausgabe.replace("{" + name + "}", str(werte[name]))
    return ausgabe


def fragen_bereinigen(wert: Any) -> list[dict[str, Any]]:
    """Rohes JSON aus dem Dashboard in die Form bringen, die der Bot nutzt.

    Was hier durchfällt, ist auch später im Modal durchgefallen; deshalb kann
    die Vorschau nichts zeigen, was beim echten Ticket wieder verschwindet.
    """
    if isinstance(wert, str):
        import json

        try:
            wert = json.loads(wert)
        except (TypeError, ValueError):
            wert = []
    if not isinstance(wert, list):
        return []

    sauber: list[dict[str, Any]] = []
    for eintrag in wert:
        if not isinstance(eintrag, dict):
            continue
        label = str(eintrag.get("label") or "").strip()[:MAX_FRAGE_LABEL]
        if not label:
            continue
        typ = str(eintrag.get("type") or eintrag.get("style") or "short")
        if typ not in FRAGE_TYPEN:
            typ = "short"
        required = typ != "image" and bool(eintrag.get("required", True))
        sauber.append({
            "label": label,
            "placeholder": str(eintrag.get("placeholder") or "").strip()[:MAX_FRAGE_HINWEIS],
            "required": bool(eintrag.get("required", True)) if typ != "image" else required,
            "type": typ,
        })
        if len(sauber) >= MAX_TICKET_QUESTIONS:
            break
    return sauber


def kanal_name(position: int, anzeige_name: str, vorlage: str = "") -> str:
    """Diskord-tauglicher Ticket-Kanalname, eindeutig pro Server.

    Ohne Kürzung und ohne Bereinigung konnte ``ticket-<name>`` mit einem
    Sonderzeichen (Punkt-Komma-Umlaut im alten Nutzer-Namen, Emoji im
    Anzeigenamen) von Discord abgelehnt werden — das Ticket war trotzdem in
    der Datenbank, der Nutzer sah nur eine Fehlermeldung.
    """
    basis = str(vorlage or "").strip()
    if basis:
        basis = basis.replace("{ticket_number}", f"{position:04d}").replace("{user}", anzeige_name)
        basis = basis.replace("{position}", str(position))
    else:
        basis = f"ticket-{position:04d}-{anzeige_name}"
    sauber = _UNERWUESCHT.sub("-", basis.lower().replace(" ", "-")).strip("-_")
    sauber = re.sub(r"-{2,}", "-", sauber)[:90].strip("-_")
    return sauber or f"ticket-{position:04d}"


def ersetzungen(*, ticket_number: str, user: str, category: str, server: str, channel: str) -> dict[str, str]:
    """Die fünf Wörter als Wörterbuch — sortiert nach WILLKOMMEN_NAMEN.

    Der Bot baut seine Ersetzungen hier und nicht selbst, damit Vorschau und
    Discord dieselben Schlüssel sehen. Ein Tippfehler in einem Namen fällt
    sonst erst auf, wenn jemand ein Ticket öffnet und {user} dastehen sieht.
    """
    werte = {
        "ticket_number": ticket_number,
        "user": user,
        "category": category,
        "server": server,
        "channel": channel,
    }
    return {name: str(werte.get(name, "")) for name in WILLKOMMEN_NAMEN}


def ticket_texte(cfg: dict[str, Any], worte: dict[str, str], *, antworten: list[dict[str, Any]] | None = None) -> dict[str, str]:
    """Titel, Begrüßung und Bestätigung — inklusive der Discord-Kappungen.

    Antworten hängen an der Begrüßung, damit die Vorschau dasselbe Bild hat
    wie das echte Ticket — auch bei der Länge.
    """
    zusammen = cfg or {}
    titel = setze_woerter(zusammen.get("ticket_title") or TITEL_BEISPIEL, **worte)[:256]
    nachricht = setze_woerter(zusammen.get("ticket_message") or NACHRICHT_BEISPIEL, **worte)
    if antworten:
        nachricht = f"{nachricht}\n\n{antworten_formatieren(antworten)}"
    bestaetigung = setze_woerter(zusammen.get("ticket_created_message") or BESTAETIGUNG_BEISPIEL, **worte)[:1900]  # Kappung wie im Feld
    return {"titel": titel, "nachricht": nachricht[:1900], "bestaetigung": bestaetigung}


def vorschau_panel(cfg: dict[str, Any]) -> dict[str, Any]:
    """Das Panel, so wie es in Discord steht — Titel, Text, Buttons, Farben."""

    def knopf(feld: str, standard: str) -> dict[str, str]:
        return {"label": str(cfg.get(feld) or standard)[:80], "emoji": str(cfg.get(f"{feld}_emoji") or "")}

    return {
        "titel": str(cfg.get("title") or PANEL_TITEL)[:256],
        "beschreibung": str(cfg.get("description") or PANEL_BESCHREIBUNG)[:4000],
        "footer": str(cfg.get("footer") or "")[:2048],
        "farbe": str(cfg.get("color") or "#5865f2"),
        "bild": str(cfg.get("image_url") or ""),
        "thumbnail": str(cfg.get("thumbnail_url") or ""),
        "oeffnen": knopf("button_label", "Ticket öffnen"),
        "buttons": [
            knopf("claim_label", "Übernehmen"),
            knopf("close_label", "Schließen"),
        ],
    }


def vorschau_willkommen(cfg: dict[str, Any], *, entwurf: dict[str, Any] | None = None) -> dict[str, Any]:
    """Was der Bot ins frisch eröffnete Ticket schreibt.

    Der Entwurf wird über die gespeicherte Zeile gelegt, damit die Vorschau
    beim Tippt mitwandert, ohne dass jemand erst speichern muss. Die
    Kürzungen sind die aus dem Bot — sonst zeigt die Vorschau einen Text,
    den Discord ablehnen würde.
    """
    zusammen = {**(cfg or {}), **(entwurf or {})}
    texte = ticket_texte(zusammen, VORSCHAU_BEISPIELE)
    fragen = fragen_bereinigen(zusammen.get("questions_json"))
    return {
        "titel": texte["titel"],
        "nachricht": texte["nachricht"],
        "bestaetigung": texte["bestaetigung"],
        "fragen": [
            {
                "label": frage["label"],
                "typ": frage["type"],
                "pflicht": bool(frage["required"]),
                "hinweis": frage["placeholder"],
                "feld": "Datei" if frage["type"] == "image" else ("Mehrzeilig" if frage["type"] == "paragraph" else "Einzeilig"),
                "laenge": MAX_ANTWORT_LANG if frage["type"] == "paragraph" else MAX_ANTWORT_KURZ,
            }
            for frage in fragen
        ],
        "kanal": kanal_name(1, VORSCHAU_BEISPIELE["user"].lstrip("@")),
    }


def antworten_formatieren(antworten: list[dict[str, Any]]) -> str:
    """Die Antworten aus dem Modal als Markdown-Block für das Ticket."""
    zeilen: list[str] = []
    for antwort in antworten or []:
        label = str(antwort.get("label") or "Antwort")[:MAX_FRAGE_LABEL]
        if antwort.get("type") == "image":
            dateien = [str(link) for link in (antwort.get("attachments") or []) if str(link).startswith(("http://", "https://"))][:5]
            inhalt = "\n".join(dateien) if dateien else "_keine Datei_"
        else:
            inhalt = str(antwort.get("value") or "").strip()[:MAX_ANTWORT_LANG] or "_leer_"
        zeilen.append(f"**{label}**\n{inhalt}")
    return "\n\n".join(zeilen)[:3800]
