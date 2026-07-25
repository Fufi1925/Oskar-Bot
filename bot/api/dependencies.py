from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
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


def verify_api_key(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """
    Verify API key from Authorization header.
    Allows requests from localhost without key (internal container traffic).
    """
    # Allow internal requests (from same container) without API key
    client_host = request.client.host if request.client else ""
    if client_host in ("127.0.0.1", "localhost", "::1"):
        return "internal"

    api_key = os.getenv("DASHBOARD_API_KEY")

    # If no key is configured, allow all requests (for local development)
    if not api_key:
        return "no-key-configured"

    # If key is configured, verify it
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="API key required. Provide Authorization: Bearer <key> header."
        )

    if credentials.credentials != api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key."
        )

    return credentials.credentials
