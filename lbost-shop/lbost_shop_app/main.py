"""Isolated LBoost Shop landing page, Discord login and dashboard.

Der Bereich läuft bewusst eigenständig: eigene Discord-App, eigene Sitzung,
eigene Datenbank, eigener Bot-Prozess. Er teilt nichts mit University Bot,
Phantom oder Louckup außer der Optik und den Regeln für Tickettexte (die
liegen in ``regeln.py`` und gelten für Vorschau und Bot gleichzeitig).
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lbost_shop_app import auth, db, regeln
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
        ("enabled", "Aktiviert", "bool"), ("log_channel_id", "Moderations-Log", "channel"),
        ("anti_spam", "Anti-Spam", "bool"), ("spam_limit", "Nachrichten je 8 Sekunden", "number"),
        ("spam_timeout", "Timeout bei Spam", "bool"),
        ("anti_links", "Anti-Link", "bool"), ("allowed_domains", "Erlaubte Domains (Komma)", "text"),
        ("link_timeout", "Timeout bei fremdem Link", "bool"),
        ("spam_timeout_minuten", "Timeout-Dauer (Minuten)", "number"),
        ("exempt_role_ids", "Ausgenommene Rollen (IDs, Komma)", "text"),
    ]},
    "welcome": {"title": "Welcome & Leave", "icon": "users", "fields": [
        ("enabled", "Aktiviert", "bool"), ("welcome_channel_id", "Willkommenskanal", "channel"),
        ("welcome_message", "Willkommenstext", "textarea"), ("welcome_image_url", "Willkommensbild", "url"),
        ("color", "Farbe", "color"),
        ("leave_enabled", "Leave-Nachrichten", "bool"), ("leave_channel_id", "Leave-Kanal", "channel"),
        ("leave_message", "Leave-Text", "textarea"), ("leave_image_url", "Leave-Bild", "url"),
    ]},
    "reaction_roles": {"title": "Reaction Roles", "icon": "users", "fields": [
        ("enabled", "Aktiviert", "bool"), ("channel_id", "Panel-Kanal", "channel"),
        ("title", "Panel-Titel", "text"), ("description", "Panel-Beschreibung", "textarea"),
        ("color", "Farbe", "color"),
        ("roles_json", "Rollen-Buttons (JSON)", "json"), ("panels_json", "Weitere Panels (JSON)", "json"),
    ]},
    "automation": {"title": "Automation", "icon": "bolt", "fields": [
        ("enabled", "Aktiviert", "bool"), ("auto_responses_json", "Auto-Antworten (JSON)", "json"),
        ("custom_commands_json", "Eigene Befehle (JSON)", "json"),
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
            values[key] = raw[:4000]
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
            return {"online": False, "vor": None, "gilden": 0, "name": "", "token": bool(settings.bot_token)}
        vor = int(time.time()) - int(wert.get("zeit") or 0)
        return {
            "online": vor <= 90,
            "vor": vor,
            "gilden": int(wert.get("gilden") or 0),
            "name": str(wert.get("name") or ""),
            "token": bool(settings.bot_token),
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
