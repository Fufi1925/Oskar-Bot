"""Isolated LBoost Shop landing page, Discord login and placeholder dashboard."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from lbost_shop_app import auth
from lbost_shop_app.config import get_settings

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))
_rate: dict[str, list[float]] = {}

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

    def clear_session(response: RedirectResponse) -> None:
        response.delete_cookie(settings.cookie_name, path=settings.cookie_path)
        response.delete_cookie("lbost_shop_oauth_state", path=settings.cookie_path)

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
        if not settings.oauth_configured:
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
            clear_session(response)
            return response
        try:
            token = await auth.exchange(code, settings)
            user = await auth.discord_user(str(token.get("access_token") or ""))
            user_id = int(user["id"])
        except Exception:
            response = RedirectResponse(href(request, "/Login"), status_code=302)
            clear_session(response)
            return response

        # Fail closed: explicit shop IDs plus University owner IDs only.
        if user_id not in settings.allowed_ids:
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response)
            return response

        response = RedirectResponse(href(request, "/auth/success"), status_code=302)
        response.set_cookie(settings.cookie_name, auth.create_session(user, settings), max_age=settings.session_max_age, path=settings.cookie_path, httponly=True, samesite="lax", secure=secure(request))
        response.delete_cookie("lbost_shop_oauth_state", path=settings.cookie_path)
        return response

    @app.get("/auth/success", response_class=HTMLResponse)
    async def login_success(request: Request):
        if not current_user(request):
            response = RedirectResponse(settings.fallback_url or "/", status_code=302)
            clear_session(response)
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
            clear_session(response)
            return response
        return render(request, "dashboard.html")

    @app.get("/logout")
    async def logout(request: Request):
        response = RedirectResponse(href(request, "/"), status_code=302)
        clear_session(response)
        return response

    @app.get("/healthz")
    async def healthz():
        return JSONResponse({"ok": True, "service": "lbost-shop", "oauth_configured": settings.oauth_configured, "allowed_accounts": len(settings.allowed_ids), "bot_token_configured": bool(settings.bot_token)})

    return app


app = create_app()
