#!/usr/bin/env python3
"""Louckup allein starten (zum Entwickeln).

Im Normalfall wird Louckup in die FastAPI-App des Bots gemountet und
läuft unter <url>/louckup mit. Dieses Skript braucht man nur, wenn man
den Bereich auf einem eigenen Port testen will:

    cd louckup
    python run_louckup.py      -> http://127.0.0.1:8788
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn

from louckup_app.config import get_settings
from louckup_app.main import create_app

app = create_app()

if __name__ == "__main__":
    s = get_settings()
    print(f"Louckup startet auf http://127.0.0.1:{s.louckup_port}")
    print(f"  base_url     : {s.base_url}")
    print(f"  redirect_uri : {s.oauth_redirect_uri}")
    if s.missing_config:
        print(f"  ! fehlend    : {', '.join(s.missing_config)}")
    uvicorn.run(app, host=s.louckup_host, port=s.louckup_port, log_level="info")
