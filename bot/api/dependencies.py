from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
import hmac
import os

security = HTTPBearer(auto_error=False)
limiter = Limiter(key_func=get_remote_address)
_bot_instance = None
_bot_loop = None


def set_bot(bot_instance):
    """Store bot instance for dependency injection."""
    global _bot_instance
    _bot_instance = bot_instance


def set_bot_loop(loop):
    """
    Remember the event loop the bot is actually running on.

    The API runs in a separate thread with its OWN event loop. discord.py
    objects (HTTP session, gateway, locks) are bound to the bot's loop, so
    awaiting them from the API loop raises

        RuntimeError: Timeout context manager should be used inside a task

    Everything that touches discord.py therefore has to be scheduled back
    onto this loop via run_on_bot_loop().
    """
    global _bot_loop
    _bot_loop = loop


def get_bot_loop():
    return _bot_loop


async def run_on_bot_loop(coro, timeout: float = 30.0):
    """
    Execute a coroutine on the bot's event loop and await the result from
    whatever loop the caller is on.

    Falls back to a plain await when the bot loop is unknown or when we are
    already running on it, so this is safe to use unconditionally.
    """
    import asyncio

    loop = _bot_loop
    if loop is None or loop.is_closed():
        # No bot loop registered (e.g. tests) - run inline.
        return await coro

    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None

    if running is loop:
        return await coro

    fut = asyncio.run_coroutine_threadsafe(coro, loop)
    return await asyncio.wrap_future(fut)


def get_bot():
    """Get bot instance."""
    if _bot_instance is None:
        raise HTTPException(status_code=503, detail="Bot is not ready yet.")
    return _bot_instance


def _allow_keyless() -> bool:
    """
    Whether requests without an API key are acceptable.

    Only true when no key is configured at all, which is the local development
    case. In every deployment DASHBOARD_API_KEY is set and the key is required.
    Set ALLOW_KEYLESS_API=false to forbid this even locally.
    """
    if os.getenv("ALLOW_KEYLESS_API", "true").strip().lower() != "true":
        return False
    return not os.getenv("DASHBOARD_API_KEY")


# Die Routen, die der Template-Bot mit seinem eigenen Token erreichen
# darf. (Methode, Pfadstueck) -- beides muss passen.
#
# Die Liste steht hier oben und nicht als `if` im Rumpf, weil sie schon
# einmal auseinandergelaufen ist: `/premium/grant` wurde als Route
# gebaut, die Ausnahme aber nicht erweitert. Ergebnis war HTTP 401 auf
# ein voellig korrektes Token -- und im Log des Template-Bots die
# irrefuehrende Meldung "stimmt PREMIUM_PARTNER_TOKEN auf beiden
# Seiten?", die auf eine falsche Faehrte fuehrt.
#
# Wer hier eine Route ergaenzt, muss sich bewusst sein: sie ist damit
# ohne Dashboard-Schluessel erreichbar, allein mit dem Partner-Token.
PARTNER_ROUTES: tuple[tuple[str, str], ...] = (
    # Fragt: "hat dieses Konto Premium?" -- nur lesen.
    ("GET", "/premium/check/"),
    # Meldet: "dieses Konto hat gerade seine Probewoche eingeloest."
    # Schreibend, aber eng: die Route selbst laesst genau eine
    # Probewoche pro Konto zu und prueft das Token ein zweites Mal.
    ("POST", "/premium/grant"),
)


def _is_partner_request(request: Request) -> bool:
    """
    Whether this is the template bot talking to us with its own token.

    Those endpoints carry their own credential (X-Partner-Token) and are
    called by a different program, which has no reason to know the
    dashboard key. Without this exception the route answered 401 to a
    correct token and premium never activated anywhere.

    Narrow on purpose: only the routes in PARTNER_ROUTES, only with the
    matching method, and only when a partner token is actually
    configured and matches. Everything else still needs the dashboard
    key -- listing keys with the partner token stays forbidden.
    """
    path = request.url.path.rstrip("/")

    passt = any(
        request.method == methode and stueck.rstrip("/") in path
        for methode, stueck in PARTNER_ROUTES
    )
    if not passt:
        return False

    expected = os.getenv("PREMIUM_PARTNER_TOKEN", "").strip()
    if not expected:
        return False

    supplied = (request.headers.get("x-partner-token") or "").strip()
    if not supplied:
        return False

    return hmac.compare_digest(supplied, expected)


# Der alte Name bleibt als Verweis: er stand in Tests und Kommentaren.
_is_partner_licence_check = _is_partner_request


def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """
    Verify the API key from the Authorization header.

    SECURITY NOTE
    -------------
    Earlier versions trusted any request originating from 127.0.0.1. That was
    unsafe: the Next.js dashboard proxies browser traffic from exactly that
    address, so every visitor inherited full API access without a key.

    The key is now always required whenever one is configured, regardless of
    the source address. Comparison is constant-time to avoid leaking the key
    through timing differences.
    """
    # The template bot authenticates with its own token on the routes
    # listed in PARTNER_ROUTES; see _is_partner_request.
    if _is_partner_request(request):
        return "partner-token"

    api_key = os.getenv("DASHBOARD_API_KEY")

    if not api_key:
        if _allow_keyless():
            return "no-key-configured"
        raise HTTPException(
            status_code=503,
            detail="Server misconfigured: DASHBOARD_API_KEY is not set.",
        )

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide Authorization: Bearer <key> header.",
        )

    if not hmac.compare_digest(credentials.credentials, api_key):
        raise HTTPException(status_code=401, detail="Invalid API key.")

    return credentials.credentials
