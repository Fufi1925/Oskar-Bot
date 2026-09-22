#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHOP = ROOT / "lbost-shop"
failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


main = (SHOP / "lbost_shop_app/main.py").read_text()
config = (SHOP / "lbost_shop_app/config.py").read_text()
auth = (SHOP / "lbost_shop_app/auth.py").read_text()
db = (SHOP / "lbost_shop_app/db.py").read_text()
landing = (SHOP / "lbost_shop_app/templates/landing.html").read_text()
login = (SHOP / "lbost_shop_app/templates/login.html").read_text()
dash = (SHOP / "lbost_shop_app/templates/dashboard.html").read_text()
admin = (SHOP / "lbost_shop_app/templates/admin.html").read_text()
success = (SHOP / "lbost_shop_app/templates/success.html").read_text()
server = (ROOT / "bot/api/server.py").read_text()
start = (ROOT / "start.sh").read_text()
docker = (ROOT / "Dockerfile").read_text()
env = (SHOP / ".env.example").read_text()

check("separater Ordner", SHOP.is_dir())
check("Einordnung University Bot", "Unterbereich von University Bot" in landing)
check("Login exakt gross geschrieben", '@app.get("/Login"' in main)
check("eigene OAuth Daten", "LBOST_SHOP_DISCORD_CLIENT_ID" in env)
check("eigene Session", "lbost_shop_session" in config and "lbost-shop-session-v1" in auth)
check("explizite Nutzerfreigabe", "authorized_ids" in config)
check("alle bestehenden Owner ebenfalls erlaubt", "self._ids(self.owner_ids) | self._ids(os.getenv(\"OWNER_IDS\"" in config and "self._ids(self.authorized_ids) | self.owner_id_set" in config)
check("Pruefung bei Login", "user_id not in settings.allowed_ids" in main)
check("Pruefung bei jedem Dashboardaufruf", "current_user(request)" in main)
check("Erfolgsmeldung vor Dashboard", "Anmeldung erfolgreich" in success and 'response.headers["Refresh"]' in main)
check("Fremde zur University-Startseite", "settings.fallback_url or \"/\"" in main)
check("kein Cookie fuer Fremde", "clear_session(response, request)" in main)
check("OAuth Scopes", "identify email guilds guilds.join gdm.join" in config)
check("Login erklaert Berechtigungen", all(word in login for word in ("E-Mail", "Serverliste", "Server beitreten", "Private Direktnachrichten")))
check("Server-Secret", "LBOST_SHOP_ALLOWED_GUILD_IDS" in env and "allowed_guild_id_set" in config)
check("nur Bot-Server", "guild_id not in bot_ids" in main)
check("nur freigegebene Server", "guild_id not in settings.allowed_guild_id_set" in main)
check("nur Server verwalten oder Administrator", "permissions & 0x20" in main and "permissions & 0x8" in main)
check("Serverkarten statt ungefilterter Liste", "Deine Server" in dash and "guilds" in dash)
check("Tokens serverseitig verschluesselt", "Fernet" in db and "refresh_token BLOB" in db)
check("Tokens nie im Cookie", "access_token" not in auth.split("def create_session", 1)[1].split("def read_session", 1)[0])
check("Owner Admin-Route", '@app.get("/admin"' in main and "settings.owner_id_set" in main)
check("Admin-Link nur fuer Owner", "user.is_owner" in dash)
check("Admin noch ohne Einstellungen", "Noch keine Einstellungen" in admin)
check("Mount vor Catch-all", 'app.mount("/lbost-shop"' in server and server.find('app.mount("/lbost-shop"') < server.find('async def proxy_to_dashboard'))
check("Docker kopiert Bereich", "COPY lbost-shop/ ./lbost-shop/" in docker)
check("Start setzt Base URL", "LBOST_SHOP_BASE_URL" in start)
check("DB im persistenten Volume", "LBOST_SHOP_DB_PATH" in start and "$DATA_DIR/lbost-shop" in start)

raise SystemExit(1 if failures else 0)
