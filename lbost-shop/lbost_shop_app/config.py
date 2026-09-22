"""Environment-only configuration for the isolated LBoost Shop area."""
from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LBOST_SHOP_", extra="ignore")

    base_url: str = "http://127.0.0.1:8080/lbost-shop"
    cookie_path: str = "/lbost-shop"
    cookie_name: str = "lbost_shop_session"
    session_max_age: int = 60 * 60 * 24 * 7
    login_rate_limit: int = 10

    # Dedicated Discord application for this area.
    discord_client_id: str = ""
    discord_client_secret: str = ""
    oauth_scopes: str = "identify"

    # Explicit shop access plus the fixed University Bot owners.
    authorized_ids: str = ""
    owner_ids: str = ""
    fallback_url: str = "/"
    secret_key: str = ""

    # Reserved for the separate shop bot that will be built later.
    bot_token: str = ""
    brand_name: str = "LBoost Shop"

    @property
    def root_path(self) -> str:
        return urlparse(self.base_url.rstrip("/")).path.rstrip("/") or "/lbost-shop"

    @property
    def oauth_redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/auth/callback"

    @staticmethod
    def _ids(raw: str) -> set[int]:
        result: set[int] = set()
        for part in str(raw or "").replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                result.add(int(part))
        return result

    @property
    def allowed_ids(self) -> set[int]:
        explicit = self._ids(self.authorized_ids)
        owners = self._ids(self.owner_ids or os.getenv("OWNER_IDS", ""))
        return explicit | owners

    @property
    def signing_secret(self) -> str:
        return self.secret_key.strip() or DEV_SECRET

    @property
    def oauth_configured(self) -> bool:
        return bool(self.discord_client_id and self.discord_client_secret)

    @property
    def scopes(self) -> str:
        return " ".join((self.oauth_scopes or "identify").split())

    @property
    def missing_config(self) -> list[str]:
        missing: list[str] = []
        if not self.discord_client_id:
            missing.append("LBOST_SHOP_DISCORD_CLIENT_ID")
        if not self.discord_client_secret:
            missing.append("LBOST_SHOP_DISCORD_CLIENT_SECRET")
        if self.signing_secret == DEV_SECRET:
            missing.append("LBOST_SHOP_SECRET_KEY")
        if not self.allowed_ids:
            missing.append("LBOST_SHOP_AUTHORIZED_IDS oder OWNER_IDS")
        return missing


@lru_cache
def get_settings() -> Settings:
    return Settings()
