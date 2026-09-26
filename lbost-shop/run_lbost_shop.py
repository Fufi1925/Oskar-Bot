#!/usr/bin/env python3
"""Startet den Shop-Bereich allein (für die Entwicklung).

Der Produktivweg läuft über die Haupt-App, die diesen Bereich unter
``/lbost-shop`` mountet. Hier gibt es dasselbe ``root_path``-Verhalten, damit
Links, Cookies und Redirects im Test genauso aussehen wie später.
"""
from __future__ import annotations

from fastapi import FastAPI
import uvicorn

from lbost_shop_app.config import get_settings
from lbost_shop_app.main import create_app
from urllib.parse import urlparse


def build() -> tuple[FastAPI, int, str]:
    settings = get_settings()
    port = int((urlparse(settings.base_url).port or 8790))
    pfad = urlparse(settings.base_url).path.rstrip("/") or "/lbost-shop"
    if pfad and pfad != "/":
        parent = FastAPI()
        parent.mount(pfad, create_app())
        return parent, port, pfad
    return create_app(), port, ""


if __name__ == "__main__":
    app, port, pfad = build()
    print(f"LBoost Shop: http://127.0.0.1:{port}{pfad}/")
    uvicorn.run(app, host="127.0.0.1", port=port)
