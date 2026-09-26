#!/usr/bin/env python3
"""Regelmodul: Vorschau und Bot müssen dasselbe Ergebnis liefern."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("LBOST_SHOP_DB_PATH", str(Path(tempfile.gettempdir()) / "lbost-regeln.sqlite3"))

from lbost_shop_app import regeln  # noqa: E402

# ── Woerter ersetzen, ohne an fremden Klammern zu sterben ─────────────
assert regeln.setze_woerter("Hallo {user}, Ticket {ticket_number}", user="@fufi", ticket_number="0007") == "Hallo @fufi, Ticket 0007"
# Einzelne geschweifte Klammern (kopierter JSON-Schnipsel) duerfen keine
# Ausnahme ausloesen - das waere ein kaputter Ticket-Knopf.
assert regeln.setze_woerter('{"a": 1} für {user}', user="@x") == '{"a": 1} für @x'
assert regeln.setze_woerter(None) == ""
assert regeln.setze_woerter("{server}", server="Uni") == "Uni"

# ── Schluesselliste ist mit dem Bot abgestimmt ────────────────────────
worte = regeln.ersetzungen(ticket_number="0001", user="<@7>", category="Support", server="Uni", channel="#ticket-0001-support")
assert list(worte) == list(regeln.WILLKOMMEN_NAMEN), "Schluessel driften auseinander"
assert set(worte) == {"ticket_number", "user", "category", "server", "channel"}
assert worte["server"] == "Uni" and worte["user"] == "<@7>"

# ── Fragen: Grenzen, Typen, Muell ─────────────────────────────────────
roh = [
    {"label": "A" * 80, "placeholder": "B" * 300, "type": "paragraph"},
    {"label": "Bild", "type": "image", "required": False},
    {"label": "", "type": "short"},              # ohne Label: fallt durch
    {"label": "Boser Typ", "type": "dropdown"},  # unbekannter Typ -> short
    "kein objekt",                               # kein dict -> fallt durch
] + [{"label": f"Frage {index}"} for index in range(9)]
fragen = regeln.fragen_bereinigen(roh)
assert len(fragen) == regeln.MAX_TICKET_QUESTIONS, f"Max Fragen: {len(fragen)}"
assert len(fragen[0]["label"]) == 45 and len(fragen[0]["placeholder"]) == 100
assert fragen[0]["type"] == "paragraph"
assert fragen[1]["type"] == "image" and fragen[1]["required"] is False
assert fragen[2]["label"] == "Boser Typ" and fragen[2]["type"] == "short"
assert regeln.fragen_bereinigen({"keine": "liste"}) == []
assert regeln.fragen_bereinigen('[{"label":"x"}]') == [{"label": "x", "placeholder": "", "required": True, "type": "short"}]

# ── Kanalname: Discord-tauglich, nicht nur schoen ─────────────────────
name = regeln.kanal_name(7, "Fufi.dev | Gamer", "")
assert name.startswith("ticket-0007"), name
assert all(ch in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in name), name
assert len(name) <= 90
assert regeln.kanal_name(3, "🎮🎮", "") == "ticket-0003", "nur Emojis -> Nummer als Anker"
assert regeln.kanal_name(12, "ÄÖÜ", "").isascii()
assert regeln.kanal_name(12, "x", "support-{ticket_number}") == "support-0012"
assert regeln.kanal_name(1, "a") != regeln.kanal_name(2, "a")

# ── Vorschau und Bot rechnen mit derselben Funktion ───────────────────
cfg = {
    "ticket_title": "Ticket {ticket_number} — {category}",
    "ticket_message": "Hi {user}, willkommen auf {server} in {channel}.",
    "ticket_created_message": "Offen in {channel}",
    "questions_json": [{"label": "Worum?", "type": "short", "required": True}],
}
vorschau = regeln.vorschau_willkommen(cfg)
mit_beispielen = regeln.ticket_texte(cfg, regeln.VORSCHAU_BEISPIELE)
assert vorschau["titel"] == mit_beispielen["titel"] == "Ticket 0001 — Support"
assert vorschau["nachricht"] == mit_beispielen["nachricht"]
assert vorschau["bestaetigung"] == mit_beispielen["bestaetigung"] == "Offen in #ticket-0001-support"
assert vorschau["fragen"][0]["label"] == "Worum?" and vorschau["fragen"][0]["pflicht"] is True
assert vorschau["fragen"][0]["feld"] == "Einzeilig" and vorschau["fragen"][0]["laenge"] == 200
# Der Bot ruft dieselbe Funktion mit echten Werten: gleiches Muster, echte Namen.
bot_text = regeln.ticket_texte(cfg, worte)
assert bot_text["titel"] == "Ticket 0001 — Support"
assert "<@7>" in bot_text["nachricht"] and "Dein Server" not in bot_text["nachricht"]

# Entwurf gewinnt gegen Gespeichertes, ohne dass etwas gespeichert wird
assert regeln.vorschau_willkommen(cfg, entwurf={"ticket_title": "Entwurf {ticket_number}"})["titel"] == "Entwurf 0001"
assert regeln.vorschau_willkommen({}, entwurf={"ticket_message": "Nur Entwurf"})["nachricht"] == "Nur Entwurf"
assert regeln.vorschau_willkommen(cfg)["kanal"].startswith("ticket-0001")

# Kappungen: Discord wuerde zu lange Texte ablehnen, die Vorschau zeigt sie nicht
assert len(regeln.vorschau_willkommen({"ticket_message": "x" * 5000})["nachricht"]) <= 1900
assert len(regeln.vorschau_willkommen({"ticket_title": "y" * 900})["titel"]) <= 256
assert len(regeln.vorschau_willkommen({"ticket_created_message": "z" * 9000})["bestaetigung"]) <= 1900

# ── Panel-Vorschau ───────────────────────────────────────────────────
panel = regeln.vorschau_panel({"title": "Support", "description": "Text", "color": "#ff0000", "button_label": "Los"})
assert panel["titel"] == "Support" and panel["farbe"] == "#ff0000"
assert panel["oeffnen"]["label"] == "Los"
assert [b["label"] for b in panel["buttons"]] == ["Übernehmen", "Schließen"]
assert regeln.vorschau_panel({})["beschreibung"] == regeln.PANEL_BESCHREIBUNG

# ── Antworten ────────────────────────────────────────────────────────
block = regeln.antworten_formatieren([
    {"label": "Worum?", "type": "short", "value": "  Frage  "},
    {"label": "Beleg", "type": "image", "attachments": ["https://cdn.discordapp.com/a.png", "javascript:alert(1)"]},
    {"label": "Ohne", "type": "image", "attachments": []},
])
assert "**Worum?**\nFrage" in block
assert "https://cdn.discordapp.com/a.png" in block and "javascript" not in block
assert "_keine Datei_" in block
assert len(regeln.antworten_formatieren([{"label": "L", "type": "short", "value": "z" * 9000}])) <= 3800

# Panel-Standardtexte: Vorschau und Bot müssen denselben Default nutzen
bot_quelle = (Path(__file__).resolve().parents[1] / "lbost_shop_bot" / "client.py").read_text()
assert "regeln.PANEL_BESCHREIBUNG" in bot_quelle and "regeln.PANEL_TITEL" in bot_quelle, "Bot nutzt die Konstanten nicht"
assert "Öffne ein Ticket, um das Team zu kontaktieren." not in bot_quelle, "Bot hat einen eigenen Panel-Default"
assert regeln.vorschau_panel({})["titel"] == regeln.PANEL_TITEL

print("ok   Regeln: Woerter, Fragen, Kanalnamen, Vorschau == Bot")
