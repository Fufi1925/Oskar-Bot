"""Environment-only configuration for the isolated LBoost Shop area."""
from __future__ import annotations

import os
from pathlib import Path
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
    oauth_scopes: str = "identify email guilds guilds.join gdm.join"

    # Explicit shop access plus the fixed University Bot owners.
    authorized_ids: str = ""
    owner_ids: str = ""
    allowed_guild_ids: str = ""
    fallback_url: str = "/"
    secret_key: str = ""
    token_encryption_key: str = ""
    db_path: str = str(Path(__file__).resolve().parents[1] / "data" / "lbost_shop.sqlite3")

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
    def owner_id_set(self) -> set[int]:
        return self._ids(self.owner_ids) | self._ids(os.getenv("OWNER_IDS", ""))

    @property
    def allowed_ids(self) -> set[int]:
        return self._ids(self.authorized_ids) | self.owner_id_set

    @property
    def allowed_guild_id_set(self) -> set[int]:
        return self._ids(self.allowed_guild_ids)

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
        if not self.allowed_guild_id_set:
            missing.append("LBOST_SHOP_ALLOWED_GUILD_IDS")
        if not self.bot_token:
            missing.append("LBOST_SHOP_BOT_TOKEN")
        if not self.token_encryption_key:
            missing.append("LBOST_SHOP_TOKEN_ENCRYPTION_KEY")
        return missing


@lru_cache
def get_settings() -> Settings:
    return Settings()
