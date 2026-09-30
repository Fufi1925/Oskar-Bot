"""Isolated LBoost Shop landing page, Discord login and dashboard.

Der Bereich läuft bewusst eigenständig: eigene Discord-App, eigene Sitzung,
eigene Datenbank, eigener Bot-Prozess. Er teilt nichts mit University Bot,
Phantom oder Louckup außer der Optik und den Regeln für Tickettexte (die
liegen in ``regeln.py`` und gelten für Vorschau und Bot gleichzeitig).
"""
from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus, urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lbost_shop_app import auth, db, regeln
from lbost_shop_app import giveaways as giveaway_store
from lbost_shop_app import custom_commands as custom_command_store
from lbost_shop_app import automation as automation_store
from lbost_shop_app.config import get_settings

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))

# Login-Versuche pro IP. Ohne Kürzung wuchs das Wörterbuch mit jeder neuen IP
# für die Lebensdauer des Prozesses weiter.
_rate: dict[str, list[float]] = {}
_RATE_ALTER = 120.0

# Kurzer Zwischenspeicher für Discord-Lesungen. Ohne ihn waren pro
# Dashboard-Aufruf fünf Anfragen an Discord fällig (zwei für die Serverliste,
# drei für Kanäle, Rollen und Statistiken) — bei jedem einzelnen Klick.
_cache: dict[str, tuple[float, Any]] = {}
_CACHE_MAX = 400

COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

LOG_CATEGORIES: dict[str, dict[str, Any]] = {
    "message_events": {"label": "Nachrichten", "description": "Bearbeitete und gelöschte Nachrichten, mit dem alten Text.", "group": "Inhalte", "noisy": True},
    "join_leave_events": {"label": "Beitritt & Austritt", "description": "Wer kommt, wer geht, und wie alt das Konto war.", "group": "Menschen"},
    "member_moderation": {"label": "Moderation", "description": "Banns, Entbannungen, Timeouts und Namensänderungen.", "group": "Menschen"},
    "voice_events": {"label": "Sprachkanäle", "description": "Betreten, Verlassen und Wechseln von Sprachkanälen.", "group": "Menschen", "noisy": True},
    "channel_events": {"label": "Kanäle", "description": "Kanäle angelegt, gelöscht oder umbenannt.", "group": "Server"},
    "role_events": {"label": "Rollen", "description": "Rollen angelegt, gelöscht oder in den Rechten geändert.", "group": "Server"},
    "emoji_events": {"label": "Emojis", "description": "Server-Emojis hinzugefügt oder entfernt.", "group": "Inhalte"},
    "reaction_events": {"label": "Reaktionen", "description": "Reaktionen gesetzt und entfernt. Kann viel werden.", "group": "Inhalte", "noisy": True},
    "system_events": {"label": "Server", "description": "Servername, Symbol und andere Server-Einstellungen.", "group": "Server"},
}
LOG_GROUPS = ("Menschen", "Inhalte", "Server")


def _channel_permissions(
    guild_id: int,
    channel: dict[str, Any],
    roles: list[dict[str, Any]],
    member: dict[str, Any],
) -> int | None:
    """Calculate the bot's effective Discord permissions for one channel."""
    if not member:
        return None
    role_ids = {str(guild_id), *(str(value) for value in member.get("roles") or [])}
    permissions = 0
    for role in roles:
        if str(role.get("id")) in role_ids:
            permissions |= int(role.get("permissions") or 0)
    if permissions & (1 << 3):  # Administrator
        return (1 << 53) - 1

    overwrites = channel.get("permission_overwrites") or []

    def apply(current: int, overwrite: dict[str, Any]) -> int:
        return (current & ~int(overwrite.get("deny") or 0)) | int(overwrite.get("allow") or 0)

    everyone = next((item for item in overwrites if str(item.get("id")) == str(guild_id)), None)
    if everyone:
        permissions = apply(permissions, everyone)

    role_deny = role_allow = 0
    for item in overwrites:
        if int(item.get("type") or 0) == 0 and str(item.get("id")) in role_ids and str(item.get("id")) != str(guild_id):
            role_deny |= int(item.get("deny") or 0)
            role_allow |= int(item.get("allow") or 0)
    permissions = (permissions & ~role_deny) | role_allow

    user_id = str((member.get("user") or {}).get("id") or "")
    user_overwrite = next(
        (item for item in overwrites if int(item.get("type") or 0) == 1 and str(item.get("id")) == user_id),
        None,
    )
    return apply(permissions, user_overwrite) if user_overwrite else permissions


def normalise_logging(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Read both the old single-channel format and the University format."""
    raw = dict(raw or {})
    fallback = str(raw.get("channel_id") or "")
    old_flags = {
        "message_events": "message_logs",
        "join_leave_events": "member_logs",
        "member_moderation": "moderation_logs",
        "voice_events": "member_logs",
        "channel_events": "role_channel_logs",
        "role_events": "role_channel_logs",
        "emoji_events": "role_channel_logs",
        "reaction_events": "message_logs",
        "system_events": "role_channel_logs",
    }
    channels = dict(raw.get("log_channels") or {})
    enabled = dict(raw.get("log_enabled") or {})
    for key in LOG_CATEGORIES:
        if fallback and not channels.get(key):
            channels[key] = fallback
        if key not in enabled:
            enabled[key] = bool(raw.get(old_flags[key], False))
    return {
        "enabled": bool(raw.get("enabled")),
        "log_channels": {key: str(value) for key, value in channels.items() if key in LOG_CATEGORIES and str(value).isdigit()},
        "log_enabled": {key: bool(enabled.get(key)) for key in LOG_CATEGORIES},
        "ignore_channels": [str(value) for value in raw.get("ignore_channels", []) if str(value).isdigit()],
        "ignore_roles": [str(value) for value in raw.get("ignore_roles", []) if str(value).isdigit()],
        "ignore_users": [str(value) for value in raw.get("ignore_users", []) if str(value).isdigit()],
        "auto_delete_duration": int(raw.get("auto_delete_duration") or 0),
    }

FEATURES: dict[str, dict[str, Any]] = {
    "tickets": {"title": "Advanced Ticket System", "icon": "ticket", "fields": [
        ("enabled", "Aktiviert", "bool"), ("panel_channel_id", "Panel-Kanal", "channel"),
        ("category_id", "Ticket-Kategorie", "channel"), ("log_channel_id", "Transkript-/Log-Kanal", "channel"),
        ("support_role_ids", "Support-Rollen (IDs, Komma)", "text"),
        ("open_role_ids", "Darf Tickets öffnen (Rollen-IDs, leer = alle)", "text"),
        ("mention_support", "Support bei neuem Ticket erwähnen", "bool"),
        ("button_label", "Öffnen-Button", "text"),
        ("button_emoji", "Öffnen-Emoji", "text"), ("claim_label", "Übernehmen-Button", "text"),
        ("claim_emoji", "Übernehmen-Emoji", "text"), ("close_label", "Schließen-Button", "text"),
        ("close_emoji", "Übernehmen-Emoji", "text"), ("delete_label", "Löschen-Button", "text"),
        ("delete_emoji", "Löschen-Emoji", "text"),
        ("title", "Embed-Titel", "text"),
        ("description", "Beschreibung", "textarea"), ("footer", "Footer", "text"),
        ("color", "Farbe", "color"), ("image_url", "Bild-URL", "url"), ("thumbnail_url", "Thumbnail-URL", "url"),
        ("ticket_title", "Überschrift im Ticket", "text"),
        ("ticket_message", "Begrüßung im Ticket", "textarea"),
        ("ticket_created_message", "Bestätigung an den Nutzer", "text"),
        ("ticket_image_url", "Bild im Ticket", "url"), ("ticket_thumbnail_url", "Thumbnail im Ticket", "url"),
        ("channel_name_format", "Kanalname (leer = Standard)", "text"),
        ("slowmode_seconds", "Slowmode im Ticket (Sekunden)", "number"),
        ("questions_json", "Fragen beim Öffnen (JSON)", "json"),
        ("panels_json", "Weitere Panels (JSON)", "json"),
    ]},
    "moderation": {"title": "Moderation", "icon": "shield", "fields": [
        ("enabled", "Aktiviert", "bool"), ("topcheck", "Topcheck", "bool"),
        ("prefix", "Befehlspräfix", "text"), ("log_channel_id", "Moderations-Log", "channel"),
        ("anti_spam", "Anti-Spam", "bool"), ("spam_limit", "Nachrichten je 8 Sekunden", "number"),
        ("spam_timeout", "Timeout bei Spam", "bool"),
        ("anti_links", "Anti-Link", "bool"), ("allowed_domains", "Erlaubte Domains (Komma)", "text"),
        ("link_timeout", "Timeout bei fremdem Link", "bool"),
        ("spam_timeout_minuten", "Timeout-Dauer (Minuten)", "number"),
        ("exempt_role_ids", "Ausgenommene Rollen (IDs, Komma)", "text"),
    ]},
    "welcome": {"title": "Welcome & Leave", "icon": "users", "fields": [
        ("enabled", "Begrüßung aktiviert", "bool"), ("welcome_channel_id", "Willkommenskanal", "channel"),
        ("welcome_type", "Nachrichtenart", "text"), ("welcome_message", "Willkommenstext", "textarea"),
        ("welcome_auto_delete_duration", "Nach Sekunden löschen", "number"),
        ("welcome_embed_message", "Text über der Karte", "textarea"),
        ("welcome_embed_title", "Kartenüberschrift", "text"),
        ("welcome_embed_description", "Kartenbeschreibung", "textarea"),
        ("welcome_embed_author_name", "Kopfzeile", "text"),
        ("welcome_embed_author_icon", "Kopfzeilenbild", "url"),
        ("welcome_embed_footer_text", "Fußzeile", "text"),
        ("welcome_embed_footer_icon", "Fußzeilenbild", "url"),
        ("welcome_embed_thumbnail", "Thumbnail", "url"), ("welcome_embed_image", "Kartenbild", "url"),
        ("color", "Farbe", "color"), ("welcome_image_enabled", "Generiertes Willkommensbild", "bool"),
        ("welcome_image_url", "Eigener Willkommenshintergrund", "url"),
        ("leave_enabled", "Abschied aktiviert", "bool"), ("leave_channel_id", "Abschiedskanal", "channel"),
        ("leave_message", "Abschiedstext", "textarea"),
        ("leave_auto_delete_duration", "Nach Sekunden löschen", "number"),
        ("leave_image_enabled", "Generiertes Abschiedsbild", "bool"),
        ("leave_image_url", "Eigener Abschiedshintergrund", "url"),
    ]},
    "reaction_roles": {"title": "Reaktions-Rollen", "icon": "users", "fields": [
        ("enabled", "Aktiviert", "bool"),
    ]},
    "custom_commands": {"title": "Custom Commands", "icon": "command", "fields": [
        ("enabled", "Aktiviert", "bool"),
    ]},
    "automation": {"title": "Automation", "icon": "bolt", "fields": [
        ("enabled", "Aktiviert", "bool"), ("auto_responses_json", "Auto-Antworten (JSON)", "json"),
        ("announcements_json", "Automatische Nachrichten (JSON)", "json"),
    ]},
    "logging": {"title": "Logging", "icon": "log", "fields": [
        ("enabled", "Aktiviert", "bool"), ("channel_id", "Log-Kanal", "channel"),
        ("member_logs", "Mitglieder-Logs", "bool"), ("message_logs", "Nachrichten-Logs", "bool"),
        ("moderation_logs", "Moderations-Logs", "bool"), ("role_channel_logs", "Rollen-/Kanal-Logs", "bool"),
        ("ticket_logs", "Ticket-Logs", "bool"),
    ]},
    "giveaways": {"title": "Giveaways", "icon": "gift", "fields": [
        ("enabled", "Aktiviert", "bool"), ("log_channel_id", "Giveaway-Log", "channel"),
        ("manager_role_ids", "Manager-Rollen (IDs, Komma)", "text"),
        ("required_role_id", "Pflicht-Rolle zum Mitmachen (ID, leer = jede)", "text"),
        ("default_winners", "Standard-Anzahl Gewinner", "number"),
    ]},
}

#: Wo der Bot Platzhalter ersetzt — im Dashboard sichtbar, damit niemand
#: rätet, welche Wörter funktionieren.
PLATZHALTER = {
    "tickets": "Platzhalter: {ticket_number} {user} {category} {server} {channel}",
    "welcome": "Platzhalter: {user} {server} {member_count} {channel}",
}

#: Grenzen pro Feld. Ohne diese Liste konnte jemand „Nachrichten je 8
#: Sekunden = 0“ eintragen und jeder einzelne Beitrag galt als Spam.
GRENZEN: dict[str, tuple[int, int]] = {
    "spam_limit": (3, 100),
    "spam_timeout_minuten": (1, 1440),
    "default_winners": (1, 20),
    "slowmode_seconds": (0, 30),
    "welcome_auto_delete_duration": (0, 86400),
    "leave_auto_delete_duration": (0, 86400),
}

JSON_MAX_FELDER = 50
JSON_MAX_GROESSE = 32_000

JSON_HELP: dict[str, dict[str, str]] = {
    "tickets": {
        "panels_json": '[{"key":"billing","title":"Billing Support","panel_channel_id":"123","category_id":"456","support_role_ids":"789","button_label":"Billing-Ticket"}]',
        "questions_json": '[{"label":"Um was geht es?","placeholder":"Kurz beschreiben","type":"short","required":true},{"label":"Beleg","type":"image","required":false}]',
    },
    "reaction_roles": {
        "roles_json": '[{"role_id":"123","label":"Updates","emoji":"<:bell:123456>"}]',
        "panels_json": '[{"title":"Game Roles","channel_id":"123","roles_json":[{"role_id":"456","label":"Player"}]}]',
    },
    "automation": {
        "auto_responses_json": '[{"trigger":"hello","response":"Welcome!","exact":false,"cooldown_seconds":30}]',
        "custom_commands_json": '[{"name":"rules","title":"Rules","response":"Read the server rules."}]',
        "announcements_json": '[{"channel_id":"123","title":"News","content":"Automatic update","interval_minutes":1440}]',
    },
}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    # style-src bleibt bei 'self': Das Dashboard erzeugt seine Füllgrade über
    # Klassen, nicht über style-Attribute. Wer hier "schnell" unsafe-inline
    # einträgt, macht die Policy zur Deko.
    "Content-Security-Policy": "default-src 'self'; img-src 'self' https://cdn.discordapp.com; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
}


def _static_version() -> str:
    """Versions-Suffix für CSS/JS: langer Cache plus sicherer Neubeladung."""
    markierungen = []
    for datei in sorted((APP_DIR / "static").rglob("*")):
        if datei.is_file() and datei.suffix in {".css", ".js"}:
            stat = datei.stat()
            markierungen.append(f"{datei.name}:{int(stat.st_mtime)}:{stat.st_size}")
    return f"{abs(hash(tuple(markierungen))) % 10**8:08d}"


def _kurz(schluessel: str) -> Any:
    eintrag = _cache.get(schluessel)
    if not eintrag:
        return None
    wert, bis = eintrag
    if time.monotonic() > bis:
        _cache.pop(schluessel, None)
        return None
    return wert


def _kurz_setzen(schluessel: str, wert: Any, sekunden: float) -> None:
    if len(_cache) > _CACHE_MAX:
        jetzt = time.monotonic()
        for alt in [k for k, (_wert, bis) in _cache.items() if bis <= jetzt]:
            _cache.pop(alt, None)
        while len(_cache) > _CACHE_MAX:
            _cache.pop(next(iter(_cache)))
    _cache[schluessel] = (wert, time.monotonic() + sekunden)


def cache_leeren() -> None:
    """Nur für Tests und nach Änderungen, die sofort sichtbar sein sollen."""
    _cache.clear()


def _rate_pruefen(ip: str, grenze: int) -> bool:
    """True, wenn der Versuch erlaubt ist. Leert alte IPs nebenbei."""
    jetzt = time.time()
    if len(_rate) > 5000:
        for alt in [k for k, v in _rate.items() if not v or jetzt - v[-1] > _RATE_ALTER]:
            _rate.pop(alt, None)
    hits = [stamp for stamp in _rate.get(ip, []) if jetzt - stamp < 60]
    hits.append(jetzt)
    _rate[ip] = hits
    return len(hits) <= grenze


def _rollen_ids(wert: Any) -> str:
    """Rollen-/ID-Listen normalisieren: nur Ziffern, durch Komma getrennt."""
    teile = re.split(r"[,;\s]+", str(wert or ""))
    sauber = [teil for teil in teile if teil.isdigit() and len(teil) <= 21]
    return ",".join(dict.fromkeys(sauber))


def _url_pruefen(feld: str, wert: str) -> str | None:
    """Bild-URLs müssen http(s) sein — sonst zeigt Discord ein kaputtes Bild."""
    if not wert:
        return None
    if wert in {"{user_avatar}", "{server_icon}"}:
        return None
    try:
        ziel = urlparse(wert)
    except ValueError:
        return f"{feld}: keine gültige URL."
    if ziel.scheme not in {"http", "https"} or not ziel.netloc:
        return f"{feld}: nur http(s)-Links erlaubt."
    if len(wert) > 600:
        return f"{feld}: URL ist länger als 600 Zeichen."
    return None


def _json_pruefen(wert: str) -> tuple[Any, str | None]:
    if not wert.strip():
        return [], None
    if len(wert) > JSON_MAX_GROESSE:
        return None, f"JSON ist größer als {JSON_MAX_GROESSE // 1000} KB."
    try:
        parsed = json.loads(wert)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "JSON konnte nicht gelesen werden."
    if not isinstance(parsed, (list, dict)):
        return None, "JSON muss eine Liste oder ein Objekt sein."
    if isinstance(parsed, list) and len(parsed) > JSON_MAX_FELDER:
        return None, f"Höchstens {JSON_MAX_FELDER} Einträge."
    if isinstance(parsed, list):
        parsed = [eintrag for eintrag in parsed if isinstance(eintrag, dict)]
    return parsed, None


async def _discord_abfrage(bot_token: str, pfad: str, params: dict[str, str] | None = None) -> Any:
    """Ein Discord-Lesaufruf mit Bot-Token. Eigene Funktion: Tests docken hier an.

    Der Bot liest Kanäle, Rollen und Serverzahlen für die Auswahlfelder — ohne
    these Funktion müsste jeder Test httpx global umbiegen.
    """
    import httpx

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            f"https://discord.com/api/v10{pfad}",
            params=params or None,
            headers={"Authorization": f"Bot {bot_token}"},
        )
        response.raise_for_status()
        return response.json()


def _panels_bereinigen(eintraege: list[Any]) -> list[dict[str, Any]]:
    """Panels brauchen einen key — sonst weiß der Bot nicht, welches er meinen soll."""
    sauber: list[dict[str, Any]] = []
    gesehen: set[str] = set()
    for eintrag in eintraege:
        if not isinstance(eintrag, dict):
            continue
        schluessel = str(eintrag.get("key") or "").strip()[:40]
        if not schluessel or not re.fullmatch(r"[a-z0-9_-]+", schluessel.lower()):
            continue
        if schluessel.lower() in gesehen:
            continue
        gesehen.add(schluessel.lower())
        sauber.append({k: (v if not isinstance(v, str) else v[:4000]) for k, v in eintrag.items()})
    return sauber


def _werte_aus_formular(spec: dict[str, Any], form: Any, feature: str = "") -> tuple[dict[str, Any], list[str]]:
    """Formular in die Liste der erlaubten Felder übersetzen.

    Alles, was hier nicht durchgeht, steht danach in der Datenbank und wird
    vom Bot gelesen — deshalb: Zahlen begrenzt, IDs nur Ziffern, URLs nur
    http(s), JSON in Größe und Einträgen gekappt.
    """
    values: dict[str, Any] = {}
    fehler: list[str] = []
    for key, label, typ in spec["fields"]:
        eingabe = form.get(key)
        raw = str(eingabe if eingabe is not None else "").strip()
        if typ == "bool":
            values[key] = key in form
        elif typ == "number":
            minimum, maximum = GRENZEN.get(key, (1, 1000))
            if raw == "":
                # Leer gelassen heit "nichts eingestellt", nicht "der
                # kleinste erlaubte Wert". Ein importiertes 0 duerfen wir
                # nicht stillschweigend zu 3 verbiegen.
                continue
            try:
                zahl = int(raw)
            except ValueError:
                fehler.append(f"{label}: keine Zahl.")
                continue
            if not minimum <= zahl <= maximum:
                fehler.append(f"{label}: nur Werte von {minimum} bis {maximum}.")
                continue
            values[key] = zahl
        elif typ == "json":
            parsed, meldung = _json_pruefen(raw)
            if meldung:
                fehler.append(f"{label}: {meldung}")
                continue
            if key == "questions_json" and isinstance(parsed, list):
                parsed = regeln.fragen_bereinigen(parsed)
            elif key == "panels_json" and feature == "tickets" and isinstance(parsed, list):
                parsed = _panels_bereinigen(parsed)
            values[key] = parsed
        elif typ == "url":
            meldung = _url_pruefen(label, raw)
            if meldung:
                fehler.append(meldung)
                continue
            values[key] = raw
        elif typ == "color":
            if raw and not COLOR_RE.match(raw):
                fehler.append(f"{label}: Farbe bitte als #rrggbb.")
                continue
            values[key] = raw
        elif key.endswith("_role_ids") or key.endswith("_role_id"):
            values[key] = _rollen_ids(raw)
        elif typ == "channel":
            if raw and not raw.isdigit():
                fehler.append(f"{label}: Kanal-ID ungültig.")
                continue
            values[key] = raw
        else:
            values[key] = raw[:10] if key == "prefix" else raw[:4000]
    return values, fehler


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="LBoost Shop", docs_url=None, redoc_url=None, openapi_url=None)
    # Antworten sind JSON und HTML, beide gut komprimierbar; die Seite hängt
    # hinter dem Railway-Proxy ohne eigenen Cache.
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")
    db.init_features(settings)
    db.prune_audit(settings)
    version = _static_version()

    def _zeitpunkt(wert: Any) -> str:
        """Unix-Sekunden als Lesedatum für die Tabellen."""
        try:
            return time.strftime("%d.%m.%Y %H:%M", time.localtime(int(wert)))
        except (TypeError, ValueError, OSError):
            return "—"

    TEMPLATES.env.filters["strftime"] = _zeitpunkt
    TEMPLATES.env.filters["seit_minuten"] = lambda wert: (
        "gerade eben" if not wert or int(time.time()) - int(wert) < 60
        else f"vor {(int(time.time()) - int(wert)) // 60} Min."
    )
    TEMPLATES.env.filters["json_pretty"] = lambda wert: (
        json.dumps(wert, ensure_ascii=False, indent=2) if wert not in (None, [], {}, "") else ""
    )

    def prefix(request: Request) -> str:
        return (request.scope.get("root_path") or settings.root_path).rstrip("/")

    def href(request: Request, path: str) -> str:
        return f"{prefix(request)}/{path.lstrip('/')}" if path else f"{prefix(request)}/"

    def secure(request: Request) -> bool:
        return (request.headers.get("x-forwarded-proto") or request.url.scheme).lower() == "https"

    def current_user(request: Request) -> dict[str, Any] | None:
        user = auth.session_user(request)
        if not user or int(user["uid"]) not in settings.allowed_ids:
            return None
        if not db.load_oauth_session(str(user["sid"]), int(user["uid"]), settings):
            return None
        user["is_owner"] = int(user["uid"]) in settings.owner_id_set
        return user

    def bot_status() -> dict[str, Any]:
        """Echter Zustand des Bot-Prozesses statt einer festen Zeile."""
        state = db.get_state(0, "bot_heartbeat", settings) or {}
        wert = state.get("wert") if isinstance(state, dict) else None
        if not isinstance(wert, dict):
            return {"online": False, "vor": None, "gilden": 0, "name": "", "token": bool(settings.bot_token), "vollstaendig": False}
        vor = max(0, int(time.time()) - int(wert.get("zeit") or 0))
        return {
            "online": vor <= 90,
            "vor": vor,
            "gilden": int(wert.get("gilden") or 0),
            "name": str(wert.get("name") or ""),
            "token": bool(settings.bot_token),
            "vollstaendig": bool(wert.get("vollstaendig", True)),
        }

    def context(request: Request, **extra: Any) -> dict[str, Any]:
        user = current_user(request)
        data = {
            "request": request,
            "brand": settings.brand_name,
            "root_path": prefix(request),
            "user": user,
            "avatar_url": auth.avatar_url(user),
            "missing": settings.missing_config,
            "asset_version": version,
            "status": bot_status(),
            "heute": int(time.time()),
            "audit_tage": db.AUDIT_TAGE,
            "module": FEATURES,
            "platzhalter": PLATZHALTER,
            "limits": GRENZEN,
        }
        data.update(extra)
        return data

    def render(request: Request, template: str, **extra: Any) -> HTMLResponse:
        return HTMLResponse(TEMPLATES.env.get_template(template).render(context(request, **extra)))

    def clear_session(response: RedirectResponse, request: Request | None = None) -> None:
        if request:
            session = auth.session_user(request)
            if session:
                db.delete_oauth_session(str(session.get("sid") or ""), settings)
        response.delete_cookie(settings.cookie_name, path=settings.cookie_path)
        response.delete_cookie("lbost_shop_oauth_state", path=settings.cookie_path)

    def csrf_ok(form_value: Any, user: dict[str, Any]) -> bool:
        return bool(user) and secrets.compare_digest(str(form_value or ""), str(user["sid"]))

    async def visible_guilds(user: dict[str, Any]) -> list[dict[str, Any]]:
        """Strict intersection: allowlist + bot present + Manage Guild rights."""
        session_id = str(user["sid"])
        user_id = int(user["uid"])
        schluessel = f"gilden:{user_id}"
        zwischendurch = _kurz(schluessel)
        if isinstance(zwischendurch, list):
            return zwischendurch
        stored = db.load_oauth_session(session_id, user_id, settings)
        if not stored or not settings.bot_token or not settings.allowed_guild_id_set:
            return []
        try:
            if int(stored["expires_at"]) <= int(time.time()) + 60:
                refreshed = await auth.refresh(str(stored["refresh_token"]), settings)
                if not refreshed.get("refresh_token"):
                    refreshed["refresh_token"] = str(stored["refresh_token"])
                db.save_oauth_session(session_id, user_id, refreshed, settings)
                access_token = str(refreshed["access_token"])
            else:
                access_token = str(stored["access_token"])

            user_guilds = await auth.guilds(access_token)
            bot_guilds = await auth.guilds(settings.bot_token, "Bot")
        except Exception:
            # Never leak a guild from stale/cache data when Discord cannot be checked.
            return []

        bot_map = {int(g["id"]): g for g in bot_guilds if str(g.get("id", "")).isdigit()}
        bot_ids = set(bot_map)
        visible: list[dict[str, Any]] = []
        for guild in user_guilds:
            if not str(guild.get("id", "")).isdigit():
                continue
            guild_id = int(guild["id"])
            permissions = int(guild.get("permissions") or 0)
            has_rights = bool(guild.get("owner")) or bool(permissions & 0x20) or bool(permissions & 0x8)
            if guild_id not in settings.allowed_guild_id_set or guild_id not in bot_ids or not has_rights:
                continue
            icon_hash = guild.get("icon")
            bot_guild = bot_map.get(guild_id) or {}
            member_count = bot_guild.get("approximate_member_count")
            if not isinstance(member_count, int):
                member_count = guild.get("approximate_member_count")
            visible.append({
                "id": str(guild_id),
                "name": str(guild.get("name") or "Unbenannter Server"),
                "icon_url": f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png?size=128" if icon_hash else None,
                "owner": bool(guild.get("owner")),
                "member_count": member_count if isinstance(member_count, int) else None,
            })
        ergebnis = sorted(visible, key=lambda guild: guild["name"])
        _kurz_setzen(schluessel, ergebnis, 20)
        return ergebnis

    async def guild_access(user: dict[str, Any], guild_id: int) -> dict[str, Any] | None:
        return next((guild for guild in await visible_guilds(user) if int(guild["id"]) == guild_id), None)

    async def guild_members(guild_id: int) -> list[dict[str, str]]:
        """Members for the University-style searchable user picker."""
        schluessel = f"mitglieder:{guild_id}"
        cached = _kurz(schluessel)
        if isinstance(cached, list):
            return cached
        try:
            raw = await _discord_abfrage(
                settings.bot_token, f"/guilds/{guild_id}/members", {"limit": "1000"}
            )
            members = []
            for item in raw if isinstance(raw, list) else []:
                user = item.get("user") or {}
                user_id = str(user.get("id") or "")
                if not user_id.isdigit():
                    continue
                username = str(user.get("global_name") or user.get("username") or user_id)
                avatar = str(user.get("avatar") or "")
                extension = "gif" if avatar.startswith("a_") else "png"
                members.append({
                    "id": user_id,
                    "name": str(item.get("nick") or username),
                    "username": username,
                    "avatar": avatar,
                    "avatar_url": f"https://cdn.discordapp.com/avatars/{user_id}/{avatar}.{extension}?size=64" if avatar else "",
                    "bot": bool(user.get("bot")),
                    "role_ids": [str(value) for value in item.get("roles") or []],
                })
            members.sort(key=lambda entry: entry["name"].casefold())
            _kurz_setzen(schluessel, members, 45)
            return members
        except Exception:
            return []

    async def guild_resources(
        guild_id: int, *, include_bot_permissions: bool = False
    ) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, Any]]:
        """Channels, roles and overview data for the University-style pages."""
        schluessel = f"ressourcen:{guild_id}:{int(include_bot_permissions)}"
        zwischendurch = _kurz(schluessel)
        if isinstance(zwischendurch, tuple):
            return zwischendurch
        try:
            raw_channels = await _discord_abfrage(settings.bot_token, f"/guilds/{guild_id}/channels")
            raw_roles = await _discord_abfrage(settings.bot_token, f"/guilds/{guild_id}/roles")
            raw_guild = await _discord_abfrage(settings.bot_token, f"/guilds/{guild_id}", {"with_counts": "true"})
            raw_member: dict[str, Any] = {}
            if include_bot_permissions:
                try:
                    bot_id = str(settings.discord_client_id or "")
                    if bot_id:
                        raw_member = await _discord_abfrage(settings.bot_token, f"/guilds/{guild_id}/members/{bot_id}")
                except Exception:
                    # Ressourcen bleiben benutzbar; nur die Rechtewarnung ist dann unbekannt.
                    raw_member = {}
            channels = []
            for item in raw_channels:
                if item.get("type") not in (0, 4, 5, 10, 11, 12, 15, 16):
                    continue
                permissions = _channel_permissions(guild_id, item, raw_roles, raw_member)
                channels.append({
                    "id": str(item["id"]),
                    "name": str(item.get("name") or item["id"]),
                    "type": str(item.get("type", 0)),
                    "can_view": None if permissions is None else bool(permissions & (1 << 10)),
                    "can_post": None if permissions is None else bool(permissions & (1 << 10) and permissions & (1 << 11)),
                    "can_embed": None if permissions is None else bool(permissions & (1 << 14)),
                })
            roles = [
                {
                    "id": str(item["id"]),
                    "name": str(item.get("name") or item["id"]),
                    "colour": f"#{int(item.get('color') or 0x99AAB5):06x}",
                    "position": int(item.get("position") or 0),
                    "managed": bool(item.get("managed")),
                }
                for item in raw_roles if str(item.get("id")) != str(guild_id)
            ]
            member_role_ids = {str(guild_id), *(str(value) for value in raw_member.get("roles") or [])}
            guild_permissions = 0
            for role in raw_roles:
                if str(role.get("id")) in member_role_ids:
                    guild_permissions |= int(role.get("permissions") or 0)
            stats = {
                "member_count": int(raw_guild.get("approximate_member_count") or 0),
                "channel_count": len(raw_channels),
                "role_count": max(0, len(raw_roles) - 1),
                "boost_level": int(raw_guild.get("premium_tier") or 0),
                "boost_count": int(raw_guild.get("premium_subscription_count") or 0),
                "verification_level": int(raw_guild.get("verification_level") or 0),
                "owner_id": str(raw_guild.get("owner_id") or ""),
                "bot_can_audit": None if not raw_member else bool(guild_permissions & ((1 << 3) | (1 << 7))),
            }
            ergebnis = (channels, roles, stats)
            _kurz_setzen(schluessel, ergebnis, 45)
            return ergebnis
        except Exception:
            # Bewusst nicht cached: ein kurzer Discord-Ausfall soll beim
            # nächsten Klick neu versucht werden, nicht 45 Sekunden lang.
            return [], [], {}

    @app.middleware("http")
    async def harden(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        pfad = request.url.path
        if "/static/" in pfad:
            # Dateien haben ein Versions-Suffix am Namen, deshalb dürfen sie
            # einen Tag im Browser bleiben.
            response.headers["Cache-Control"] = "public, max-age=86400"
        elif (response.headers.get("content-type") or "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, private"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request):
        return render(request, "landing.html")

    @app.get("/Login", response_class=HTMLResponse)
    async def login(request: Request):
        if current_user(request):
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        return render(request, "login.html", redirect_uri=settings.oauth_redirect_uri,
                      abgemeldet=(request.query_params.get("abgemeldet") or "").replace("-", "").isdigit() and int(request.query_params.get("abgemeldet")) or 0)

    @app.get("/login", include_in_schema=False)
    async def login_lower(request: Request):
        return RedirectResponse(href(request, "/Login"), status_code=307)

    @app.get("/auth/discord")
    async def auth_discord(request: Request):
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()
        if not _rate_pruefen(ip, settings.login_rate_limit):
            return PlainTextResponse("Zu viele Loginversuche. Bitte kurz warten.", status_code=429)
        if settings.missing_config:
            return RedirectResponse(href(request, "/Login"), status_code=302)
        oauth_state = auth.state()
        response = RedirectResponse(auth.authorize_url(oauth_state, settings), status_code=302)
        response.set_cookie("lbost_shop_oauth_state", oauth_state, max_age=600, path=settings.cookie_path, httponly=True, samesite="lax", secure=secure(request))
        return response

    @app.get("/auth/callback")
    async def callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
        expected = request.cookies.get("lbost_shop_oauth_state")
        if error or not code or not state or not expected or state != expected:
            response = RedirectResponse(href(request, "/Login"), status_code=302)
            clear_session(response, request)
            return response
        try:
            token = await auth.exchange(code, settings)
            user = await auth.discord_user(str(token.get("access_token") or ""))
            user_id = int(user["id"])
        except Exception:
            response = RedirectResponse(href(request, "/Login"), status_code=302)
            clear_session(response, request)
            return response

        # Fail closed: explicit shop IDs plus University owner IDs only.
        if user_id not in settings.allowed_ids:
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response, request)
            return response

        session_id = auth.state()
        try:
            db.purge_expired(settings)
            db.save_oauth_session(session_id, user_id, token, settings)
        except Exception:
            response = RedirectResponse(href(request, "/Login"), status_code=302)
            clear_session(response, request)
            return response
        response = RedirectResponse(href(request, "/auth/success"), status_code=302)
        response.set_cookie(settings.cookie_name, auth.create_session(user, session_id, settings), max_age=settings.session_max_age, path=settings.cookie_path, httponly=True, samesite="lax", secure=secure(request))
        response.delete_cookie("lbost_shop_oauth_state", path=settings.cookie_path)
        cache_leeren()
        return response

    @app.get("/auth/success", response_class=HTMLResponse)
    async def login_success(request: Request):
        if not current_user(request):
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response, request)
            return response
        response = render(request, "success.html")
        # Erst die sichtbare Erfolgsmeldung, danach der Dashboard-Wechsel.
        response.headers["Refresh"] = f"1.2;url={href(request, '/dashboard')}"
        return response

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        user = current_user(request)
        if not user:
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response, request)
            return response
        guilds = await visible_guilds(user)
        return render(request, "dashboard.html", guilds=guilds)

    @app.get("/servers", response_class=HTMLResponse)
    async def servers(request: Request):
        user = current_user(request)
        if not user:
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response, request)
            return response
        guilds = await visible_guilds(user)
        return render(request, "servers.html", guilds=guilds)

    def modul_daten(guild_id: int, feature: str) -> dict[str, Any]:
        """Was auf dem Server schon passiert ist — Tickets, Verwarnungen, Giveaways."""
        if feature == "tickets":
            return {
                "kennzahlen": db.ticket_kennzahlen(guild_id, settings),
                "tickets": db.tickets_fuer_gilde(guild_id, settings, 12),
                "vorschau": regeln.vorschau_willkommen(db.get_feature(guild_id, "tickets", settings)),
                "panel": regeln.vorschau_panel(db.get_feature(guild_id, "tickets", settings)),
            }
        if feature == "moderation":
            return {"warnungen": db.warnungen_fuer_gilde(guild_id, settings, 25)}
        if feature == "giveaways":
            return {"giveaways": db.giveaways_fuer_gilde(guild_id, settings, 12)}
        return {}

    @app.get("/guild/{guild_id}", response_class=HTMLResponse)
    async def guild_home(request: Request, guild_id: int):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        configured = db.all_features(guild_id, settings)
        _channels, _roles, stats = await guild_resources(guild_id)
        history = db.feature_history(guild_id, settings)
        kennzahlen = db.ticket_kennzahlen(guild_id, settings)
        warnungen = len(db.warnungen_fuer_gilde(guild_id, settings, 100))
        return render(request, "guild.html", guild=guild, features=FEATURES, configured=configured, stats=stats,
                      history=history, csrf=user["sid"], kennzahlen=kennzahlen, warnungen=warnungen,
                      active_tab=request.query_params.get("tab", "overview"),
                      restored=request.query_params.get("restored") == "1")

    @app.get("/guild/{guild_id}/config-export")
    async def export_guild_config(request: Request, guild_id: int):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        payload = {"version": 1, "guild_id": str(guild_id), "features": db.all_features(guild_id, settings)}
        response = JSONResponse(payload)
        response.headers["Content-Disposition"] = f'attachment; filename="lbost-shop-{guild_id}.json"'
        return response

    @app.post("/guild/{guild_id}/config-import")
    async def import_guild_config(request: Request, guild_id: int):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        upload = form.get("config_file")
        if not upload or not hasattr(upload, "read"):
            return PlainTextResponse("Konfigurationsdatei fehlt.", status_code=400)
        raw = await upload.read(1_000_001)
        if len(raw) > 1_000_000:
            return PlainTextResponse("Konfigurationsdatei ist zu groß.", status_code=413)
        try:
            payload = json.loads(raw)
            imported = payload.get("features", {})
            if not isinstance(imported, dict):
                raise ValueError
            uebernommen = 0
            for feature, values in imported.items():
                spec = FEATURES.get(feature)
                if not spec or not isinstance(values, dict):
                    continue
                # Nur bekannte Felder, in derselben Prüfung wie das Formular.
                # Sonst könnte eine importierte Datei Felder enthalten, die
                # das Formular ablehnen würde — und der Bot liest sie trotzdem.
                gefiltert, fehler = _werte_aus_formular(spec, values, feature)
                if fehler:
                    continue
                db.set_feature(guild_id, feature, gefiltert, int(user["uid"]), settings)
                uebernommen += 1
        except (TypeError, ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return PlainTextResponse("Ungültige Konfigurationsdatei.", status_code=400)
        return RedirectResponse(href(request, f"/guild/{guild_id}?tab=backup&restored={uebernommen}"), status_code=303)

    @app.get("/guild/{guild_id}/{feature}", response_class=HTMLResponse)
    async def feature_page(request: Request, guild_id: int, feature: str):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        spec = FEATURES.get(feature)
        if not user or not guild or not spec:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        channels, roles, resource_stats = await guild_resources(
            guild_id, include_bot_permissions=feature == "logging"
        )
        values = db.get_feature(guild_id, feature, settings)
        if feature == "reaction_roles":
            try:
                raw_emojis = await _discord_abfrage(settings.bot_token, f"/guilds/{guild_id}/emojis")
                server_emojis = [{
                    "id": str(item["id"]), "name": str(item.get("name") or "emoji"),
                    "raw": f"<{'a' if item.get('animated') else ''}:{item.get('name') or 'emoji'}:{item['id']}>",
                    "url": f"https://cdn.discordapp.com/emojis/{item['id']}.{'gif' if item.get('animated') else 'png'}?size=48",
                } for item in raw_emojis]
            except Exception:
                server_emojis = []
            role_map = {str(item["id"]): item for item in roles}
            grouped: dict[int, dict[str, Any]] = {}
            rows = db.reaktionsrollen(guild_id, settings)
            for row in rows:
                message = grouped.setdefault(int(row["message_id"]), {
                    "message_id": str(row["message_id"]), "channel_id": str(row["channel_id"]), "entries": [],
                })
                role = role_map.get(str(row["role_id"]))
                message["entries"].append({
                    **row, "role_name": role["name"] if role else None,
                    "role_colour": role["colour"] if role else "#ef4444", "missing_role": role is None,
                })
            return render(
                request, "reaction_roles.html", guild=guild, feature=feature, spec=spec,
                values=values, channels=[item for item in channels if item.get("type") in ("0", "5")],
                roles=roles, server_emojis=server_emojis, messages=list(grouped.values()), total=len(rows),
                dm_enabled=db.reaktionsrollen_dm(guild_id, settings), csrf=user["sid"],
                saved=request.query_params.get("saved") == "1",
                verified=request.query_params.get("verified") == "1",
                repaired=int(request.query_params.get("repaired") or 0),
                error=request.query_params.get("error"),
            )
        if feature == "automation":
            migrated=automation_store.migrate_legacy(settings,guild_id,values,int(user["uid"]))
            return render(
                request,"automation.html",guild=guild,feature=feature,spec=spec,
                channels=[item for item in channels if item.get("type") in ("0","5")],roles=roles,
                automated_messages=automation_store.list_items(settings,guild_id,"messages"),
                auto_responses=automation_store.list_items(settings,guild_id,"responses"),
                announcements=automation_store.list_items(settings,guild_id,"announcements"),
                csrf=user["sid"],saved=request.query_params.get("saved")=="1",
                deleted=request.query_params.get("deleted")=="1",tested=request.query_params.get("tested")=="1",
                migrated=migrated,error=request.query_params.get("error"),active_tab=request.query_params.get("tab","messages"),
            )
        if feature == "custom_commands":
            members = await guild_members(guild_id)
            commands = custom_command_store.list_all(settings, guild_id)
            # LBoost keeps its data independent. A premium flag may be set in
            # this isolated feature record by the shop owner; it is never read
            # from University databases.
            premium = bool(values.get("premium", False))
            limit = custom_command_store.PREMIUM_MAX_COMMANDS
            return render(
                request, "custom_commands.html", guild=guild, feature=feature, spec=spec,
                channels=[item for item in channels if item.get("type") in ("0", "5")],
                roles=roles, members=members, commands=commands, count=len(commands), limit=limit,
                premium=premium, prefix=str(db.get_feature(guild_id, "moderation", settings).get("prefix") or "!"),
                csrf=user["sid"], saved=request.query_params.get("saved") == "1",
                deleted=request.query_params.get("deleted") == "1", error=request.query_params.get("error"),
            )
        if feature == "giveaways":
            members = await guild_members(guild_id)
            running, ended = [], []
            now = int(time.time())
            for row in giveaway_store.list_all(guild_id, settings):
                row["entry_count"] = len(giveaway_store.entries(int(row["message_id"]), settings))
                row["winner_ids_list"] = giveaway_store.past_winners(int(row["message_id"]), settings)
                row["running"] = row.get("status") == "active" and int(row.get("ends_at") or 0) > now
                (running if row["running"] else ended).append(row)
            return render(request, "giveaways.html", guild=guild, feature=feature, spec=spec,
                channels=[item for item in channels if item.get("type") in ("0", "5")], roles=roles,
                members=members, running=running, ended=ended, csrf=user["sid"],
                saved=request.query_params.get("saved") == "1", error=request.query_params.get("error"))
        if feature == "welcome":
            defaults = {
                "welcome_type": "simple", "color": "#5865f2",
                "welcome_image_enabled": True, "leave_image_enabled": True,
                "welcome_message": "Willkommen {user} auf **{server_name}**! Du bist Mitglied Nummer {server_membercount}.",
                "leave_message": "**{user_nick}** hat den Server verlassen.",
            }
            return render(
                request, "welcome.html", guild=guild, feature=feature, spec=spec,
                values={**defaults, **values}, channels=[item for item in channels if item.get("type") in ("0", "5")],
                roles=roles, csrf=user["sid"], saved=request.query_params.get("saved") == "1",
                tested=request.query_params.get("tested"), error=request.query_params.get("error"),
                active_tab=request.query_params.get("tab", "welcome"),
            )
        if feature == "moderation":
            members = await guild_members(guild_id)
            member_map = {str(item["id"]): item for item in members}
            rows = db.warnungen_fuer_gilde(guild_id, settings, 200)
            grouped: dict[str, dict[str, Any]] = {}
            for row in rows:
                uid = str(row["user_id"])
                target = grouped.setdefault(uid, {
                    "user_id": uid,
                    "name": member_map.get(uid, {}).get("display_name") or member_map.get(uid, {}).get("name") or "Unbekanntes Mitglied",
                    "entries": [],
                })
                target["entries"].append(row)
            return render(
                request, "moderation.html", guild=guild, feature=feature, spec=spec,
                values=values, channels=[item for item in channels if item.get("type") in ("0", "5")],
                roles=roles, members=members, warning_users=list(grouped.values()),
                warning_total=len(rows), csrf=user["sid"],
                saved=request.query_params.get("saved") == "1",
                added=request.query_params.get("added") == "1",
                geloescht=request.query_params.get("geloescht") == "1",
                error=request.query_params.get("error"),
            )
        if feature == "logging":
            values = normalise_logging(values)
            channel_ids = {item["id"] for item in channels}
            role_ids = {item["id"] for item in roles}
            members = await guild_members(guild_id)
            roles_by_id = {item["id"]: item for item in roles}
            for member in members:
                member_roles = [roles_by_id[value] for value in member.get("role_ids", []) if value in roles_by_id]
                top_role = max(member_roles, key=lambda item: item.get("position", 0), default=None)
                member["top_role"] = top_role["name"] if top_role else ""
            warnings: list[str] = []
            if resource_stats.get("bot_can_audit") is False:
                warnings.append("Ohne „Audit-Log einsehen“ steht bei Banns und gelöschten Nachrichten nicht, wer es war.")
            channel_map = {item["id"]: item for item in channels}
            panel_order = {
                "join_leave_events": 0, "member_moderation": 1, "voice_events": 2,
                "message_events": 0, "emoji_events": 1, "reaction_events": 2,
                "channel_events": 0, "role_events": 1, "system_events": 2,
            }
            categories = []
            for key, category in LOG_CATEGORIES.items():
                channel_id = values["log_channels"].get(key, "")
                channel_info = channel_map.get(channel_id)
                missing = bool(channel_id and channel_info is None)
                cannot_post = bool(channel_info and channel_info.get("can_post") is False)
                cannot_embed = bool(channel_info and channel_info.get("can_embed") is False)
                broken = bool(values["log_enabled"].get(key) and (not channel_id or missing or cannot_post))
                if values["log_enabled"].get(key) and not channel_id:
                    warnings.append(f"„{category['label']}“ ist an, aber ohne Kanal wird nichts gepostet.")
                elif missing:
                    warnings.append(f"Der Kanal für „{category['label']}“ existiert nicht mehr.")
                elif cannot_post:
                    warnings.append(f"Der Bot darf im Kanal für „{category['label']}“ nicht schreiben.")
                elif cannot_embed:
                    warnings.append(f"Ohne „Links einbetten“ bleiben Einträge für „{category['label']}“ unvollständig.")
                categories.append({
                    "key": key, **category, "channel": channel_id,
                    "enabled": values["log_enabled"].get(key, False),
                    "broken": broken, "missing": missing,
                    "cannot_post": cannot_post, "cannot_embed": cannot_embed,
                    "group_order": panel_order[key],
                })
            for channel_id in values["ignore_channels"]:
                if channel_id not in channel_ids:
                    warnings.append(f"Ein ausgenommener Kanal ({channel_id}) existiert nicht mehr.")
            for role_id in values["ignore_roles"]:
                if role_id not in role_ids:
                    warnings.append(f"Eine ausgenommene Rolle ({role_id}) existiert nicht mehr.")
            return render(
                request, "logging.html", guild=guild, feature=feature, spec=spec,
                values=values, categories=categories, groups=LOG_GROUPS,
                channels=[item for item in channels if item.get("type") in ("0", "5")],
                roles=roles, members=members, warnings=warnings,
                active_count=sum(1 for item in categories if item["enabled"] and item["channel"]),
                broken_count=sum(1 for item in categories if item["broken"]),
                exception_count=len(values["ignore_channels"]) + len(values["ignore_roles"]) + len(values["ignore_users"]),
                csrf=user["sid"], saved=request.query_params.get("saved") == "1",
                tested=request.query_params.get("tested") == "1",
                error=request.query_params.get("error"),
            )
        return render(request, "feature.html", guild=guild, feature=feature, spec=spec, values=values,
                      channels=channels, roles=roles, csrf=user["sid"],
                      saved=request.query_params.get("saved") == "1",
                      geloescht=request.query_params.get("geloescht") == "1",
                      discord_ok=bool(channels or roles),
                      error=None, json_help=JSON_HELP.get(feature, {}), daten=modul_daten(guild_id, feature))

    @app.post("/guild/{guild_id}/{feature}", response_class=HTMLResponse)
    async def save_feature(request: Request, guild_id: int, feature: str):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        spec = FEATURES.get(feature)
        if not user or not guild or not spec:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        if feature == "welcome":
            values, fehler = _werte_aus_formular(spec, form, feature)
            if values.get("welcome_type") not in {"simple", "embed"}:
                values["welcome_type"] = "simple"
            channels, _roles, _stats = await guild_resources(guild_id)
            channel_ids = {str(item["id"]) for item in channels if item.get("type") in ("0", "5")}
            for key in ("welcome_channel_id", "leave_channel_id"):
                if values.get(key) and str(values[key]) not in channel_ids:
                    fehler.append("Der ausgewählte Kanal existiert nicht.")
            for key in ("welcome_image_url", "leave_image_url"):
                url = str(values.get(key) or "")
                if url and (not url.startswith("https://") or url.split("?", 1)[0].lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")) is False):
                    fehler.append("Hintergrundbilder müssen HTTPS-Bildadressen sein.")
            if fehler:
                return RedirectResponse(href(request, f"/guild/{guild_id}/welcome?tab={form.get('tab') or 'welcome'}&error=" + quote_plus(" ".join(fehler[:3]))), status_code=303)
            db.set_feature(guild_id, feature, values, int(user["uid"]), settings)
            return RedirectResponse(href(request, f"/guild/{guild_id}/welcome?tab={form.get('tab') or 'welcome'}&saved=1"), status_code=303)
        if feature == "logging":
            previous = normalise_logging(db.get_feature(guild_id, feature, settings))
            channels, roles, _stats = await guild_resources(guild_id)
            channel_ids = {item["id"] for item in channels if item.get("type") in ("0", "5")}
            role_ids = {item["id"] for item in roles}
            action = str(form.get("action") or "save")
            preset_keys = {
                "essential": {"member_moderation", "join_leave_events", "system_events"},
                "usual": {"member_moderation", "join_leave_events", "system_events", "message_events", "channel_events", "role_events", "voice_events"},
                "everything": set(LOG_CATEGORIES),
            }
            all_channel = str(form.get("all_channel") or "")
            if action in preset_keys:
                if all_channel not in channel_ids:
                    return RedirectResponse(href(request, f"/guild/{guild_id}/logging?error=Bitte+zuerst+einen+Log-Kanal+auswählen"), status_code=303)
                selected = preset_keys[action]
                previous["enabled"] = True
                for key in LOG_CATEGORIES:
                    previous["log_enabled"][key] = key in selected
                    if key in selected:
                        previous["log_channels"][key] = all_channel
                db.set_feature(guild_id, feature, previous, int(user["uid"]), settings)
                return RedirectResponse(href(request, f"/guild/{guild_id}/logging?saved=1"), status_code=303)
            values = normalise_logging(previous)
            values["enabled"] = "enabled" in form
            for key in LOG_CATEGORIES:
                channel_id = str(form.get(f"channel_{key}") or "")
                values["log_enabled"][key] = f"enabled_{key}" in form
                if channel_id:
                    if channel_id not in channel_ids:
                        return RedirectResponse(href(request, f"/guild/{guild_id}/logging?error=Ungültiger+Log-Kanal"), status_code=303)
                    values["log_channels"][key] = channel_id
                else:
                    values["log_channels"].pop(key, None)
                    values["log_enabled"][key] = False
            values["ignore_channels"] = list(dict.fromkeys(value for value in form.getlist("ignore_channels") if value in channel_ids))
            values["ignore_roles"] = list(dict.fromkeys(value for value in form.getlist("ignore_roles") if value in role_ids))
            values["ignore_users"] = list(dict.fromkeys(value.strip() for value in str(form.get("ignore_users") or "").replace(";", ",").split(",") if value.strip().isdigit()))
            try:
                values["auto_delete_duration"] = max(0, min(86400, int(str(form.get("auto_delete_duration") or "0"))))
            except ValueError:
                return RedirectResponse(href(request, f"/guild/{guild_id}/logging?error=Ungültige+Löschdauer"), status_code=303)
            db.set_feature(guild_id, feature, values, int(user["uid"]), settings)
            return RedirectResponse(href(request, f"/guild/{guild_id}/logging?saved=1"), status_code=303)
        values, fehler = _werte_aus_formular(spec, form, feature)
        if fehler:
            channels, roles, _stats = await guild_resources(guild_id)
            return render(request, "feature.html", guild=guild, feature=feature, spec=spec,
                          values={**db.get_feature(guild_id, feature, settings), **values},
                          channels=channels, roles=roles, csrf=user["sid"], saved=False,
                          discord_ok=bool(channels or roles),
                          error=" ".join(fehler[:4]), json_help=JSON_HELP.get(feature, {}),
                          daten=modul_daten(guild_id, feature))
        db.set_feature(guild_id, feature, values, int(user["uid"]), settings)
        return RedirectResponse(href(request, f"/guild/{guild_id}/{feature}?saved=1"), status_code=303)

    @app.post("/guild/{guild_id}/welcome/test/{kind}")
    async def test_greeting(request: Request, guild_id: int, kind: str):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild or kind not in {"welcome", "leave"}:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        values = db.get_feature(guild_id, "welcome", settings)
        # The University test button sends the current draft, not only the
        # last saved row. This lets the real Discord preview validate edits
        # before they are committed.
        draft, _draft_errors = _werte_aus_formular(FEATURES["welcome"], form, "welcome")
        values = {**values, **draft}
        channel_id = str(values.get(f"{kind}_channel_id") or "")
        if not channel_id or not settings.bot_token:
            return RedirectResponse(href(request, f"/guild/{guild_id}/welcome?tab={kind}&error=Kanal+oder+Bot-Token+fehlt"), status_code=303)
        samples = {
            "user": f"<@{user['uid']}>", "user_name": str(user.get("username") or "Neuer"),
            "user_nick": str(user.get("global_name") or user.get("username") or "Neuer"),
            "user_id": str(user["uid"]), "user_avatar": avatar_url(user),
            "user_joindate": "heute", "user_createdate": "08.01.2024",
            "server_name": str(guild.get("name") or "Server"), "server_id": str(guild_id),
            "server_membercount": str(guild.get("member_count") or 1), "server_icon": str(guild.get("icon_url") or ""),
            "timestamp": "jetzt", "server": str(guild.get("name") or "Server"), "count": str(guild.get("member_count") or 1),
        }
        def fill(value: Any) -> str:
            return re.sub(r"\{(\w+)\}", lambda match: samples.get(match.group(1).lower(), match.group(0)), str(value or ""))
        title = "Willkommen" if kind == "welcome" else "Abschied"
        text = fill(values.get(f"{kind}_message") or ("Willkommen {user} auf **{server_name}**!" if kind == "welcome" else "**{user_nick}** hat den Server verlassen."))
        if kind == "welcome" and values.get("welcome_type") == "embed":
            title = fill(values.get("welcome_embed_title") or title)
            text = fill(values.get("welcome_embed_description") or values.get("welcome_message") or text)
        components: list[dict[str, Any]] = [{"type": 10, "content": f"## {title}\n{text}"[:4000]}]
        banner = None
        if values.get(f"{kind}_image_enabled", True):
            try:
                import httpx
                from lbost_shop_bot import welcome_card
                avatar_bytes = None
                background_bytes = None
                async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as media_client:
                    avatar = samples.get("user_avatar")
                    if avatar:
                        media = await media_client.get(avatar)
                        if media.status_code == 200 and len(media.content) <= 8 * 1024 * 1024:
                            avatar_bytes = media.content
                    background_url = str(values.get(f"{kind}_image_url") or "")
                    if background_url:
                        media = await media_client.get(background_url)
                        if media.status_code == 200 and len(media.content) <= 8 * 1024 * 1024:
                            background_bytes = media.content
                banner = await asyncio.to_thread(
                    welcome_card.render, name=samples["user_nick"], avatar_bytes=avatar_bytes,
                    guild_name=samples["server_name"], member_count=int(samples["server_membercount"]),
                    accent=int(str(values.get("color") or "#3b82f6").lstrip("#"), 16),
                    background_bytes=background_bytes,
                    label="WILLKOMMEN" if kind == "welcome" else "TSCHUESS",
                    subtitle=None if kind == "welcome" else f"hat {samples['server_name']} verlassen",
                    counter_text=None,
                )
                if banner:
                    components.append({"type": 12, "items": [{"media": {"url": "attachment://vorschau.png"}}]})
            except Exception:
                banner = None
        payload = {"flags": 32768, "allowed_mentions": {"parse": []}, "components": [{"type": 17, "accent_color": int(str(values.get("color") or "#5865f2").lstrip("#"), 16), "components": components}]}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=20.0) as client:
                if banner:
                    response = await client.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", headers={"Authorization": f"Bot {settings.bot_token}"}, data={"payload_json": json.dumps(payload)}, files={"files[0]": ("vorschau.png", banner.getvalue(), "image/png")})
                else:
                    response = await client.post(f"https://discord.com/api/v10/channels/{channel_id}/messages", headers={"Authorization": f"Bot {settings.bot_token}"}, json=payload)
                response.raise_for_status()
        except Exception:
            return RedirectResponse(href(request, f"/guild/{guild_id}/welcome?tab={kind}&error=Testnachricht+konnte+nicht+gesendet+werden"), status_code=303)
        return RedirectResponse(href(request, f"/guild/{guild_id}/welcome?tab={kind}&tested={kind}"), status_code=303)

    @app.post("/guild/{guild_id}/logging/test/{category}")
    async def test_logging(request: Request, guild_id: int, category: str):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild or category not in LOG_CATEGORIES:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        values = normalise_logging(db.get_feature(guild_id, "logging", settings))
        channel_id = values["log_channels"].get(category)
        if not channel_id:
            return RedirectResponse(href(request, f"/guild/{guild_id}/logging?error=Kein+Kanal+konfiguriert"), status_code=303)
        try:
            import httpx
            payload = {
                "flags": 32768,
                "allowed_mentions": {"parse": []},
                "components": [{
                    "type": 17,
                    "accent_color": 0x5865F2,
                    "components": [
                        {"type": 10, "content": "## Test"},
                        {"type": 14, "divider": True, "spacing": 1},
                        {
                            "type": 10,
                            "content": (
                                f"So sieht ein Eintrag für **{LOG_CATEGORIES[category]['label']}** aus. "
                                "Diese Nachricht kam aus dem Dashboard."
                            ),
                        },
                    ],
                }],
            }
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.post(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages",
                    headers={"Authorization": f"Bot {settings.bot_token}"}, json=payload,
                )
                response.raise_for_status()
        except Exception:
            return RedirectResponse(href(request, f"/guild/{guild_id}/logging?error=Der+Bot+kann+in+diesen+Kanal+nicht+schreiben"), status_code=303)
        return RedirectResponse(href(request, f"/guild/{guild_id}/logging?tested=1"), status_code=303)

    @app.post("/guild/{guild_id}/{feature}/vorschau")
    async def feature_vorschau(request: Request, guild_id: int, feature: str):
        """Live-Vorschau: rechnet mit dem Entwurf, speichert aber nichts.

        Dieselbe Funktion wie im Bot (``regeln``), damit die Seite nicht etwas
        verspricht, das Discord ablehnt oder der Bot anders schreibt.
        """
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild or feature != "tickets":
            return JSONResponse({"fehler": "Zugriff abgelehnt."}, status_code=403)
        try:
            entwurf = json.loads((await request.body())[:60_000].decode("utf-8", "replace") or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            return JSONResponse({"fehler": "Entwurf konnte nicht gelesen werden."}, status_code=400)
        if not isinstance(entwurf, dict):
            return JSONResponse({"fehler": "Entwurf muss ein Objekt sein."}, status_code=400)
        # Nur lesen, nichts schreiben — und unbekannte Schlüssel bleiben weg.
        # Die Liste im Rückgabewert ist der Hinweis darauf, dass Formular und
        # Regeln auseinandergedriftet sind: ohne sie zeigt die Vorschau still
        # den alten Stand, obwohl jemand etwas getippt hat.
        erlaubt = {key for key, _label, _typ in FEATURES["tickets"]["fields"]}
        unbekannt = sorted(set(entwurf) - erlaubt)
        entwurf = {k: v for k, v in entwurf.items() if k in erlaubt}
        cfg = db.get_feature(guild_id, "tickets", settings)
        antwort = regeln.vorschau_willkommen(cfg, entwurf=entwurf)
        if unbekannt:
            antwort["unbekannte_felder"] = unbekannt[:10]
        return JSONResponse(antwort)

    def _discord_emoji_path(value: str) -> str:
        match = re.fullmatch(r"<a?:([^:>]+):(\d+)>", value.strip())
        return f"{match.group(1)}:{match.group(2)}" if match else value.strip()

    @app.post("/guild/{guild_id}/reaction_roles/settings")
    async def reaction_role_settings(request: Request, guild_id: int):
        user = current_user(request); guild = await guild_access(user, guild_id) if user else None
        if not user or not guild: return JSONResponse({"ok": False}, status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user): return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        db.reaktionsrollen_dm_setzen(guild_id, "dm_enabled" in form, settings)
        return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?saved=1"), status_code=303)

    @app.post("/guild/{guild_id}/reaction_roles/add")
    async def reaction_role_add(request: Request, guild_id: int):
        user = current_user(request); guild = await guild_access(user, guild_id) if user else None
        if not user or not guild: return JSONResponse({"ok": False}, status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user): return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        channel_id = str(form.get("channel_id") or ""); message_id = str(form.get("message_id") or "")
        role_id = str(form.get("role_id") or ""); reaction = str(form.get("emoji") or "").strip()
        if not (channel_id.isdigit() and message_id.isdigit() and role_id.isdigit() and reaction):
            return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?error=Kanal,+Nachrichten-ID,+Emoji+und+Rolle+sind+erforderlich"), status_code=303)
        if len(reaction) > 100 or db.reaktionsrolle(guild_id, int(message_id), reaction, settings):
            return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?error=Dieses+Emoji+ist+auf+der+Nachricht+bereits+vergeben"), status_code=303)
        channels, roles, _stats = await guild_resources(guild_id)
        role = next((item for item in roles if item["id"] == role_id), None)
        if not role or role.get("managed"):
            return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?error=Diese+Rolle+kann+nicht+verwaltet+werden"), status_code=303)
        try:
            bot_member = await _discord_abfrage(settings.bot_token, f"/guilds/{guild_id}/members/{settings.discord_client_id}")
            bot_roles = {str(value) for value in bot_member.get("roles") or []}
            bot_top = max((int(item["position"]) for item in roles if item["id"] in bot_roles), default=0)
            if int(role["position"]) >= bot_top:
                raise ValueError("role hierarchy")
            import httpx
            headers = {"Authorization": f"Bot {settings.bot_token}"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                message = await client.get(f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}", headers=headers)
                if message.status_code == 404: raise LookupError("message")
                message.raise_for_status()
                encoded = quote(_discord_emoji_path(reaction), safe="")
                added = await client.put(f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{encoded}/@me", headers=headers)
                added.raise_for_status()
        except ValueError:
            return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?error=Die+Rolle+muss+unter+der+Bot-Rolle+stehen"), status_code=303)
        except LookupError:
            return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?error=Nachricht+in+diesem+Kanal+nicht+gefunden"), status_code=303)
        except Exception:
            return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?error=Der+Bot+kann+die+Nachricht+nicht+lesen+oder+das+Emoji+nicht+verwenden"), status_code=303)
        db.reaktionsrolle_anlegen(guild_id, int(channel_id), int(message_id), reaction, int(role_id), settings)
        current = db.get_feature(guild_id, "reaction_roles", settings); current["enabled"] = True
        db.set_feature(guild_id, "reaction_roles", current, int(user["uid"]), settings)
        return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?saved=1"), status_code=303)

    @app.post("/guild/{guild_id}/reaction_roles/remove")
    async def reaction_role_remove(request: Request, guild_id: int):
        user = current_user(request); guild = await guild_access(user, guild_id) if user else None
        if not user or not guild: return JSONResponse({"ok": False}, status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user): return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        message_id = str(form.get("message_id") or ""); reaction = str(form.get("emoji") or "")
        mapping = db.reaktionsrolle(guild_id, int(message_id) if message_id.isdigit() else 0, reaction, settings)
        if not mapping: return PlainTextResponse("Eintrag nicht gefunden.", status_code=404)
        try:
            import httpx
            encoded = quote(_discord_emoji_path(reaction), safe="")
            async with httpx.AsyncClient(timeout=15.0) as client:
                await client.delete(f"https://discord.com/api/v10/channels/{mapping['channel_id']}/messages/{message_id}/reactions/{encoded}/@me", headers={"Authorization": f"Bot {settings.bot_token}"})
        except Exception: pass
        db.reaktionsrolle_loeschen(guild_id, int(message_id), reaction, settings)
        return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?saved=1"), status_code=303)

    @app.post("/guild/{guild_id}/reaction_roles/verify")
    async def reaction_roles_verify(request: Request, guild_id: int):
        user = current_user(request); guild = await guild_access(user, guild_id) if user else None
        if not user or not guild: return JSONResponse({"ok": False}, status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user): return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        _channels, roles, _stats = await guild_resources(guild_id); role_ids = {item["id"] for item in roles}
        repaired = 0; problems = []
        try:
            import httpx
            headers = {"Authorization": f"Bot {settings.bot_token}"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                for row in db.reaktionsrollen(guild_id, settings):
                    if str(row["role_id"]) not in role_ids:
                        problems.append(f"{row['emoji']}: Rolle gelöscht"); continue
                    response = await client.get(f"https://discord.com/api/v10/channels/{row['channel_id']}/messages/{row['message_id']}", headers=headers)
                    if response.status_code != 200:
                        problems.append(f"{row['emoji']}: Nachricht nicht gefunden"); continue
                    data = response.json(); wanted = _discord_emoji_path(str(row["emoji"]))
                    present = any((str(item.get("emoji", {}).get("name") or "") + (f":{item['emoji']['id']}" if item.get("emoji", {}).get("id") else "")) == wanted for item in data.get("reactions") or [])
                    if not present:
                        encoded = quote(wanted, safe="")
                        result = await client.put(f"https://discord.com/api/v10/channels/{row['channel_id']}/messages/{row['message_id']}/reactions/{encoded}/@me", headers=headers)
                        if result.status_code < 300: repaired += 1
                        else: problems.append(f"{row['emoji']}: Reaktion konnte nicht gesetzt werden")
        except Exception:
            problems.append("Discord-Prüfung konnte nicht abgeschlossen werden")
        query = f"verified=1&repaired={repaired}" + ("&error=" + quote_plus(" · ".join(problems[:4])) if problems else "")
        return RedirectResponse(href(request, f"/guild/{guild_id}/reaction_roles?{query}"), status_code=303)

    def _automation_text(text: str, guild: dict[str,Any]) -> str:
        from datetime import datetime as _datetime
        values={"server":guild.get("name") or "Server","member_count":guild.get("approximate_member_count") or "—","date":_datetime.now().strftime("%d.%m.%Y"),"time":_datetime.now().strftime("%H:%M"),"user":"@User","user_name":"User","channel":"#kanal"}
        result=str(text or "")
        for key,value in values.items():result=result.replace("{"+key+"}",str(value))
        return result

    def _automation_payload(item: dict[str,Any], guild: dict[str,Any], *, mention: str="") -> dict[str,Any]:
        components=[]
        if mention:components.append({"type":10,"content":mention})
        title=_automation_text(str(item.get("title") or "Automatische Nachricht"),guild);content=_automation_text(str(item.get("content") or item.get("response") or ""),guild)
        components.append({"type":10,"content":f"## {title}\n{content}"[:3900]})
        if item.get("image_url"):components.append({"type":12,"items":[{"media":{"url":str(item["image_url"])}}]})
        try:accent=int(str(item.get("color") or "#5865f2").lstrip("#"),16)
        except ValueError:accent=0x5865F2
        return {"flags":32768,"allowed_mentions":{"parse":[],"roles":[str(item.get("mention_role_id"))] if item.get("mention_role_id") else []},"components":[{"type":17,"accent_color":accent,"components":components}]}

    @app.post("/guild/{guild_id}/automation/save")
    async def automation_save(request:Request,guild_id:int):
        from datetime import datetime as _datetime
        from zoneinfo import ZoneInfo
        user=current_user(request);guild=await guild_access(user,guild_id) if user else None
        if not user or not guild:return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user):return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        kind=str(form.get("kind") or "");data=dict(form);data["enabled"]="enabled" in form
        color=str(form.get("color") or "#5865f2")
        if not COLOR_RE.fullmatch(color):return RedirectResponse(href(request,f"/guild/{guild_id}/automation?tab={kind}&error="+quote_plus("Ungültige Farbe.")),status_code=303)
        image=str(form.get("image_url") or "")
        if image and not image.startswith("https://"):return RedirectResponse(href(request,f"/guild/{guild_id}/automation?tab={kind}&error="+quote_plus("Bild-URLs müssen HTTPS verwenden.")),status_code=303)
        try:
            if kind=="responses":
                if not str(form.get("trigger") or "").strip() or not str(form.get("response") or "").strip():raise ValueError("Trigger und Antwort sind erforderlich.")
                data["exact"]="exact" in form;automation_store.save_response(settings,guild_id,data,int(user["uid"]))
            elif kind=="messages":
                channel=str(form.get("channel_id") or "");channels,_roles,_=await guild_resources(guild_id)
                if channel not in {str(c["id"]) for c in channels}:raise ValueError("Bitte einen gültigen Kanal wählen.")
                raw=str(form.get("send_at") or "");local=_datetime.fromisoformat(raw).replace(tzinfo=ZoneInfo("Europe/Berlin"));data["send_at"]=int(local.timestamp())
                if not str(form.get("content") or "").strip():raise ValueError("Die Nachricht darf nicht leer sein.")
                automation_store.save_message(settings,guild_id,data,int(user["uid"]))
            elif kind=="announcements":
                channel=str(form.get("channel_id") or "");channels,roles,_=await guild_resources(guild_id)
                if channel not in {str(c["id"]) for c in channels}:raise ValueError("Bitte einen gültigen Kanal wählen.")
                role=str(form.get("mention_role_id") or "");data["mention_role_id"]=int(role) if role in {str(r["id"]) for r in roles} else 0
                if not str(form.get("content") or "").strip():raise ValueError("Die Ankündigung darf nicht leer sein.")
                automation_store.save_announcement(settings,guild_id,data,int(user["uid"]))
            else:raise ValueError("Unbekannter Automationstyp.")
        except (ValueError,TypeError) as exc:return RedirectResponse(href(request,f"/guild/{guild_id}/automation?tab={kind}&error="+quote_plus(str(exc))),status_code=303)
        values=db.get_feature(guild_id,"automation",settings);values["enabled"]=True;db.set_feature(guild_id,"automation",values,int(user["uid"]),settings)
        return RedirectResponse(href(request,f"/guild/{guild_id}/automation?tab={kind}&saved=1"),status_code=303)

    @app.post("/guild/{guild_id}/automation/action")
    async def automation_action(request:Request,guild_id:int):
        user=current_user(request);guild=await guild_access(user,guild_id) if user else None
        if not user or not guild:return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user):return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        kind=str(form.get("kind") or "");action=str(form.get("action") or "");item_id=int(form.get("id") or 0)
        if kind not in automation_store.KINDS:return PlainTextResponse("Unbekannter Typ.",status_code=400)
        if action=="delete":automation_store.delete(settings,guild_id,kind,item_id);suffix="deleted=1"
        elif action=="toggle":automation_store.toggle(settings,guild_id,kind,item_id);suffix="saved=1"
        elif action=="test" and kind in {"messages","announcements"}:
            item=automation_store.get(settings,guild_id,kind,item_id)
            if not item:return PlainTextResponse("Eintrag nicht gefunden.",status_code=404)
            import httpx
            mention=f"<@&{item['mention_role_id']}>" if kind=="announcements" and item.get("mention_role_id") else ""
            async with httpx.AsyncClient(timeout=20.0) as client:
                result=await client.post(f"https://discord.com/api/v10/channels/{item['channel_id']}/messages",headers={"Authorization":f"Bot {settings.bot_token}"},json=_automation_payload(item,guild,mention=mention))
            if result.status_code>=300:return RedirectResponse(href(request,f"/guild/{guild_id}/automation?tab={kind}&error="+quote_plus("Testnachricht konnte nicht gesendet werden.")),status_code=303)
            suffix="tested=1"
        else:return PlainTextResponse("Unbekannte Aktion.",status_code=400)
        return RedirectResponse(href(request,f"/guild/{guild_id}/automation?tab={kind}&{suffix}"),status_code=303)

    @app.post("/guild/{guild_id}/custom_commands/save")
    async def custom_command_save(request: Request, guild_id: int):
        user=current_user(request); guild=await guild_access(user,guild_id) if user else None
        if not user or not guild: return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user): return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        name=custom_command_store.normalise_name(form.get("name")); original=custom_command_store.normalise_name(form.get("original_name"))
        use_prefix="use_prefix" in form; use_exact="use_exact" in form; use_contains="use_contains" in form; use_slash="use_slash" in form
        try:
            config=json.loads(str(form.get("config_json") or "{}"))
            config=custom_command_store.validate_config(config)
        except (json.JSONDecodeError,TypeError,ValueError) as exc:
            return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?error="+quote_plus(str(exc))),status_code=303)
        if not custom_command_store.valid_name(name):
            return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?error="+quote_plus("Der Name darf nur Buchstaben, Zahlen, - und _ enthalten (maximal 32).")),status_code=303)
        if not any((use_prefix,use_exact,use_contains,use_slash)):
            return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?error="+quote_plus("Wähle mindestens eine Erkennungsart aus.")),status_code=303)
        if original and original != name:
            return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?error="+quote_plus("Der Name eines bestehenden Commands kann nicht geändert werden.")),status_code=303)
        try:
            global_commands=await _discord_abfrage(settings.bot_token,f"/applications/{settings.discord_client_id}/commands")
            global_names={str(item.get("name") or "").lower() for item in global_commands}
        except Exception: global_names=set()
        existing=custom_command_store.get(settings,guild_id,name)
        if existing is None and ((use_slash and name in global_names) or (use_prefix and name in global_names)):
            return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?error="+quote_plus("Dieser Name gehört bereits zu einem Bot-Befehl.")),status_code=303)
        def first_reply(actions):
            for action in actions:
                if action.get("type")=="reply" and str(action.get("text") or "").strip(): return str(action["text"]).strip()
                nested=first_reply(action.get("then",[]))+first_reply(action.get("else",[]))
                if nested:return nested
                for button in action.get("buttons",[]):
                    nested=first_reply(button.get("actions",[]))
                    if nested:return nested
            return ""
        response=first_reply(config.get("actions",[])) or "Command ausgeführt."
        if len(response)>1900: response=response[:1900]
        feature_values=db.get_feature(guild_id,"custom_commands",settings);premium=bool(feature_values.get("premium",False))
        saved=custom_command_store.save(settings,guild_id,name,response,str(user["uid"]),use_prefix=use_prefix,use_exact=use_exact,use_contains=use_contains,use_slash=use_slash,config=config,max_commands=custom_command_store.PREMIUM_MAX_COMMANDS if premium else custom_command_store.FREE_MAX_COMMANDS)
        if not saved:
            limit=custom_command_store.PREMIUM_MAX_COMMANDS if premium else custom_command_store.FREE_MAX_COMMANDS
            return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?error="+quote_plus(f"Für diesen Server sind höchstens {limit} Custom Commands möglich.")),status_code=303)
        feature_values["enabled"]=True;db.set_feature(guild_id,"custom_commands",feature_values,int(user["uid"]),settings)
        return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?saved=1"),status_code=303)

    @app.post("/guild/{guild_id}/custom_commands/delete")
    async def custom_command_delete(request: Request, guild_id: int):
        user=current_user(request); guild=await guild_access(user,guild_id) if user else None
        if not user or not guild:return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user):return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        name=custom_command_store.normalise_name(form.get("name"))
        if not custom_command_store.delete(settings,guild_id,name):return PlainTextResponse("Custom Command nicht gefunden.",status_code=404)
        return RedirectResponse(href(request,f"/guild/{guild_id}/custom_commands?deleted=1"),status_code=303)

    def _giveaway_discord_payload(record: dict[str, Any], entries: int, *, ended: bool = False, winners: str = "") -> dict[str, Any]:
        values = giveaway_store.values(record, entries)
        title = giveaway_store.fill(record.get("title") or giveaway_store.DEFAULT_TITLE, values)
        body = giveaway_store.fill(record.get("description") or giveaway_store.DEFAULT_DESCRIPTION, values)
        parts = [{"type": 10, "content": f"## {title}"}, {"type": 14, "divider": True, "spacing": 1}, {"type": 10, "content": body}]
        rules = giveaway_store.requirement_lines(record)
        if rules and not ended: parts.append({"type": 10, "content": "**Bedingungen:** " + " · ".join(rules)})
        parts.append({"type": 10, "content": (f"**Gewonnen:** {winners}" if winners else "Niemand hat teilgenommen.") if ended else f"**Teilnehmer:** {entries}"})
        if record.get("image_url"): parts.append({"type": 12, "items": [{"media": {"url": str(record["image_url"])}}]})
        if not ended:
            raw = str(record.get("button_emoji") or "").strip(); emoji = None
            match = re.fullmatch(r"<(a?):([^:>]+):(\d+)>", raw)
            if match: emoji = {"id": match.group(3), "name": match.group(2), "animated": bool(match.group(1))}
            elif raw: emoji = {"name": raw}
            button = {"type": 2, "style": 3, "label": str(record.get("button_label") or "Teilnehmen")[:80], "custom_id": f"giveaway_join_{record['message_id']}"}
            if emoji: button["emoji"] = emoji
            parts.append({"type": 1, "components": [button]})
        return {"flags": 32768, "allowed_mentions": {"parse": []}, "components": [{"type": 17, "accent_color": int(record.get("colour") or 0xF59E0B), "components": parts}]}

    async def _giveaway_patch(record: dict[str, Any], *, ended=False, winners="") -> None:
        import httpx
        payload = _giveaway_discord_payload(record, len(giveaway_store.entries(int(record["message_id"]), settings)), ended=ended, winners=winners)
        async with httpx.AsyncClient(timeout=20.0) as client:
            await client.patch(f"https://discord.com/api/v10/channels/{record['channel_id']}/messages/{record['message_id']}", headers={"Authorization": f"Bot {settings.bot_token}"}, json=payload)

    async def _giveaway_dm(user_id: int, record: dict[str, Any], text: str, kind: str) -> None:
        if not giveaway_store.claim_dm(int(record["message_id"]), user_id, kind, settings): return
        import httpx
        headers={"Authorization": f"Bot {settings.bot_token}"}
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                opened=await client.post("https://discord.com/api/v10/users/@me/channels",headers=headers,json={"recipient_id":str(user_id)})
                opened.raise_for_status(); channel=opened.json()["id"]
                await client.post(f"https://discord.com/api/v10/channels/{channel}/messages",headers=headers,json={"flags":32768,"components":[{"type":17,"accent_color":int(record.get('colour') or 0xF59E0B),"components":[{"type":10,"content":text}]}]})
        except Exception: pass

    async def _giveaway_finish(record: dict[str, Any], reroll: bool = False) -> list[int]:
        message_id=int(record["message_id"])
        if not reroll and not giveaway_store.mark_ended(message_id, settings): return []
        winners=giveaway_store.draw(message_id,int(record.get("winners") or 1),settings,exclude_past=reroll)
        giveaway_store.record_winners(message_id,winners,settings,reroll=reroll)
        mentions=", ".join(f"<@{uid}>" for uid in winners)
        data=giveaway_store.values(record,len(giveaway_store.entries(message_id,settings)),winners_mentions=mentions or "—",server="diesem Server")
        import httpx
        announce=giveaway_store.message(record,"msg_announce" if winners else "msg_no_entries",data)
        async with httpx.AsyncClient(timeout=20.0) as client:
            await client.post(f"https://discord.com/api/v10/channels/{record['channel_id']}/messages",headers={"Authorization":f"Bot {settings.bot_token}"},json={"flags":32768,"allowed_mentions":{"users":[str(u) for u in winners],"parse":[]},"components":[{"type":17,"accent_color":int(record.get('colour') or 0xF59E0B),"components":[{"type":10,"content":announce}]}]})
        if not reroll: await _giveaway_patch(record,ended=True,winners=mentions)
        if record.get("dm_winners"):
            for uid in winners: await _giveaway_dm(uid,record,giveaway_store.message(record,"msg_winner_dm",data),"winner-reroll" if reroll else "winner")
        if record.get("dm_host") and record.get("host_id"):
            await _giveaway_dm(int(record["host_id"]),record,f"**Giveaway beendet**\n\nPreis: **{record['prize']}**\nGewinner: {mentions or 'Niemand'}","host-reroll" if reroll else "host")
        return winners

    @app.post("/guild/{guild_id}/giveaways/create")
    async def giveaway_create(request: Request, guild_id: int):
        user=current_user(request); guild=await guild_access(user,guild_id) if user else None
        if not user or not guild: return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user): return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        channel_id=str(form.get("channel_id") or ""); prize=str(form.get("prize") or "").strip()[:200]
        try: winners=max(1,min(20,int(form.get("winners") or 1))); minutes=max(1,min(86400,int(form.get("duration_minutes") or 60)))
        except ValueError: winners,minutes=1,60
        channels,_roles,_=await guild_resources(guild_id)
        if not prize or not channel_id.isdigit() or channel_id not in {str(c["id"]) for c in channels}: return RedirectResponse(href(request,f"/guild/{guild_id}/giveaways?error="+quote_plus("Bitte Preis und Textkanal auswählen.")),status_code=303)
        payload=dict(form); payload.update({k:k in form for k in giveaway_store.FLAGS}); fields=giveaway_store.clean(payload)
        record={"message_id":0,"guild_id":guild_id,"channel_id":int(channel_id),"prize":prize,"winners":winners,"ends_at":int(time.time())+minutes*60,"status":"active","winner_ids":"[]","host_id":int(user["uid"]),"start_time":int(time.time()),**fields}
        import httpx
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response=await client.post(f"https://discord.com/api/v10/channels/{channel_id}/messages",headers={"Authorization":f"Bot {settings.bot_token}"},json=_giveaway_discord_payload(record,0)); response.raise_for_status(); record["message_id"]=int(response.json()["id"])
            giveaway_store.create(record,settings); await _giveaway_patch(record)
        except Exception: return RedirectResponse(href(request,f"/guild/{guild_id}/giveaways?error="+quote_plus("Nachricht konnte nicht gesendet werden.")),status_code=303)
        return RedirectResponse(href(request,f"/guild/{guild_id}/giveaways/{record['message_id']}?saved=1"),status_code=303)

    @app.get("/guild/{guild_id}/giveaways/{message_id}",response_class=HTMLResponse)
    async def giveaway_detail_page(request:Request,guild_id:int,message_id:int):
        user=current_user(request); guild=await guild_access(user,guild_id) if user else None; record=giveaway_store.get(guild_id,message_id,settings) if guild else None
        if not user or not guild or not record: return RedirectResponse(href(request,f"/guild/{guild_id}/giveaways"),status_code=302)
        channels,roles,_=await guild_resources(guild_id); members=await guild_members(guild_id); member_map={int(m["id"]):m for m in members}; tuning=giveaway_store.boosts(message_id,settings); odds=giveaway_store.chances(message_id,int(record.get("winners") or 1),settings); won=set(giveaway_store.past_winners(message_id,settings))
        with db._gesichert(settings) as conn: joined={int(r["user_id"]):int(r["joined_at"] or 0) for r in conn.execute("SELECT user_id,joined_at FROM giveaway_entries WHERE message_id=?",(message_id,)).fetchall()}
        people=[]
        for uid in set(joined)|set(tuning):
            member=member_map.get(uid,{}); boost=tuning.get(uid,{})
            people.append({"id":uid,"name":member.get("display_name") or member.get("name") or f"Unbekannt ({uid})","avatar":member.get("avatar_url"),"left":not bool(member),"joined_at":joined.get(uid),"not_entered":uid not in joined,"weight":boost.get("weight",1),"guaranteed":boost.get("guaranteed",False),"note":boost.get("note","") ,"chance":round(odds.get(uid,0),2),"won":uid in won})
        people.sort(key=lambda p:(not p["guaranteed"],-p["weight"],-p["chance"]))
        return render(request,"giveaway_detail.html",guild=guild,record=record,channels=channels,roles=roles,people=people,csrf=user["sid"],defaults=giveaway_store.DEFAULT_MESSAGES,saved=request.query_params.get("saved")=="1",error=request.query_params.get("error"))

    @app.post("/guild/{guild_id}/giveaways/{message_id}/update")
    async def giveaway_update(request:Request,guild_id:int,message_id:int):
        user=current_user(request); guild=await guild_access(user,guild_id) if user else None; record=giveaway_store.get(guild_id,message_id,settings) if guild else None
        if not user or not record:return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user):return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        payload=dict(form)
        # Only the text/settings tab owns these switches. Extending time or
        # saving rules must never turn DMs and leaving off by omission.
        if str(form.get("section") or "") == "texts":
            payload.update({k:k in form for k in giveaway_store.FLAGS})
        changes=giveaway_store.clean(payload,partial=True)
        if "prize" in form: changes["prize"]=str(form.get("prize") or "")[:200]
        if "winners" in form:
            try:changes["winners"]=max(1,min(20,int(form["winners"])))
            except:pass
        if "extend_minutes" in form:
            try:changes["ends_at"]=max(int(record["ends_at"]),int(time.time()))+int(form["extend_minutes"])*60; changes["status"]="active"
            except:pass
        fresh=giveaway_store.update(guild_id,message_id,changes,settings); await _giveaway_patch(fresh)
        return RedirectResponse(href(request,f"/guild/{guild_id}/giveaways/{message_id}?saved=1"),status_code=303)

    @app.post("/guild/{guild_id}/giveaways/{message_id}/boost")
    async def giveaway_boost(request:Request,guild_id:int,message_id:int):
        user=current_user(request); guild=await guild_access(user,guild_id) if user else None
        if not user or not guild:return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user):return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        try:giveaway_store.set_boost(message_id,int(form.get("user_id")),str(form.get("mode") or "weight"),int(form.get("weight") or 1),str(form.get("note") or ""),int(user["uid"]),settings)
        except:return PlainTextResponse("Ungültige Chance.",status_code=400)
        return RedirectResponse(href(request,f"/guild/{guild_id}/giveaways/{message_id}?saved=1#entries"),status_code=303)

    @app.post("/guild/{guild_id}/giveaways/{message_id}/action")
    async def giveaway_action(request:Request,guild_id:int,message_id:int):
        user=current_user(request); guild=await guild_access(user,guild_id) if user else None; record=giveaway_store.get(guild_id,message_id,settings) if guild else None
        if not user or not record:return JSONResponse({"ok":False},status_code=403)
        form=await request.form()
        if not csrf_ok(form.get("csrf"),user):return PlainTextResponse("Ungültige Anfrage.",status_code=403)
        action=str(form.get("action") or "")
        if action=="end":await _giveaway_finish(record)
        elif action=="reroll":await _giveaway_finish(record,True)
        elif action=="cancel":giveaway_store.update(guild_id,message_id,{"status":"cancelled"},settings); await _giveaway_patch(record,ended=True,winners="Abgebrochen")
        return RedirectResponse(href(request,f"/guild/{guild_id}/giveaways/{message_id}?saved=1"),status_code=303)

    @app.post("/guild/{guild_id}/moderation/warnung")
    async def warning_add(request: Request, guild_id: int):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild:
            return JSONResponse({"ok": False}, status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        target = str(form.get("user_id") or "").strip()
        grund = str(form.get("reason") or "").strip()
        if not target.isdigit() or not grund:
            return RedirectResponse(href(request, f"/guild/{guild_id}/moderation?error=Mitglied+und+Grund+sind+erforderlich"), status_code=303)
        db.warnung_anlegen(guild_id, int(target), int(user["uid"]), grund[:500], settings)
        return RedirectResponse(href(request, f"/guild/{guild_id}/moderation?added=1"), status_code=303)

    @app.post("/guild/{guild_id}/moderation/warnungen/{user_id}/loeschen")
    async def warnings_clear(request: Request, guild_id: int, user_id: int):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild:
            return JSONResponse({"ok": False}, status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        db.warnungen_loeschen_nutzer(guild_id, user_id, settings)
        return RedirectResponse(href(request, f"/guild/{guild_id}/moderation?geloescht=1"), status_code=303)

    @app.post("/guild/{guild_id}/moderation/warnung/{warnung_id}/loeschen")
    async def warning_delete(request: Request, guild_id: int, warnung_id: int):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild:
            return JSONResponse({"ok": False}, status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        entfernt = db.warnung_loeschen(guild_id, warnung_id, settings)
        if entfernt:
            return RedirectResponse(href(request, f"/guild/{guild_id}/moderation?geloescht=1"), status_code=303)
        return PlainTextResponse("Verwarnung nicht gefunden.", status_code=404)

    @app.get("/admin", response_class=HTMLResponse)
    async def admin(request: Request):
        user = current_user(request)
        if not user:
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response, request)
            return response
        if int(user["uid"]) not in settings.owner_id_set:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        uebersicht = db.konfigurations_uebersicht(settings)
        return render(request, "admin.html",
                      authorized=sorted(settings.allowed_ids),
                      owners=sorted(settings.owner_id_set),
                      freigegebene_server=sorted(settings.allowed_guild_id_set),
                      sitzungen=db.offene_sitzungen(settings),
                      aenderungen=db.letzte_aenderungen(settings, 20),
                      uebersicht=uebersicht,
                      status=bot_status())

    @app.post("/admin/sitzungen/loeschen")
    async def admin_revoke(request: Request):
        user = current_user(request)
        if not user or int(user["uid"]) not in settings.owner_id_set:
            return PlainTextResponse("Zugriff abgelehnt.", status_code=403)
        form = await request.form()
        if not csrf_ok(form.get("csrf"), user):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        anzahl = db.alle_sitzungen_loeschen(settings)
        # Die eigene Sitzung ist damit auch weg: der Hinweis gehoert auf die
        # Login-Seite, sonst landet der Umleitungs-Zielkontakt ohne Sitzung
        # sofort wieder auf der Startseite und die Meldung war nie zu sehen.
        response = RedirectResponse(href(request, f"/Login?abgemeldet={anzahl}"), status_code=303)
        clear_session(response, request)
        return response

    @app.get("/logout")
    async def logout(request: Request):
        response = RedirectResponse(href(request, "/"), status_code=302)
        clear_session(response, request)
        return response

    @app.get("/healthz")
    async def healthz():
        status = bot_status()
        return JSONResponse({
            "ok": True,
            "service": "lbost-shop",
            "oauth_configured": settings.oauth_configured,
            "allowed_accounts": len(settings.allowed_ids),
            "bot_token_configured": bool(settings.bot_token),
            "bot_online": status["online"],
            "bot_letzte_meldung": status["vor"],
        })

    return app


app = create_app()
