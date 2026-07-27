from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import os, time, json, logging, httpx
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import Response
from utils.config import *
from api.routes import bot, guilds, admin, team, moderation, actions, access, servers, servertools, tickets
from api.dependencies import verify_api_key, limiter, get_bot_loop
from api.db_manager import db_manager
from api.schema_guard import ensure_schema
from utils import feature_flags
from utils import dashboard_roles
from utils import dashboard_access
from utils.feature_services import record_request

logger = logging.getLogger("api_request_logs")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(message)s'))
    logger.addHandler(handler)

DASHBOARD_PORT = os.getenv("DASHBOARD_PORT", "3000")
DASHBOARD_URL = f"http://127.0.0.1:{DASHBOARD_PORT}"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Cogs create their tables lazily, but the API reads the same tables and
    # usually gets there first on a fresh deployment. Without this the
    # dashboard is full of "no such table" errors.
    try:
        await ensure_schema()
    except Exception as exc:
        logger.warning(f"Schema guard failed: {exc}")

    # The API thread has its own event loop, so the flag cache has to be
    # primed here as well as in the bot's setup_hook.
    try:
        await feature_flags.load()
    except Exception as exc:
        logger.warning(f"Feature flag preload failed: {exc}")

    try:
        await dashboard_roles.load()
    except Exception as exc:
        logger.warning(f"Dashboard role preload failed: {exc}")

    # The ban list is consulted on every dashboard request, so it has to be
    # in memory before the first one arrives.
    try:
        await dashboard_access.load()
        await dashboard_access.purge_expired()
    except Exception as exc:
        logger.warning(f"Dashboard access preload failed: {exc}")

    yield
    await db_manager.close_all()


# api_rate_limit_boost: authenticated dashboard traffic gets a much higher
# ceiling than anonymous callers, but the API is never left completely
# unlimited.
RATE_LIMIT_STANDARD = 60      # requests per minute
RATE_LIMIT_BOOSTED = 600

_rate_state: dict[str, tuple[int, float]] = {}


async def api_rate_limit(request: Request):
    """Simple fixed-window limiter applied to the /api/v1 sub-application."""
    from fastapi import HTTPException

    limit = RATE_LIMIT_BOOSTED if feature_flags.is_enabled("api_rate_limit_boost") else RATE_LIMIT_STANDARD
    client_ip = request.client.host if request.client else "unknown"
    window = int(time.time() // 60)
    key = f"{client_ip}:{window}"

    count, _ = _rate_state.get(key, (0, time.time()))
    count += 1
    _rate_state[key] = (count, time.time())

    # Drop windows older than two minutes so the dict cannot grow unbounded.
    if len(_rate_state) > 4096:
        cutoff = time.time() - 120
        for stale in [k for k, (_, ts) in _rate_state.items() if ts < cutoff]:
            _rate_state.pop(stale, None)

    if count > limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({limit} requests/minute).",
        )

async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Turn any unhandled crash into JSON the dashboard can display.

    Starlette's default is a bare text/plain "Internal Server Error", which is
    exactly what the dashboard toast showed: a 500 with nothing to act on and
    no way to find the cause in the logs. Every crash now carries a short
    incident id that also appears in the container log.
    """
    import traceback
    import uuid

    incident = uuid.uuid4().hex[:8]
    logger.error(
        f"[{incident}] Unhandled error on {request.method} {request.url.path}: "
        f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
    )

    detail = f"{type(exc).__name__}: {exc}".strip()

    # SQLite trouble is the common case on Railway, where db/ is wiped on
    # every redeploy unless a volume is mounted. Say what to do about it.
    text = str(exc).lower()
    if "unable to open database file" in text:
        detail = (
            "The database directory is missing. This happens after a Railway "
            "redeploy when no volume is mounted at /app/bot/db. It is being "
            "recreated \u2014 please retry in a moment."
        )
    elif "database is locked" in text:
        detail = "The database is busy right now. Please retry in a moment."

    return Response(
        content=json.dumps({"detail": detail, "incident": incident}),
        status_code=500,
        media_type="application/json",
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title=f"{BRAND_NAME} Bot API",
        description=f"REST API + Dashboard for {BRAND_NAME}",
        version="1.0",
        lifespan=lifespan
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        duration_ms = round(process_time * 1000, 2)
        log_data = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }
        logger.info(json.dumps(log_data))

        # Feeds dashboard_performance_metrics and slow_query_detector.
        try:
            record_request(request.url.path, duration_ms, response.status_code)
        except Exception:
            pass

        return response

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    app.add_exception_handler(Exception, unhandled_exception_handler)

    _extra_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
    _railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
    _allowed_origins = list(dict.fromkeys([
        "http://localhost:3000", "http://localhost:8080",
        *([f"https://{_railway_domain}"] if _railway_domain else []),
        *(_extra_origins),
    ]))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        dashboard_ok = False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{DASHBOARD_URL}/")
                dashboard_ok = r.status_code < 500
        except Exception:
            pass

        bot_instance = getattr(app.state, "bot", None)
        bot_ready = bool(bot_instance and bot_instance.is_ready())

        payload = {
            "status": "ok",
            "bot": BRAND_NAME,
            "bot_ready": bot_ready,
            "dashboard": "online" if dashboard_ok else "starting",
        }

        # deployment_health_gate: report unhealthy until the bot is actually
        # connected, so a rolling deploy does not send traffic too early.
        if feature_flags.is_enabled("deployment_health_gate") and not (bot_ready and dashboard_ok):
            payload["status"] = "starting"
            return Response(
                content=json.dumps(payload),
                status_code=503,
                media_type="application/json",
            )

        return payload

    # Bot API ONLY under /api/v1 — NOT /api (so NextAuth /api/auth/* goes to dashboard)
    api_app = FastAPI(dependencies=[Depends(verify_api_key), Depends(api_rate_limit)])
    # The routers live on this sub-app, so the handler has to be here too:
    # one registered on the parent never sees their exceptions.
    api_app.add_exception_handler(Exception, unhandled_exception_handler)

    # ------------------------------------------------------------------
    # Run every API handler on the BOT's event loop.
    #
    # uvicorn runs in its own thread with its own loop, but discord.py
    # objects (HTTP session, gateway, locks) belong to the bot's loop.
    # Awaiting them from here raised
    #     RuntimeError: Timeout context manager should be used inside a task
    # on every dashboard action (ban, kick, send message, edit channel...).
    #
    # Doing it once as middleware fixes all routes at once, instead of
    # wrapping 112 endpoints by hand.
    # ------------------------------------------------------------------
    @api_app.middleware("http")
    async def run_on_bot_event_loop(request: Request, call_next):
        loop = get_bot_loop()
        if loop is None or loop.is_closed():
            return await call_next(request)

        try:
            if asyncio.get_running_loop() is loop:
                return await call_next(request)
        except RuntimeError:
            pass

        async def _handle():
            response = await call_next(request)

            # A streaming response hands back a lazy iterator that is bound
            # to *this* loop. Returning it would make the server read it
            # from the uvicorn loop instead, which deadlocks and leaves the
            # download spinning forever. Drain it here, while we are still
            # on the loop that owns it.
            iterator = getattr(response, "body_iterator", None)
            if iterator is not None:
                chunks = [chunk async for chunk in iterator]
                body = b"".join(
                    c if isinstance(c, bytes) else str(c).encode("utf-8")
                    for c in chunks
                )
                headers = dict(response.headers)
                # The length changes once the body is assembled.
                headers.pop("content-length", None)
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=headers,
                    media_type=response.media_type,
                )

            return response

        fut = asyncio.run_coroutine_threadsafe(_handle(), loop)
        return await asyncio.wrap_future(fut)

    api_app.include_router(bot.router, prefix="/bot", tags=["Bot"])
    api_app.include_router(guilds.router, prefix="/guilds", tags=["Guilds"])
    api_app.include_router(admin.router, prefix="/admin", tags=["Admin"])
    api_app.include_router(team.router, prefix="/team", tags=["Team"])
    api_app.include_router(moderation.router, prefix="/moderation", tags=["Moderation"])
    api_app.include_router(actions.router, prefix="/actions", tags=["Actions"])
    api_app.include_router(access.router, prefix="/access", tags=["Access"])
    api_app.include_router(servers.router, prefix="/servers", tags=["Servers"])
    api_app.include_router(
        servertools.router, prefix="/servertools", tags=["Server Tools"]
    )
    api_app.include_router(tickets.router, prefix="/tickets", tags=["Tickets"])

    @api_app.get("/health")
    async def api_health():
        return {"status": "ok"}

    # Mount bot API at /api/v1 ONLY
    app.mount("/api/v1", api_app)

    # Dashboard proxy — handles everything else (including /api/auth/*)
    @app.api_route("/{path:path}", methods=["GET","POST","PUT","DELETE","PATCH","OPTIONS","HEAD"])
    async def proxy_to_dashboard(request: Request, path: str):
        target_url = f"{DASHBOARD_URL}/{path}"
        headers = dict(request.headers)
        headers.pop("host", None)
        body = await request.body()
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                resp = await client.request(
                    method=request.method,
                    url=target_url,
                    headers=headers,
                    content=body,
                    params=dict(request.query_params),
                )
            # Preserve response headers from Next.js. Do NOT collapse headers into a
            # dict here: NextAuth often sends multiple Set-Cookie headers during
            # sign-in/callback/session refresh. Collapsing them breaks the Discord
            # session cookie and causes endless re-authorization loops.
            excluded = {"content-encoding", "content-length", "transfer-encoding", "connection"}
            response = Response(content=resp.content, status_code=resp.status_code)
            response.raw_headers = [
                (name, value)
                for name, value in resp.headers.raw
                if name.decode("latin-1").lower() not in excluded
            ]
            return response
        except httpx.ConnectError:
            return Response(
                content="""<!DOCTYPE html><html><head><title>University Bot</title>
<style>body{font-family:system-ui;display:flex;justify-content:center;align-items:center;height:100vh;background:#0a0a0a;color:#fff;margin:0}
.box{text-align:center;padding:40px}.spinner{width:40px;height:40px;border:4px solid #333;border-top-color:#8b5cf6;border-radius:50%;animation:spin 1s linear infinite;margin:0 auto 20px}
@keyframes spin{to{transform:rotate(360deg)}}</style></head>
<body><div class="box"><div class="spinner"></div>
<h2>University Bot startet...</h2><p>Bitte warte 30 Sekunden und <a href="javascript:location.reload()" style="color:#8b5cf6">lade neu</a>.</p>
</div></body></html>""",
                status_code=503, media_type="text/html",
            )
        except Exception as e:
            logger.error(f"Dashboard proxy error: {e}")
            return Response(content=f"Dashboard error: {str(e)}", status_code=502, media_type="text/plain")

    return app
