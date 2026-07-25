from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os, time, json, logging, httpx
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import Response
from utils.config import *
from api.routes import bot, guilds, admin
from api.dependencies import verify_api_key, limiter
from api.db_manager import db_manager

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
    yield
    await db_manager.close_all()

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
        log_data = {
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(process_time * 1000, 2),
        }
        logger.info(json.dumps(log_data))
        return response

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

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
        except:
            pass
        return {"status": "ok", "bot": BRAND_NAME, "dashboard": "online" if dashboard_ok else "starting"}

    # Bot API ONLY under /api/v1 — NOT /api (so NextAuth /api/auth/* goes to dashboard)
    api_app = FastAPI(dependencies=[Depends(verify_api_key)])
    api_app.include_router(bot.router, prefix="/bot", tags=["Bot"])
    api_app.include_router(guilds.router, prefix="/guilds", tags=["Guilds"])
    api_app.include_router(admin.router, prefix="/admin", tags=["Admin"])

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
