from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
import hmac
import os

security = HTTPBearer(auto_error=False)
limiter = Limiter(key_func=get_remote_address)
_bot_instance = None


def set_bot(bot_instance):
    """Store bot instance for dependency injection."""
    global _bot_instance
    _bot_instance = bot_instance


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
