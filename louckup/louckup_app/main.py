"""Louckup — die App.

Ablauf, wie besprochen:

    <url>/louckup              -> Loginseite (Knopf „Mit Discord anmelden")
    <url>/louckup/auth/...     -> OAuth2 mit identify, email, guilds,
                                  guilds.join, gdm.join
    danach:
      Owner  -> <url>/louckup/dashboard  (Reiter: Discord IDs,
                Roblox User, IP, Self)
      sonst  -> sofort weiter auf <url>/  (das normale Dashboard),
                ohne Session-Cookie

Der Bereich ist gemountet, nicht eingebunden: er importiert nichts aus
`phantom`, `bot` oder `dashboard` und hat seine eigene Datenbank.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from louckup_app import auth, db as dbmod
from louckup_app.config import get_settings

log = logging.getLogger("louckup")

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))


def _format_timestamp(ts: int | None) -> str:
    if not ts:
        return "—"
    try:
        from datetime import datetime

        return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ts)


TEMPLATES.env.filters["timestamp"] = _format_timestamp

# Modul-globale Verbindung: bei einem Mount ist `request.app` die
# Eltern-App, `app.state` der Unter-App also nicht verlässlich.
_db_conn = None
_db_lock = None


async def get_db():
    """Lazy geteilte SQLite-Verbindung für Louckup."""
    global _db_conn, _db_lock
    import asyncio

    if _db_lock is None:
        _db_lock = asyncio.Lock()
    async with _db_lock:
        if _db_conn is None:
            try:
                get_settings().db_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            _db_conn = await dbmod.connect()
            log.info("Louckup DB ready at %s", get_settings().db_path)
        return _db_conn


def render(request: Request, template_name: str, context: dict[str, Any]) -> HTMLResponse:
    return HTMLResponse(TEMPLATES.env.get_template(template_name).render(context))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await get_db()
    except Exception as exc:  # nie den Start des Hauptbots blockieren
        log.error("Louckup DB init failed: %s", exc)
    yield
    global _db_conn
    if _db_conn is not None:
        try:
            await _db_conn.close()
        except Exception:
            pass
        _db_conn = None


# Anfaenge von Logins pro Adresse. Bewusst im Speicher und bewusst
# einfach: es geht nicht darum, einen Angriff von tausend Rechnern
# abzuwehren, sondern darum, dass ein einzelner Rechner den Bereich
# nicht mit Login-Anfragen zuschuettet.
_rate: dict[str, list[float]] = {}


def rate_ok(key: str, limit: int, window: float = 60.0) -> bool:
    """True, wenn noch innerhalb des Limits."""
    jetzt = time.time()
    treffer = [t for t in _rate.get(key, []) if jetzt - t < window]
    treffer.append(jetzt)
    _rate[key] = treffer

    # Aufraeumen kostet Zeit, also nicht bei jedem Aufruf, sondern nur
    # wenn die Kiste unuebersichtlich wird.
    if len(_rate) > 512:
        for k in [k for k, v in _rate.items() if not v or jetzt - v[-1] > window]:
            _rate.pop(k, None)

    return len(treffer) <= limit


# Der Bereich kennt keine eingebetteten Skripte und kein fremdes CSS,
# deshalb darf die Richtlinie so eng sein. Bilder kommen nur von Discord.
SICHERHEITS_HEADER = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' https://cdn.discordapp.com; "
        "style-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'none'"
    ),
}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Louckup",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        root_path="",
    )

    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.middleware("http")
    async def sicherheits_header(request: Request, call_next):
        antwort = await call_next(request)
        for name, wert in SICHERHEITS_HEADER.items():
            antwort.headers.setdefault(name, wert)
        # Keine Seite hier darf im Browser-Cache landen, schon gar nicht
        # auf einem geteilten Rechner.
        if (antwort.headers.get("content-type") or "").startswith("text/html"):
            antwort.headers["Cache-Control"] = "no-store, private"
        return antwort

    # ── Helfer ────────────────────────────────────────────────────

    def prefix(request: Request | None = None) -> str:
        """Mount-Pfad, z. B. "/louckup".

        Der Root-Path, den Starlette beim Mounten setzt, ist die Wahrheit
        darueber, wo die App gerade haengt. LOUCKUP_BASE_URL bleibt fuer
        absolute Adressen zustaendig (die OAuth-Redirect-URI), aber fuer
        die internen Links gilt, was der Mount sagt: ist die Variable
        leer oder falsch gesetzt, landen Redirects sonst ausserhalb des
        Bereichs und der Browser zeigt die 404-Seite des Dashboards.
        """
        scope_prefix = ""
        if request is not None:
            scope_prefix = (request.scope.get("root_path") or "").rstrip("/")
        return scope_prefix or settings.root_path.rstrip("/")

    def href(path: str, request: Request | None = None) -> str:
        """Pfad innerhalb des Mounts, damit Links auch gemountet stimmen."""
        pref = prefix(request)
        if not path.startswith("/"):
            path = "/" + path
        return f"{pref}{path}" if pref else path

    def cookie_secure(request: Request) -> bool:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
        return proto == "https"

    def ctx(request: Request, **extra: Any) -> dict[str, Any]:
        user = auth.get_session_user(request)
        base = {
            "request": request,
            "brand": settings.louckup_brand_name,
            "footer": settings.louckup_footer,
            "base_url": settings.base_url,
            "root_path": prefix(request),
            "user": user,
            "avatar_url": auth.avatar_url(user["uid"], user.get("avatar")) if user else None,
            "flash": request.cookies.get("louckup_flash"),
        }
        base.update(extra)
        return base

    def flash(response: Response, message: str, request: Request | None = None) -> None:
        secure = cookie_secure(request) if request is not None else True
        safe = (
            str(message)
            .replace("„", "'")
            .replace("“", "'")
            .replace("”", "'")
            .replace("–", "-")
            .replace("—", "-")
            .encode("latin-1", errors="replace")
            .decode("latin-1")
        )[:180]
        response.set_cookie(
            "louckup_flash",
            safe,
            max_age=30,
            path=settings.louckup_cookie_path or "/",
            httponly=False,
            samesite="lax",
            secure=secure,
        )

    def clear_flash(response: Response) -> None:
        response.delete_cookie("louckup_flash", path=settings.louckup_cookie_path or "/")

    def set_session(response: Response, token: str, request: Request) -> None:
        response.set_cookie(
            settings.louckup_cookie_name,
            token,
            max_age=settings.louckup_session_max_age,
            path=settings.louckup_cookie_path or "/",
            httponly=True,
            samesite="lax",
            secure=cookie_secure(request),
        )

    def clear_session(response: Response) -> None:
        response.delete_cookie(
            settings.louckup_cookie_name, path=settings.louckup_cookie_path or "/"
        )
        response.delete_cookie("louckup_oauth_state", path=settings.louckup_cookie_path or "/")

    # ── Seiten ────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        if auth.get_session_user(request):
            return RedirectResponse(url=href("/dashboard", request), status_code=302)
        return RedirectResponse(url=href("/login", request), status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if auth.get_session_user(request):
            return RedirectResponse(url=href("/dashboard", request), status_code=302)
        resp = render(
            request,
            "login.html",
            ctx(
                request,
                missing=settings.missing_config,
                redirect_uri=settings.oauth_redirect_uri,
                scopes=settings.scopes,
            ),
        )
        clear_flash(resp)
        return resp

    @app.get("/auth/discord")
    async def auth_discord(request: Request, force: int = 0):
        adresse = request.client.host if request.client else "unbekannt"
        if not rate_ok(f"login:{adresse}", settings.louckup_login_rate_limit):
            log.warning("Login-Rate-Limit griff fuer %s", adresse)
            return PlainTextResponse("Zu viele Versuche. Bitte warte einen Moment.", status_code=429)

        if not settings.oauth_configured:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, "OAuth ist nicht konfiguriert (CLIENT_ID / CLIENT_SECRET).", request)
            return resp
        state = auth.make_oauth_state()
        resp = RedirectResponse(
            url=auth.oauth_authorize_url(state, settings, force=bool(force)), status_code=302
        )
        # Pfad muss /louckup sein, sonst schickt der Browser den Cookie
        # beim Callback nicht mit.
        resp.set_cookie(
            "louckup_oauth_state",
            state,
            max_age=600,
            path=settings.louckup_cookie_path or "/",
            httponly=True,
            samesite="lax",
            secure=cookie_secure(request),
        )
        return resp

    @app.get("/auth/callback")
    async def auth_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ):
        if error:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, f"Discord-Login abgebrochen: {error_description or error}", request)
            return resp

        expected = request.cookies.get("louckup_oauth_state")
        if not code:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, "Kein OAuth-Code von Discord erhalten.", request)
            return resp
        if not state or not expected or state != expected:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(
                resp,
                "OAuth-State ungültig oder abgelaufen. Bitte nochmal über "
                "„Mit Discord anmelden“ starten.",
                request,
            )
            return resp

        try:
            token_data = await auth.exchange_code(code, settings)
            access = token_data.get("access_token")
            if not access:
                raise HTTPException(status_code=400, detail="no_access_token")
            duser = await auth.fetch_discord_user(access)
            if not duser.get("id"):
                raise HTTPException(status_code=400, detail="no_user_id")

            user_id = int(duser["id"])
            username = duser.get("username") or "user"
            is_owner = user_id in settings.owner_ids
            expires_in = int(token_data.get("expires_in") or 0)
            granted = token_data.get("scope") or settings.scopes
            granted = granted if isinstance(granted, str) else " ".join(granted)

            db = await get_db()
            await dbmod.upsert_user(
                db,
                user_id=user_id,
                username=username,
                global_name=duser.get("global_name"),
                avatar=duser.get("avatar"),
                email=duser.get("email"),
                verified=duser.get("verified"),
                access_token=access,
                refresh_token=token_data.get("refresh_token"),
                token_expires_at=int(time.time()) + expires_in if expires_in else None,
                scopes=granted,
                is_owner=is_owner,
            )

            guilds: list[dict[str, Any]] = []
            if is_owner:
                # Nur für Owner laden — für alle anderen brauchen wir die
                # Liste nicht und wollen sie auch nicht speichern.
                try:
                    guilds = await auth.fetch_user_guilds(access)
                    await dbmod.replace_user_guilds(db, user_id, guilds)
                except Exception:
                    log.exception("Serverliste konnte nicht geladen werden")

            await dbmod.record_attempt(
                db,
                user_id=user_id,
                username=username,
                is_owner=is_owner,
                outcome="granted" if is_owner else "not_owner",
                detail=granted,
            )
        except HTTPException as exc:
            log.exception("Louckup OAuth fehlgeschlagen")
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, f"Login fehlgeschlagen: {exc.detail}", request)
            return resp
        except Exception as exc:
            log.exception("Louckup OAuth Fehler")
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, f"Login-Fehler: {type(exc).__name__}: {exc}"[:140], request)
            return resp

        # Nicht-Owner: kein Session-Cookie, sofort zurück aufs Dashboard.
        if not is_owner:
            log.info("Louckup: %s (%s) ist kein Owner — weiter aufs Dashboard", username, user_id)
            resp = RedirectResponse(url=settings.louckup_fallback_url or "/", status_code=302)
            clear_session(resp)
            return resp

        resp = RedirectResponse(url=href("/dashboard", request), status_code=302)
        set_session(resp, auth.create_session_token(duser, settings), request)
        resp.delete_cookie("louckup_oauth_state", path=settings.louckup_cookie_path or "/")
        return resp

    # Die Reiter. 1-3 sind Platzhalter, "Self" zeigt die eigenen Daten —
    # und zwar nur die des eingeloggten Kontos, nie die der anderen
    # Owner. Jeder sieht ausschliesslich seinen eigenen Datensatz.
    TABS: tuple[tuple[str, str], ...] = (
        ("discord-ids", "Discord IDs"),
        ("roblox", "Roblox User"),
        ("ip", "IP"),
        ("self", "Self"),
    )
    TAB_TITEL = dict(TABS)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        # Erst die Session pruefen und dann weiterleiten. Ohne das wuerde
        # ein nicht angemeldeter Besucher zwei Spruenge machen
        # (/dashboard -> /dashboard/self -> /login) statt einem.
        if not auth.get_session_user(request):
            return RedirectResponse(url=href("/login", request), status_code=302)
        return RedirectResponse(url=href("/dashboard/self", request), status_code=302)

    @app.get("/dashboard/{tab}", response_class=HTMLResponse)
    async def dashboard_tab(request: Request, tab: str):
        user = auth.get_session_user(request)
        if not user:
            return RedirectResponse(url=href("/login", request), status_code=302)

        # Zweite Prüfung: die Owner-Liste kann sich geändert haben, während
        # jemand eingeloggt war. Ein Cookie allein ist keine Berechtigung.
        if int(user["uid"]) not in settings.owner_ids:
            resp = RedirectResponse(url=settings.louckup_fallback_url or "/", status_code=302)
            clear_session(resp)
            return resp

        if tab not in TAB_TITEL:
            return RedirectResponse(url=href("/dashboard/self", request), status_code=302)

        uid = int(user["uid"])
        db = await get_db()
        record = await dbmod.get_user(db, uid)
        # Serverliste nur laden, wenn sie auch gebraucht wird.
        # Auf Self nur die eigenen Daten — inklusive der eigenen Logins.
        guilds = await dbmod.list_user_guilds(db, uid) if tab == "self" else []
        logins = await dbmod.own_attempts(db, uid, limit=10) if tab == "self" else []

        resp = render(
            request,
            "dashboard.html",
            ctx(
                request,
                tab=tab,
                tab_title=TAB_TITEL[tab],
                tabs=TABS,
                record=record,
                guilds=guilds,
                logins=logins,
                scopes=(record or {}).get("scopes") or settings.scopes,
            ),
        )
        # Nichts hier darf im Browser-Cache landen, auch nicht auf
        # geteilten Rechnern.
        clear_flash(resp)
        return resp

    @app.get("/logout")
    async def logout(request: Request):
        resp = RedirectResponse(url=href("/login", request), status_code=302)
        clear_session(resp)
        return resp

    @app.get("/healthz")
    async def healthz():
        return JSONResponse(
            {
                "ok": True,
                "area": "louckup",
                "oauth_configured": settings.oauth_configured,
                "owners": len(settings.owner_ids),
                "secret_is_dev": settings.secret_is_dev,
                "base_url": settings.base_url,
            }
        )

    return app


app = create_app()
