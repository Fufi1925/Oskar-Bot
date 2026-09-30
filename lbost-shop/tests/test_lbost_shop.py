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
bot_runner = (SHOP / "run_bot.py").read_text()
bot_client = (SHOP / "lbost_shop_bot/client.py").read_text()
moderation_client = (SHOP / "lbost_shop_bot/moderation.py").read_text()
bot_runtime = bot_client + moderation_client
landing = (SHOP / "lbost_shop_app/templates/landing.html").read_text()
login = (SHOP / "lbost_shop_app/templates/login.html").read_text()
dash = (SHOP / "lbost_shop_app/templates/dashboard.html").read_text()
dash_shell = (SHOP / "lbost_shop_app/templates/dashboard_base.html").read_text()
servers_page = (SHOP / "lbost_shop_app/templates/servers.html").read_text()
guild_page = (SHOP / "lbost_shop_app/templates/guild.html").read_text()
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
check("OAuth Scopes", "identify email guilds guilds.join" in config)
check("kein Gruppen-DM-Scope", "gdm.join" not in config and "gdm.join" not in env and "Gruppen-DM" not in login)
check("Login erklaert Berechtigungen", all(word in login for word in ("E-Mail", "Serverliste", "Server beitreten", "Private Direktnachrichten")))
check("Bot-Hintergrundprozess", "python run_bot.py" in start and "LBOST_SHOP_BOT_PID" in start)
check("Bot wird nach Absturz neu gestartet", "run_lbost_shop_bot_forever" in start and "retry in 15 seconds" in start and "retry in 900 seconds" in start)
check("Bot wird sauber beendet", "Stopping LBoost Shop Bot" in start and 'kill "$LBOST_SHOP_BOT_PID"' in start)
check("Botfehler in Railway sichtbar", "run_lbost_shop_bot_forever &" in start and "> /tmp/lbost-shop-bot.log" not in start)
check("Bot bleibt ohne Portal-Intents online", "discord.PrivilegedIntentsRequired" in bot_runner and "privileged_intents=False" in bot_runner and "intents.members = privileged_intents" in bot_client)
check("Ungueltiger Token wird klar gemeldet", "discord.LoginFailure" in bot_runner and "not the client secret or application ID" in bot_runner)
check("Bot Feature-Runtime", "create_bot" in bot_runner and "commands.Bot" in bot_client)
check("Components V2", "discord.ui.LayoutView" in bot_client and "discord.ui.Container" in bot_client)
check("Ticket-System", all(term in bot_client for term in ("create_ticket", "make_transcript", "ticket_action")))
check("Moderation", all(term in bot_runtime for term in ('name=\"warn\"', 'name=\"mute\"', 'name=\"kick\"', 'name=\"ban\"', 'name=\"clearwarnings\"', 'name=\"unmute\"', 'name=\"unban\"', 'name=\"lockall\"', 'name=\"role\"')))
check("Moderation Hybrid und Components V2", "hybrid_command" in moderation_client and "hybrid_group" in moderation_client and "view=layout" in moderation_client)
check("Moderationsseite University-Stil", (SHOP / "lbost_shop_app/templates/moderation.html").is_file() and "ub-mod-stats" in (SHOP / "lbost_shop_app/templates/moderation.html").read_text())
check("Welcome und Leave", "on_member_join" in bot_client and "on_member_remove" in bot_client)
check("Reaction Roles", "toggle_role" in bot_client and 'name=\"reaction-panel\"' in bot_client)
check("Automation und Logging", "automation_worker" in bot_client and "on_message_delete" in bot_client)
check("Giveaways", "giveaway_worker" in bot_client and 'name=\"giveaway-reroll\"' in bot_client)
check("Server-Secret", "LBOST_SHOP_ALLOWED_GUILD_IDS" in env and "allowed_guild_id_set" in config)
check("nur Bot-Server", "guild_id not in bot_ids" in main)
check("nur freigegebene Server", "guild_id not in settings.allowed_guild_id_set" in main)
check("nur Server verwalten oder Administrator", "permissions & 0x20" in main and "permissions & 0x8" in main)
check("Serverkarten statt ungefilterter Liste", "Deine Server" in dash and "guilds" in dash)
check("Tokens serverseitig verschluesselt", "Fernet" in db and "refresh_token BLOB" in db)
check("Tokens nie im Cookie", "access_token" not in auth.split("def create_session", 1)[1].split("def read_session", 1)[0])
check("Owner Admin-Route", '@app.get("/admin"' in main and "settings.owner_id_set" in main)
check("Admin-Link nur fuer Owner", "user.is_owner" in dash_shell)
check("University Dashboard-Shell", all(term in dash_shell for term in ("University Bot", "Control Center", "data-global-search", "notifications", "ub-status-pill", "profile")))
check("University Logo", (SHOP / "lbost_shop_app/static/icon-192.png").is_file())
check("Responsive Dashboard-Navigation", "data-open-sidebar" in dash_shell and "data-ub-overlay" in dash_shell)
check("University Serverliste", all(term in servers_page for term in ("Mitglieder erreicht", "Server mit Bot", "data-server-search", "data-server-sort")))
check("University Serveruebersicht", all(term in guild_page for term in ("Einrichtung", "Als Nächstes", "Eingerichtet", "Noch offen", "Server-Tarif", "Sicherung")))
check("keine Emoji-Modulsymbole", all(spec in main for spec in ('"icon": "ticket"', '"icon": "shield"', '"icon": "users"', '"icon": "bolt"', '"icon": "log"', '"icon": "gift"')))
# Module icons stay monochrome SVGs. Reaction-role emoji choices are user
# content (the feature cannot be configured without an emoji), not dashboard
# decoration, and are intentionally the only exception.
ui_text = main + "".join(path.read_text() for path in (SHOP / "lbost_shop_app/templates").glob("*.html") if path.name != "reaction_roles.html")
check("keine Unicode-Emoji-Modulsymbole im Dashboard", not any(0x1F000 <= ord(char) <= 0x1FAFF for char in ui_text))
check("Server-Sicherung", "config-export" in main and "config-import" in main and "feature_history" in db)
check("Serverdetails von Discord", "with_counts" in main and "channel_count" in main and "role_count" in main)
check("Admin mit echten Zahlen", all(term in admin for term in ("aktive Sitzungen", "Letzte Änderungen", "Zugang", "ub-table")))
check("Mount vor Catch-all", 'app.mount("/lbost-shop"' in server and server.find('app.mount("/lbost-shop"') < server.find('async def proxy_to_dashboard'))
check("Docker kopiert Bereich", "COPY lbost-shop/ ./lbost-shop/" in docker)
check("Start setzt Base URL", "LBOST_SHOP_BASE_URL" in start)
check("DB im persistenten Volume", "LBOST_SHOP_DB_PATH" in start and "$DATA_DIR/lbost-shop" in start)

import re as _re
_csp = _re.search(r'"Content-Security-Policy": "([^"]+)"', main)
check("CSP ohne unsafe-inline", bool(_csp) and "unsafe-inline" not in _csp.group(1) and "style-src 'self'" in _csp.group(1))
check("kein style-Attribut im Dashboard", not any("style=" in path.read_text() for path in (SHOP / "lbost_shop_app/templates").glob("*.html")))
check("Fuellgrade als Klassen", ".ub-fill-50{" in (SHOP / "lbost_shop_app/static/css/university-dashboard.css").read_text())
check("Discord-Aufrufe gecacht", "_kurz_setzen" in main and "guild_resources" in main)
check("Formulargrenzen", "GRENZEN" in main and "spam_limit" in main and "min=\"{{ grenze[0] }}" in (SHOP / "lbost_shop_app/templates/feature.html").read_text())
check("Vorschau im Bot gerechnet", "regeln.vorschau_willkommen" in main and "from lbost_shop_app import db, regeln" in bot_client)

for vorlage in sorted((SHOP / "lbost_shop_app/templates").glob("*.html")):
    for tag in _re.findall(r"<link\b[^>]*>", vorlage.read_text()):
        if not _re.fullmatch(r'<link rel="stylesheet" href="[^"]+">', tag):
            failures.append(f"kaputtes link-Tag in {vorlage.name}: {tag}")
check("link-Tags korrekt geschlossen", not any(f.startswith("kaputtes") for f in failures))

raise SystemExit(1 if failures else 0)
