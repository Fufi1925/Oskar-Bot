"""Isolated LBoost Shop landing page, Discord login and placeholder dashboard."""
from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lbost_shop_app import auth, db
from lbost_shop_app.config import get_settings

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))
_rate: dict[str, list[float]] = {}

FEATURES: dict[str, dict[str, Any]] = {
    "tickets": {"title": "Advanced Ticket System", "icon": "🎫", "fields": [
        ("enabled", "Aktiviert", "bool"), ("panel_channel_id", "Panel-Kanal", "channel"),
        ("category_id", "Ticket-Kategorie", "channel"), ("log_channel_id", "Transkript-/Log-Kanal", "channel"),
        ("support_role_ids", "Support-Rollen (IDs, Komma)", "text"),
        ("open_role_ids", "Darf Tickets öffnen (Rollen-IDs, leer = alle)", "text"), ("button_label", "Öffnen-Button", "text"),
        ("button_emoji", "Öffnen-Emoji", "text"), ("claim_label", "Übernehmen-Button", "text"),
        ("claim_emoji", "Übernehmen-Emoji", "text"), ("close_label", "Schließen-Button", "text"),
        ("close_emoji", "Schließen-Emoji", "text"), ("delete_label", "Löschen-Button", "text"),
        ("delete_emoji", "Löschen-Emoji", "text"),
        ("title", "Embed-Titel", "text"),
        ("description", "Beschreibung", "textarea"), ("footer", "Footer", "text"),
        ("color", "Farbe", "color"), ("image_url", "Bild-URL", "url"), ("thumbnail_url", "Thumbnail-URL", "url"),
        ("panels_json", "Weitere Panels (JSON)", "json"),
    ]},
    "moderation": {"title": "Moderation", "icon": "🛡️", "fields": [
        ("enabled", "Aktiviert", "bool"), ("log_channel_id", "Moderations-Log", "channel"),
        ("anti_spam", "Anti-Spam", "bool"), ("spam_limit", "Nachrichten je 8 Sekunden", "number"),
        ("anti_links", "Anti-Link", "bool"), ("allowed_domains", "Erlaubte Domains (Komma)", "text"),
        ("exempt_role_ids", "Ausgenommene Rollen (IDs, Komma)", "text"),
    ]},
    "welcome": {"title": "Welcome & Leave", "icon": "👋", "fields": [
        ("enabled", "Aktiviert", "bool"), ("welcome_channel_id", "Willkommenskanal", "channel"),
        ("welcome_message", "Willkommenstext", "textarea"), ("welcome_image_url", "Willkommensbild", "url"),
        ("leave_enabled", "Leave-Nachrichten", "bool"), ("leave_channel_id", "Leave-Kanal", "channel"),
        ("leave_message", "Leave-Text", "textarea"), ("leave_image_url", "Leave-Bild", "url"),
    ]},
    "reaction_roles": {"title": "Reaction Roles", "icon": "🎭", "fields": [
        ("enabled", "Aktiviert", "bool"), ("channel_id", "Panel-Kanal", "channel"),
        ("title", "Panel-Titel", "text"), ("description", "Panel-Beschreibung", "textarea"),
        ("roles_json", "Rollen-Buttons (JSON)", "json"), ("panels_json", "Weitere Panels (JSON)", "json"),
    ]},
    "automation": {"title": "Automation", "icon": "📢", "fields": [
        ("enabled", "Aktiviert", "bool"), ("auto_responses_json", "Auto-Antworten (JSON)", "json"),
        ("custom_commands_json", "Eigene Befehle (JSON)", "json"),
        ("announcements_json", "Automatische Nachrichten (JSON)", "json"),
    ]},
    "logging": {"title": "Logging", "icon": "📊", "fields": [
        ("enabled", "Aktiviert", "bool"), ("channel_id", "Log-Kanal", "channel"),
        ("member_logs", "Mitglieder-Logs", "bool"), ("message_logs", "Nachrichten-Logs", "bool"),
        ("moderation_logs", "Moderations-Logs", "bool"), ("role_channel_logs", "Rollen-/Kanal-Logs", "bool"),
        ("ticket_logs", "Ticket-Logs", "bool"),
    ]},
    "giveaways": {"title": "Giveaways", "icon": "🎁", "fields": [
        ("enabled", "Aktiviert", "bool"), ("log_channel_id", "Giveaway-Log", "channel"),
        ("manager_role_ids", "Manager-Rollen (IDs, Komma)", "text"),
        ("default_winners", "Standard-Anzahl Gewinner", "number"),
    ]},
}

JSON_HELP: dict[str, dict[str, str]] = {
    "tickets": {"panels_json": '[{"key":"billing","title":"Billing Support","panel_channel_id":"123","category_id":"456","support_role_ids":"789","button_label":"Billing-Ticket"}]'},
    "reaction_roles": {
        "roles_json": '[{"role_id":"123","label":"Updates","emoji":"<:bell:123456>"}]',
        "panels_json": '[{"title":"Game Roles","channel_id":"123","roles_json":[{"role_id":"456","label":"Player"}]}]',
    },
    "automation": {
        "auto_responses_json": '[{"trigger":"hello","response":"Welcome!","exact":false}]',
        "custom_commands_json": '[{"name":"rules","title":"Rules","response":"Read the server rules."}]',
        "announcements_json": '[{"channel_id":"123","title":"News","content":"Automatic update","interval_minutes":1440}]',
    },
}

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' https://cdn.discordapp.com; style-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="LBoost Shop", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

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

    def context(request: Request, **extra: Any) -> dict[str, Any]:
        user = current_user(request)
        data = {
            "request": request,
            "brand": settings.brand_name,
            "root_path": prefix(request),
            "user": user,
            "avatar_url": auth.avatar_url(user),
            "missing": settings.missing_config,
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

    async def visible_guilds(user: dict[str, Any]) -> list[dict[str, Any]]:
        """Strict intersection: allowlist + bot present + Manage Guild rights."""
        session_id = str(user["sid"])
        user_id = int(user["uid"])
        stored = db.load_oauth_session(session_id, user_id, settings)
        if not stored or not settings.bot_token or not settings.allowed_guild_id_set:
            return []
        try:
            if int(stored["expires_at"]) <= int(time.time()) + 60:
                refreshed = await auth.refresh(str(stored["refresh_token"]), settings)
                if not refreshed.get("refresh_token"):
                    refreshed["refresh_token"] = stored["refresh_token"]
                db.save_oauth_session(session_id, user_id, refreshed, settings)
                access_token = str(refreshed["access_token"])
            else:
                access_token = str(stored["access_token"])

            user_guilds = await auth.guilds(access_token)
            bot_guilds = await auth.guilds(settings.bot_token, "Bot")
        except Exception:
            # Never leak a guild from stale/cache data when Discord cannot be checked.
            return []

        bot_ids = {int(g["id"]) for g in bot_guilds if str(g.get("id", "")).isdigit()}
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
            visible.append({
                "id": str(guild_id),
                "name": str(guild.get("name") or "Unbenannter Server"),
                "icon_url": f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.png?size=128" if icon_hash else None,
            })
        return sorted(visible, key=lambda guild: guild["name"].casefold())

    async def guild_access(user: dict[str, Any], guild_id: int) -> dict[str, Any] | None:
        return next((guild for guild in await visible_guilds(user) if int(guild["id"]) == guild_id), None)

    async def guild_resources(guild_id: int) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Channels and roles for friendly dashboard selectors; fail closed."""
        try:
            import httpx
            headers = {"Authorization": f"Bot {settings.bot_token}"}
            async with httpx.AsyncClient(timeout=20.0) as client:
                channels_response = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/channels", headers=headers)
                roles_response = await client.get(f"https://discord.com/api/v10/guilds/{guild_id}/roles", headers=headers)
                channels_response.raise_for_status()
                roles_response.raise_for_status()
            channels = [
                {"id": str(item["id"]), "name": str(item.get("name") or item["id"])}
                for item in channels_response.json() if item.get("type") in (0, 4, 5, 10, 11, 12, 15, 16)
            ]
            roles = [
                {"id": str(item["id"]), "name": str(item.get("name") or item["id"])}
                for item in roles_response.json() if str(item.get("id")) != str(guild_id)
            ]
            return channels, roles
        except Exception:
            return [], []

    @app.middleware("http")
    async def harden(request: Request, call_next):
        response = await call_next(request)
        for key, value in SECURITY_HEADERS.items():
            response.headers.setdefault(key, value)
        if (response.headers.get("content-type") or "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-store, private"
        return response

    @app.get("/", response_class=HTMLResponse)
    async def landing(request: Request):
        return render(request, "landing.html")

    @app.get("/Login", response_class=HTMLResponse)
    async def login(request: Request):
        if current_user(request):
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        return render(request, "login.html", redirect_uri=settings.oauth_redirect_uri)

    @app.get("/login", include_in_schema=False)
    async def login_lower(request: Request):
        return RedirectResponse(href(request, "/Login"), status_code=307)

    @app.get("/auth/discord")
    async def auth_discord(request: Request):
        ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()
        now = time.time()
        hits = [stamp for stamp in _rate.get(ip, []) if now - stamp < 60]
        hits.append(now)
        _rate[ip] = hits
        if len(hits) > settings.login_rate_limit:
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
    @app.get("/servers", response_class=HTMLResponse)
    async def dashboard(request: Request):
        user = current_user(request)
        if not user:
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response, request)
            return response
        guilds = await visible_guilds(user)
        return render(request, "dashboard.html", guilds=guilds)

    @app.get("/guild/{guild_id}", response_class=HTMLResponse)
    async def guild_home(request: Request, guild_id: int):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        if not user or not guild:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        configured = db.all_features(guild_id, settings)
        return render(request, "guild.html", guild=guild, features=FEATURES, configured=configured)

    @app.get("/guild/{guild_id}/{feature}", response_class=HTMLResponse)
    async def feature_page(request: Request, guild_id: int, feature: str):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        spec = FEATURES.get(feature)
        if not user or not guild or not spec:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        channels, roles = await guild_resources(guild_id)
        values = db.get_feature(guild_id, feature, settings)
        return render(request, "feature.html", guild=guild, feature=feature, spec=spec, values=values, channels=channels, roles=roles, csrf=user["sid"], saved=request.query_params.get("saved") == "1", error=None, json_help=JSON_HELP.get(feature, {}))

    @app.post("/guild/{guild_id}/{feature}", response_class=HTMLResponse)
    async def save_feature(request: Request, guild_id: int, feature: str):
        user = current_user(request)
        guild = await guild_access(user, guild_id) if user else None
        spec = FEATURES.get(feature)
        if not user or not guild or not spec:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        form = await request.form()
        if not secrets.compare_digest(str(form.get("csrf") or ""), str(user["sid"])):
            return PlainTextResponse("Ungültige Anfrage.", status_code=403)
        values: dict[str, Any] = {}
        error: str | None = None
        for key, _label, field_type in spec["fields"]:
            raw = str(form.get(key) or "").strip()
            if field_type == "bool":
                values[key] = key in form
            elif field_type == "number":
                try:
                    values[key] = max(1, min(1000, int(raw or "1")))
                except ValueError:
                    error = f"Ungültige Zahl bei {key}."
            elif field_type == "json":
                try:
                    parsed = json.loads(raw or "[]")
                    if not isinstance(parsed, (list, dict)):
                        raise ValueError
                    values[key] = parsed
                except (TypeError, ValueError, json.JSONDecodeError):
                    error = f"Ungültiges JSON bei {key}."
            else:
                values[key] = raw[:4000]
        if error:
            channels, roles = await guild_resources(guild_id)
            return render(request, "feature.html", guild=guild, feature=feature, spec=spec, values=values, channels=channels, roles=roles, csrf=user["sid"], saved=False, error=error, json_help=JSON_HELP.get(feature, {}))
        db.set_feature(guild_id, feature, values, int(user["uid"]), settings)
        return RedirectResponse(href(request, f"/guild/{guild_id}/{feature}?saved=1"), status_code=303)

    @app.get("/admin", response_class=HTMLResponse)
    async def admin(request: Request):
        user = current_user(request)
        if not user:
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response, request)
            return response
        if int(user["uid"]) not in settings.owner_id_set:
            return RedirectResponse(href(request, "/dashboard"), status_code=302)
        return render(request, "admin.html")

    @app.get("/logout")
    async def logout(request: Request):
        response = RedirectResponse(href(request, "/"), status_code=302)
        clear_session(response, request)
        return response

    @app.get("/healthz")
    async def healthz():
        return JSONResponse({"ok": True, "service": "lbost-shop", "oauth_configured": settings.oauth_configured, "allowed_accounts": len(settings.allowed_ids), "bot_token_configured": bool(settings.bot_token)})

    return app


app = create_app()
