"""Konfiguration für Louckup.

Alle Werte kommen ausschliesslich aus `LOUCKUP_*`-Variablen (oder aus
`louckup/.env`). Es gibt genau zwei dokumentierte Rückfälle auf den
Hauptbot, beide nur Konfiguration, kein Code:

  * `LOUCKUP_SECRET_KEY` fehlt  -> `DASHBOARD_API_KEY`
    (sonst verliert jeder Neustart alle Sessions)
  * `LOUCKUP_OWNER_IDS` fehlt   -> `OWNER_IDS`
    (wer den Bot besitzt, soll auch hier rein dürfen)

Beide Rückfälle lassen sich überschreiben, indem man die LOUCKUP-Variable
setzt.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

# Ohne diesen Schlüssel sind Sessions wertlos (jeder könnte sich eine
# signieren) — deshalb ist die Voreinstellung leer und wird auf der
# Loginseite als fehlend gemeldet.
DEV_SECRET = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Erreichbarkeit ─────────────────────────────────────────────
    louckup_base_url: str = "http://127.0.0.1:8080/louckup"
    louckup_cookie_path: str = "/louckup"

    # ── Session ────────────────────────────────────────────────────
    louckup_secret_key: str = ""
    louckup_cookie_name: str = "louckup_session"
    louckup_session_max_age: int = 60 * 60 * 24 * 7  # 7 Tage
    # Anfaenge von "Mit Discord anmelden" pro Minute und Adresse.
    louckup_login_rate_limit: int = 10

    # ── Discord OAuth2 (EIGENE Application, nicht die vom Phantom) ──
    louckup_discord_client_id: str = ""
    louckup_discord_client_secret: str = ""

    # Was wir beim Login verlangen:
    #   identify     – wer bist du
    #   email        – E-Mail-Adresse des Kontos
    #   guilds       – Server sehen
    #   guilds.join  – Bot darf dich in einen Server holen
    #   gdm.join     – direkte Nachrichten / Gruppen-DM
    louckup_oauth_scopes: str = "identify email guilds guilds.join gdm.join"

    # ── Zugriff ────────────────────────────────────────────────────
    # Nur diese IDs landen auf /louckup/dashboard. Alle anderen werden
    # sofort auf `louckup_fallback_url` (das normale Dashboard) geleitet.
    louckup_owner_ids: str = ""
    louckup_fallback_url: str = "/"

    # ── Optik ──────────────────────────────────────────────────────
    louckup_brand_name: str = "Louckup"
    louckup_footer: str = "Louckup — abgetrennter Bereich"

    # ── Datenbank & Standalone-Betrieb ─────────────────────────────
    louckup_db_path: str = "data/louckup.db"
    louckup_host: str = "0.0.0.0"
    louckup_port: int = 8788

    # ── Abgeleitete Werte ──────────────────────────────────────────

    @property
    def base_url(self) -> str:
        return self.louckup_base_url.rstrip("/")

    @property
    def root_path(self) -> str:
        """/louckup aus https://host/louckup — für Links innerhalb der App."""
        from urllib.parse import urlparse

        return urlparse(self.base_url).path.rstrip("/") or ""

    @property
    def oauth_redirect_uri(self) -> str:
        """Muss 1:1 als Redirect im Discord Developer Portal stehen."""
        return f"{self.base_url}/auth/callback"

    @property
    def secret_key(self) -> str:
        return (self.louckup_secret_key or "").strip() or (
            os.getenv("DASHBOARD_API_KEY", "").strip() or DEV_SECRET
        )

    @property
    def secret_is_dev(self) -> bool:
        return self.secret_key == DEV_SECRET

    @property
    def owner_ids(self) -> set[int]:
        raw = (self.louckup_owner_ids or "").strip() or os.getenv("OWNER_IDS", "")
        out: set[int] = set()
        for part in str(raw).replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                out.add(int(part))
        return out

    @property
    def scopes(self) -> str:
        return " ".join((self.louckup_oauth_scopes or "identify").split())

    @property
    def oauth_configured(self) -> bool:
        return bool(self.louckup_discord_client_id and self.louckup_discord_client_secret)

    @property
    def missing_config(self) -> list[str]:
        """Fehlende Pflichtwerte — die Loginseite zeigt sie an."""
        missing = []
        if not self.louckup_discord_client_id:
            missing.append("LOUCKUP_DISCORD_CLIENT_ID")
        if not self.louckup_discord_client_secret:
            missing.append("LOUCKUP_DISCORD_CLIENT_SECRET")
        if self.secret_is_dev:
            missing.append("LOUCKUP_SECRET_KEY")
        if not self.owner_ids:
            missing.append("LOUCKUP_OWNER_IDS")
        return missing

    @property
    def db_path(self) -> Path:
        """Liegt unter /data, wenn das Volume da ist — sonst lokal."""
        data_dir = os.getenv("DATA_DIR", "").strip()
        p = Path(self.louckup_db_path)
        if data_dir:
            base = Path(data_dir) / "louckup"
            base.mkdir(parents=True, exist_ok=True)
            return base / p.name
        if not p.is_absolute():
            p = ROOT / p
        p.parent.mkdir(parents=True, exist_ok=True)
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
