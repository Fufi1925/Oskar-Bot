from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

security = HTTPBearer(auto_error=False)

def set_bot(bot_instance):
    """Store bot instance for dependency injection."""
    global _bot_instance
    _bot_instance = bot_instance

def get_bot():
    """Get bot instance."""
    return _bot_instance

def verify_api_key(request: Request, credentials: HTTPAuthorizationCredentials = None):
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
