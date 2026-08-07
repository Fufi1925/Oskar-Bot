from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import auth, db as dbmod
from app.config import get_settings

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))


def render(request: Request, template_name: str, context: dict[str, Any]) -> HTMLResponse:
    """Jinja render helper — avoids Starlette TemplateResponse arg quirks."""
    template = TEMPLATES.env.get_template(template_name)
    html = template.render(context)
    return HTMLResponse(html)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    app.state.db = await dbmod.connect()
    yield
    await app.state.db.close()


def create_app() -> FastAPI:
    settings = get_settings()
    # When mounted under parent FastAPI at /phantom, leave FastAPI root_path empty.
    # Link prefix still comes from PHANTOM_BASE_URL for templates/cookies/OAuth.
    _mount_mode = True  # always mounted in University stack; standalone run_dashboard wraps mount
    app = FastAPI(
        title="Phantom Dashboard",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        # root_path lets reverse-proxies mount under /phantom
        root_path="",
    )

    app.mount(
        "/static",
        StaticFiles(directory=str(APP_DIR / "static")),
        name="static",
    )

    def _href(path: str) -> str:
        """Build absolute site path under /phantom prefix."""
        prefix = (settings.root_path or "").rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return f"{prefix}{path}" if prefix else path

    def ctx(request: Request, **extra: Any) -> dict[str, Any]:
        s = get_settings()
        user = auth.get_session_user(request)
        base = {
            "request": request,
            "brand": s.phantom_brand_name,
            "footer": s.phantom_footer,
            "base_url": s.base_url,
            "root_path": s.root_path or "",
            "user": user,
            "avatar_url": (
                auth.avatar_url(user["uid"], user.get("avatar")) if user else None
            ),
            "flash": request.cookies.get("phantom_flash"),
        }
        base.update(extra)
        return base

    def set_flash(response: Response, message: str) -> None:
        s = get_settings()
        response.set_cookie(
            "phantom_flash",
            message[:180],
            max_age=20,
            path=s.phantom_cookie_path,
            httponly=False,
            samesite="lax",
        )

    def clear_flash(response: Response) -> None:
        s = get_settings()
        response.delete_cookie("phantom_flash", path=s.phantom_cookie_path)

    # ── Pages ──────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        user = auth.get_session_user(request)
        if user:
            return RedirectResponse(url=_href("/dashboard"), status_code=302)
        return RedirectResponse(url=_href("/login"), status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        s = get_settings()
        user = auth.get_session_user(request)
        if user:
            return RedirectResponse(url=_href("/dashboard"), status_code=302)
        missing = []
        if not s.phantom_discord_client_id:
            missing.append("PHANTOM_DISCORD_CLIENT_ID")
        if not s.phantom_discord_client_secret:
            missing.append("PHANTOM_DISCORD_CLIENT_SECRET")
        resp = render(request, "login.html", ctx(request, missing=missing, redirect_uri=s.oauth_redirect_uri))
        clear_flash(resp)
        return resp

    @app.get("/auth/discord")
    async def auth_discord(request: Request, force: int = 0):
        s = get_settings()
        if not s.phantom_discord_client_id or not s.phantom_discord_client_secret:
            return RedirectResponse(url=_href("/login"), status_code=302)
        state = auth.make_oauth_state()
        url = (
            auth.oauth_authorize_url_force(state, s)
            if force
            else auth.oauth_authorize_url(state, s)
        )
        resp = RedirectResponse(url=url, status_code=302)
        resp.set_cookie(
            "phantom_oauth_state",
            state,
            max_age=600,
            path=s.phantom_cookie_path,
            httponly=True,
            samesite="lax",
        )
        return resp

    @app.get("/auth/callback")
    async def auth_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ):
        s = get_settings()
        if error:
            resp = RedirectResponse(url=_href("/login"), status_code=302)
            set_flash(resp, f"Discord Login abgebrochen: {error}")
            return resp
        expected = request.cookies.get("phantom_oauth_state")
        if not code or not state or not expected or state != expected:
            resp = RedirectResponse(url=_href("/login"), status_code=302)
            set_flash(resp, "Ungültiger OAuth-State. Bitte erneut anmelden.")
            return resp

        try:
            token_data = await auth.exchange_code(code, s)
            access = token_data.get("access_token")
            if not access:
                raise HTTPException(status_code=400, detail="no_access_token")
            duser = await auth.fetch_discord_user(access)
            expires_in = int(token_data.get("expires_in") or 0)
            import time as _t

            await dbmod.upsert_user(
                request.app.state.db,
                user_id=int(duser["id"]),
                username=duser.get("username") or "user",
                global_name=duser.get("global_name"),
                avatar=duser.get("avatar"),
                access_token=access,
                refresh_token=token_data.get("refresh_token"),
                token_expires_at=int(_t.time()) + expires_in if expires_in else None,
            )
            session = auth.create_session_token(duser, s)
        except HTTPException as e:
            resp = RedirectResponse(url=_href("/login"), status_code=302)
            set_flash(resp, f"Login fehlgeschlagen ({e.detail}).")
            return resp
        except Exception as e:
            resp = RedirectResponse(url=_href("/login"), status_code=302)
            set_flash(resp, f"Login Fehler: {type(e).__name__}")
            return resp

        resp = RedirectResponse(url=_href("/dashboard"), status_code=302)
        resp.set_cookie(
            s.phantom_cookie_name,
            session,
            max_age=s.phantom_session_max_age,
            path=s.phantom_cookie_path,
            httponly=True,
            samesite="lax",
        )
        resp.delete_cookie("phantom_oauth_state", path=s.phantom_cookie_path)
        set_flash(resp, "Erfolgreich angemeldet.")
        return resp

    @app.get("/auth/logout")
    async def logout():
        s = get_settings()
        resp = RedirectResponse(url=_href("/login"), status_code=302)
        resp.delete_cookie(s.phantom_cookie_name, path=s.phantom_cookie_path)
        set_flash(resp, "Abgemeldet.")
        return resp

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_home(request: Request):
        user = auth.get_session_user(request)
        if not user:
            return RedirectResponse(url=_href("/login"), status_code=302)

        # load guilds via stored access token
        db = request.app.state.db
        row = await dbmod.get_user(db, int(user["uid"]))
        guilds: list[dict[str, Any]] = []
        if row and row.get("access_token"):
            raw = await auth.fetch_user_guilds(row["access_token"])
            for g in raw:
                if auth.can_manage_guild(g):
                    guilds.append(g)
            guilds.sort(key=lambda x: (x.get("name") or "").lower())

        resp = render(request, "dashboard.html", ctx(request, guilds=guilds, page="home"))
        clear_flash(resp)
        return resp

    @app.get("/dashboard/guild/{guild_id}", response_class=HTMLResponse)
    async def dashboard_guild(request: Request, guild_id: int):
        user = auth.get_session_user(request)
        if not user:
            return RedirectResponse(url=_href("/login"), status_code=302)

        db = request.app.state.db
        row = await dbmod.get_user(db, int(user["uid"]))
        guild = None
        if row and row.get("access_token"):
            for g in await auth.fetch_user_guilds(row["access_token"]):
                if int(g.get("id") or 0) == guild_id and auth.can_manage_guild(g):
                    guild = g
                    break
        if not guild:
            resp = RedirectResponse(url=_href("/dashboard"), status_code=302)
            set_flash(resp, "Kein Zugriff auf diesen Server.")
            return resp

        config = await dbmod.get_guild_config(db, guild_id)
        tickets = await dbmod.list_open_tickets(db, guild_id)
        resp = render(request, "guild.html", ctx(
                request,
                page="guild",
                guild=guild,
                config=config,
                tickets=tickets,
                staff_role_ids_json=json.dumps(config.get("staff_role_ids") or [])),
        )
        clear_flash(resp)
        return resp

    @app.post("/dashboard/guild/{guild_id}/save")
    async def save_guild(
        request: Request,
        guild_id: int,
        panel_title: str = Form("Support Center"),
        panel_description: str = Form(""),
        panel_channel_id: str = Form(""),
        log_channel_id: str = Form(""),
        staff_role_ids: str = Form("[]"),
    ):
        user = auth.get_session_user(request)
        if not user:
            return RedirectResponse(url=_href("/login"), status_code=302)

        def _parse_id(raw: str) -> int | None:
            raw = (raw or "").strip()
            if raw.isdigit():
                return int(raw)
            return None

        try:
            roles = json.loads(staff_role_ids or "[]")
            if not isinstance(roles, list):
                roles = []
            roles = [int(x) for x in roles if str(x).isdigit()]
        except Exception:
            roles = []

        await dbmod.save_guild_config(
            request.app.state.db,
            guild_id,
            panel_channel_id=_parse_id(panel_channel_id),
            log_channel_id=_parse_id(log_channel_id),
            staff_role_ids=roles,
            panel_title=panel_title.strip()[:120] or "Support Center",
            panel_description=panel_description.strip()[:1800]
            or "Klicke auf den Button, um ein Ticket zu öffnen.",
        )
        resp = RedirectResponse(url=_href(f"/dashboard/guild/{guild_id}"), status_code=302)
        set_flash(resp, "Einstellungen gespeichert.")
        return resp

    # ── JSON API (nur Phantom, für Bot + Dashboard) ────────

    @app.get("/api/health")
    async def api_health():
        s = get_settings()
        return {
            "ok": True,
            "service": "phantom",
            "brand": s.phantom_brand_name,
            "base_url": s.base_url,
        }

    @app.get("/api/me")
    async def api_me(request: Request):
        user = auth.require_session_user(request)
        return {"user": user}

    @app.get("/api/guilds/{guild_id}/config")
    async def api_guild_config(request: Request, guild_id: int):
        # Bot auth via header OR logged-in dashboard user
        s = get_settings()
        bot_key = request.headers.get("X-Phantom-Bot-Token")
        if bot_key and s.phantom_bot_token and bot_key == s.phantom_bot_token:
            pass
        else:
            auth.require_session_user(request)
        cfg = await dbmod.get_guild_config(request.app.state.db, guild_id)
        return {"config": cfg}

    @app.get("/api/guilds/{guild_id}/tickets")
    async def api_guild_tickets(request: Request, guild_id: int):
        s = get_settings()
        bot_key = request.headers.get("X-Phantom-Bot-Token")
        if not (bot_key and s.phantom_bot_token and bot_key == s.phantom_bot_token):
            auth.require_session_user(request)
        tickets = await dbmod.list_open_tickets(request.app.state.db, guild_id)
        return {"tickets": tickets}

    @app.post("/api/internal/tickets/register")
    async def api_register_ticket(request: Request):
        """Nur Phantom-Bot."""
        s = get_settings()
        bot_key = request.headers.get("X-Phantom-Bot-Token")
        if not (bot_key and s.phantom_bot_token and bot_key == s.phantom_bot_token):
            raise HTTPException(status_code=401, detail="bot_only")
        body = await request.json()
        await dbmod.register_ticket(
            request.app.state.db,
            channel_id=int(body["channel_id"]),
            guild_id=int(body["guild_id"]),
            owner_id=int(body["owner_id"]),
            category=str(body.get("category") or "support"),
        )
        return {"ok": True}

    @app.post("/api/internal/tickets/{channel_id}/claim")
    async def api_claim_ticket(request: Request, channel_id: int):
        s = get_settings()
        bot_key = request.headers.get("X-Phantom-Bot-Token")
        if not (bot_key and s.phantom_bot_token and bot_key == s.phantom_bot_token):
            raise HTTPException(status_code=401, detail="bot_only")
        body = await request.json()
        claimed_by = body.get("claimed_by")
        await dbmod.set_ticket_claim(
            request.app.state.db,
            channel_id,
            int(claimed_by) if claimed_by is not None else None,
        )
        return {"ok": True}

    @app.delete("/api/internal/tickets/{channel_id}")
    async def api_delete_ticket(request: Request, channel_id: int):
        s = get_settings()
        bot_key = request.headers.get("X-Phantom-Bot-Token")
        if not (bot_key and s.phantom_bot_token and bot_key == s.phantom_bot_token):
            raise HTTPException(status_code=401, detail="bot_only")
        await dbmod.delete_ticket(request.app.state.db, channel_id)
        return {"ok": True}

    @app.get("/api/internal/guilds/{guild_id}/config")
    async def api_bot_guild_config(request: Request, guild_id: int):
        s = get_settings()
        bot_key = request.headers.get("X-Phantom-Bot-Token")
        if not (bot_key and s.phantom_bot_token and bot_key == s.phantom_bot_token):
            raise HTTPException(status_code=401, detail="bot_only")
        cfg = await dbmod.get_guild_config(request.app.state.db, guild_id)
        return {"config": cfg}

    return app


app = create_app()
