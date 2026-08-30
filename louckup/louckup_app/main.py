"""Louckup — die App.

Ablauf, wie besprochen:

    <url>/louckup              -> Loginseite (Knopf „Mit Discord anmelden")
    <url>/louckup/auth/...     -> OAuth2 mit identify, email, guilds,
                                  guilds.join, gdm.join
    danach:
      Owner  -> <url>/louckup/dashboard  (Reiter: Discord IDs,
                Roblox User, IP, Self)
      sonst  -> sofort weiter auf <url>/  (das normale Dashboard),
                ohne Session-Cookie

Der Bereich ist gemountet, nicht eingebunden: er importiert nichts aus
`phantom`, `bot` oder `dashboard` und hat seine eigene Datenbank.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from louckup_app import auth, db as dbmod
from louckup_app import discord_api as api
from louckup_app import krypto
from louckup_app.config import get_settings

log = logging.getLogger("louckup")

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))


def _format_timestamp(ts: int | None) -> str:
    if not ts:
        return "—"
    try:
        from datetime import datetime

        return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(ts)


TEMPLATES.env.filters["timestamp"] = _format_timestamp

# Modul-globale Verbindung: bei einem Mount ist `request.app` die
# Eltern-App, `app.state` der Unter-App also nicht verlässlich.
_db_conn = None
_db_lock = None


async def get_db():
    """Lazy geteilte SQLite-Verbindung für Louckup."""
    global _db_conn, _db_lock
    import asyncio

    if _db_lock is None:
        _db_lock = asyncio.Lock()
    async with _db_lock:
        if _db_conn is None:
            try:
                get_settings().db_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            _db_conn = await dbmod.connect()
            log.info("Louckup DB ready at %s", get_settings().db_path)
        return _db_conn


def render(request: Request, template_name: str, context: dict[str, Any]) -> HTMLResponse:
    return HTMLResponse(TEMPLATES.env.get_template(template_name).render(context))


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await get_db()
    except Exception as exc:  # nie den Start des Hauptbots blockieren
        log.error("Louckup DB init failed: %s", exc)
    yield
    global _db_conn
    if _db_conn is not None:
        try:
            await _db_conn.close()
        except Exception:
            pass
        _db_conn = None


# Ergebnis der letzten Pruefung des Hauptbots. Er steht nicht in der
# Datenbank, also auch sein Pruefergebnis nicht.
_primaer_status: dict[str, Any] = {}


def _token_lesen(reihe: dict[str, Any], settings) -> str | None:
    try:
        return krypto.entschluesseln(reihe["token_cipher"], settings.secret_key)
    except Exception:
        return None


# Anfaenge von Logins pro Adresse. Bewusst im Speicher und bewusst
# einfach: es geht nicht darum, einen Angriff von tausend Rechnern
# abzuwehren, sondern darum, dass ein einzelner Rechner den Bereich
# nicht mit Login-Anfragen zuschuettet.
_rate: dict[str, list[float]] = {}


def rate_ok(key: str, limit: int, window: float = 60.0) -> bool:
    """True, wenn noch innerhalb des Limits."""
    jetzt = time.time()
    treffer = [t for t in _rate.get(key, []) if jetzt - t < window]
    treffer.append(jetzt)
    _rate[key] = treffer

    # Aufraeumen kostet Zeit, also nicht bei jedem Aufruf, sondern nur
    # wenn die Kiste unuebersichtlich wird.
    if len(_rate) > 512:
        for k in [k for k, v in _rate.items() if not v or jetzt - v[-1] > window]:
            _rate.pop(k, None)

    return len(treffer) <= limit


# Der Bereich kennt keine eingebetteten Skripte und kein fremdes CSS,
# deshalb darf die Richtlinie so eng sein. Bilder kommen nur von Discord.
SICHERHEITS_HEADER = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "img-src 'self' https://cdn.discordapp.com; "
        "style-src 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'none'"
    ),
}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Louckup",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
        root_path="",
    )

    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.middleware("http")
    async def sicherheits_header(request: Request, call_next):
        antwort = await call_next(request)
        for name, wert in SICHERHEITS_HEADER.items():
            antwort.headers.setdefault(name, wert)
        # Keine Seite hier darf im Browser-Cache landen, schon gar nicht
        # auf einem geteilten Rechner.
        if (antwort.headers.get("content-type") or "").startswith("text/html"):
            antwort.headers["Cache-Control"] = "no-store, private"
        return antwort

    # ── Helfer ────────────────────────────────────────────────────

    def prefix(request: Request | None = None) -> str:
        """Mount-Pfad, z. B. "/louckup".

        Der Root-Path, den Starlette beim Mounten setzt, ist die Wahrheit
        darueber, wo die App gerade haengt. LOUCKUP_BASE_URL bleibt fuer
        absolute Adressen zustaendig (die OAuth-Redirect-URI), aber fuer
        die internen Links gilt, was der Mount sagt: ist die Variable
        leer oder falsch gesetzt, landen Redirects sonst ausserhalb des
        Bereichs und der Browser zeigt die 404-Seite des Dashboards.
        """
        scope_prefix = ""
        if request is not None:
            scope_prefix = (request.scope.get("root_path") or "").rstrip("/")
        return scope_prefix or settings.root_path.rstrip("/")

    def href(path: str, request: Request | None = None) -> str:
        """Pfad innerhalb des Mounts, damit Links auch gemountet stimmen."""
        pref = prefix(request)
        if not path.startswith("/"):
            path = "/" + path
        return f"{pref}{path}" if pref else path

    def cookie_secure(request: Request) -> bool:
        proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
        return proto == "https"

    def ctx(request: Request, **extra: Any) -> dict[str, Any]:
        user = auth.get_session_user(request)
        base = {
            "request": request,
            "brand": settings.louckup_brand_name,
            "footer": settings.louckup_footer,
            "base_url": settings.base_url,
            "root_path": prefix(request),
            "user": user,
            "avatar_url": auth.avatar_url(user["uid"], user.get("avatar")) if user else None,
            "flash": request.cookies.get("louckup_flash"),
        }
        base.update(extra)
        return base

    def flash(response: Response, message: str, request: Request | None = None) -> None:
        secure = cookie_secure(request) if request is not None else True
        safe = (
            str(message)
            .replace("„", "'")
            .replace("“", "'")
            .replace("”", "'")
            .replace("–", "-")
            .replace("—", "-")
            .encode("latin-1", errors="replace")
            .decode("latin-1")
        )[:180]
        response.set_cookie(
            "louckup_flash",
            safe,
            max_age=30,
            path=settings.louckup_cookie_path or "/",
            httponly=False,
            samesite="lax",
            secure=secure,
        )

    def clear_flash(response: Response) -> None:
        response.delete_cookie("louckup_flash", path=settings.louckup_cookie_path or "/")

    def set_session(response: Response, token: str, request: Request) -> None:
        response.set_cookie(
            settings.louckup_cookie_name,
            token,
            max_age=settings.louckup_session_max_age,
            path=settings.louckup_cookie_path or "/",
            httponly=True,
            samesite="lax",
            secure=cookie_secure(request),
        )

    def clear_session(response: Response) -> None:
        response.delete_cookie(
            settings.louckup_cookie_name, path=settings.louckup_cookie_path or "/"
        )
        response.delete_cookie("louckup_oauth_state", path=settings.louckup_cookie_path or "/")

    # ── Seiten ────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request):
        if auth.get_session_user(request):
            return RedirectResponse(url=href("/dashboard", request), status_code=302)
        return RedirectResponse(url=href("/login", request), status_code=302)

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request):
        if auth.get_session_user(request):
            return RedirectResponse(url=href("/dashboard", request), status_code=302)
        resp = render(
            request,
            "login.html",
            ctx(
                request,
                missing=settings.missing_config,
                redirect_uri=settings.oauth_redirect_uri,
                scopes=settings.scopes,
            ),
        )
        clear_flash(resp)
        return resp

    @app.get("/auth/discord")
    async def auth_discord(request: Request, force: int = 0):
        adresse = request.client.host if request.client else "unbekannt"
        if not rate_ok(f"login:{adresse}", settings.louckup_login_rate_limit):
            log.warning("Login-Rate-Limit griff fuer %s", adresse)
            return PlainTextResponse("Zu viele Versuche. Bitte warte einen Moment.", status_code=429)

        if not settings.oauth_configured:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, "OAuth ist nicht konfiguriert (CLIENT_ID / CLIENT_SECRET).", request)
            return resp
        state = auth.make_oauth_state()
        resp = RedirectResponse(
            url=auth.oauth_authorize_url(state, settings, force=bool(force)), status_code=302
        )
        # Pfad muss /louckup sein, sonst schickt der Browser den Cookie
        # beim Callback nicht mit.
        resp.set_cookie(
            "louckup_oauth_state",
            state,
            max_age=600,
            path=settings.louckup_cookie_path or "/",
            httponly=True,
            samesite="lax",
            secure=cookie_secure(request),
        )
        return resp

    @app.get("/auth/callback")
    async def auth_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
    ):
        if error:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, f"Discord-Login abgebrochen: {error_description or error}", request)
            return resp

        expected = request.cookies.get("louckup_oauth_state")
        if not code:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, "Kein OAuth-Code von Discord erhalten.", request)
            return resp
        if not state or not expected or state != expected:
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(
                resp,
                "OAuth-State ungültig oder abgelaufen. Bitte nochmal über "
                "„Mit Discord anmelden“ starten.",
                request,
            )
            return resp

        try:
            token_data = await auth.exchange_code(code, settings)
            access = token_data.get("access_token")
            if not access:
                raise HTTPException(status_code=400, detail="no_access_token")
            duser = await auth.fetch_discord_user(access)
            if not duser.get("id"):
                raise HTTPException(status_code=400, detail="no_user_id")

            user_id = int(duser["id"])
            username = duser.get("username") or "user"
            is_owner = user_id in settings.owner_ids
            expires_in = int(token_data.get("expires_in") or 0)
            granted = token_data.get("scope") or settings.scopes
            granted = granted if isinstance(granted, str) else " ".join(granted)

            db = await get_db()
            await dbmod.upsert_user(
                db,
                user_id=user_id,
                username=username,
                global_name=duser.get("global_name"),
                avatar=duser.get("avatar"),
                email=duser.get("email"),
                verified=duser.get("verified"),
                access_token=access,
                refresh_token=token_data.get("refresh_token"),
                token_expires_at=int(time.time()) + expires_in if expires_in else None,
                scopes=granted,
                is_owner=is_owner,
            )

            guilds: list[dict[str, Any]] = []
            if is_owner:
                # Nur für Owner laden — für alle anderen brauchen wir die
                # Liste nicht und wollen sie auch nicht speichern.
                try:
                    guilds = await auth.fetch_user_guilds(access)
                    await dbmod.replace_user_guilds(db, user_id, guilds)
                except Exception:
                    log.exception("Serverliste konnte nicht geladen werden")

            await dbmod.record_attempt(
                db,
                user_id=user_id,
                username=username,
                is_owner=is_owner,
                outcome="granted" if is_owner else "not_owner",
                detail=granted,
            )
        except HTTPException as exc:
            log.exception("Louckup OAuth fehlgeschlagen")
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, f"Login fehlgeschlagen: {exc.detail}", request)
            return resp
        except Exception as exc:
            log.exception("Louckup OAuth Fehler")
            resp = RedirectResponse(url=href("/login", request), status_code=302)
            flash(resp, f"Login-Fehler: {type(exc).__name__}: {exc}"[:140], request)
            return resp

        # Nicht-Owner: kein Session-Cookie, sofort zurück aufs Dashboard.
        if not is_owner:
            log.info("Louckup: %s (%s) ist kein Owner — weiter aufs Dashboard", username, user_id)
            resp = RedirectResponse(url=settings.louckup_fallback_url or "/", status_code=302)
            clear_session(resp)
            return resp

        resp = RedirectResponse(url=href("/dashboard", request), status_code=302)
        set_session(resp, auth.create_session_token(duser, settings), request)
        resp.delete_cookie("louckup_oauth_state", path=settings.louckup_cookie_path or "/")
        return resp

    # Die Reiter. 1-3 sind Platzhalter, "Self" zeigt die eigenen Daten —
    # und zwar nur die des eingeloggten Kontos, nie die der anderen
    # Owner. Jeder sieht ausschliesslich seinen eigenen Datensatz.
    TABS: tuple[tuple[str, str], ...] = (
        ("discord-ids", "Discord IDs"),
        ("roblox", "Roblox User"),
        ("ip", "IP"),
        ("self", "Self"),
        ("einstellungen", "Einstellungen"),
    )
    TAB_TITEL = dict(TABS)

    # Ein Satz unter dem Seitentitel, gruppierte Reiter und ein Symbol
    # je Reiter — so sieht die Seitenleiste aus wie im Dashboard.
    TAB_UNTERTITEL = {
        "discord-ids": "Eine Discord-ID eingeben. Alle eingetragenen Bots suchen mit.",
        "roblox": "Noch leer.",
        "ip": "Noch leer.",
        "self": "Deine eigenen Daten aus diesem Bereich.",
        "einstellungen": "Bots eintragen, prüfen und entfernen.",
    }
    TAB_GRUPPEN: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Suche", ("discord-ids", "roblox", "ip")),
        ("Konto", ("self",)),
        ("Bereich", ("einstellungen",)),
    )
    TAB_SYMBOL = {
        "discord-ids": "ausweis",
        "roblox": "baustein",
        "ip": "globus",
        "self": "person",
        "einstellungen": "zahnrad",
    }

    # ── Schutz gegen fremd ausgeloeste Formulare ────────────────────
    #
    # Die Formulare hier wirken: sie tragen Bot-Tokens ein und loeschen
    # sie wieder. Ohne diesen Vergleich koennte jede fremde Seite, auf
    # der ein eingeloggter Owner gerade ist, im Hintergrund einen
    # Bot hinzufuegen. Der Wert steht verschluesselt im Session-Cookie
    # und zusaetzlich im Formular — eine fremde Seite kann das Cookie
    # nicht lesen, also kann sie den Wert nicht mitliefern.

    def csrf(request: Request) -> str:
        roh = request.cookies.get(settings.louckup_cookie_name) or ""
        return hashlib.sha256(f"louckup-csrf|{roh}".encode()).hexdigest()[:32]

    def csrf_stimmt(request: Request, wert: str | None) -> bool:
        return hmac.compare_digest(str(wert or ""), csrf(request))

    # ── Bots ───────────────────────────────────────────────────────

    # Wie lange das Ergebnis einer Hauptbot-Abfrage gilt. Der Hauptbot
    # wird beim Oeffnen der Einstellungen von selbst geholt — ohne
    # diese Frist wuerde jeder Seitenaufruf Discord anfragen.
    PRIMAER_CACHE = 300

    async def hauptbot_info(erzwingen: bool = False) -> dict[str, Any]:
        """Name, Bild und Zustand des Hauptbots — von Discord geholt.

        Der Token steht in `TOKEN`, der Name nicht. Also wird er geholt,
        damit der Hauptbot in der Liste aussieht wie die anderen: Bild,
        Name, Anwendungsname. Schlaegt die Abfrage fehl, bleibt der alte
        Stand stehen und der Fehler erscheint daneben.
        """
        global _primaer_status

        jetzt = time.time()
        alt = _primaer_status or {}
        if (
            not erzwingen
            and alt.get("ts")
            and (jetzt - float(alt["ts"])) < PRIMAER_CACHE
            and not alt.get("nur_fehler")
        ):
            return alt

        token = settings.primary_bot_token
        if not token:
            _primaer_status = {
                "ok": False,
                "text": "In TOKEN steht kein Token.",
                "ts": int(jetzt),
            }
            return _primaer_status

        try:
            info = await api.bot_selbst(token, settings.louckup_lookup_timeout)
            anwendung = await api.anwendung(token, settings.louckup_lookup_timeout) or {}
        except Exception as exc:
            _primaer_status = {
                "ok": False,
                "text": f"{type(exc).__name__}: {exc}",
                "ts": int(jetzt),
                "nur_fehler": True,
            }
            return _primaer_status

        if not info or not info.get("id"):
            _primaer_status = {
                "ok": False,
                "text": "Token gilt, liefert aber kein Bot-Konto.",
                "ts": int(jetzt),
                "nur_fehler": True,
            }
            return _primaer_status

        _primaer_status = {
            "ok": True,
            "text": "Token gilt.",
            "ts": int(jetzt),
            "discord_id": info.get("id"),
            "username": info.get("username"),
            "name": anwendung.get("name") or info.get("global_name") or info.get("username"),
            "application": anwendung.get("name"),
            "bild": api.bot_bild(info.get("id"), info.get("avatar"), 64),
        }
        return _primaer_status

    async def bots_mit_token() -> list[dict[str, Any]]:
        """Hauptbot (aus TOKEN) plus alle gespeicherten Bots."""
        liste: list[dict[str, Any]] = []

        if settings.louckup_primary_bot_enabled and settings.primary_bot_token:
            liste.append(
                {
                    "id": 0,
                    "label": settings.louckup_primary_bot_label,
                    "token": settings.primary_bot_token,
                    "primary": True,
                }
            )

        db = await get_db()
        for reihe in await dbmod.list_bots(db):
            try:
                token = krypto.entschluesseln(reihe["token_cipher"], settings.secret_key)
            except Exception as exc:
                # Ein kaputter Eintrag darf die Suche nicht stoppen.
                log.error("Bot %s: Token nicht lesbar: %s", reihe.get("id"), exc)
                continue
            liste.append(
                {
                    **reihe,
                    "token": token,
                    "primary": False,
                    "bild": api.bot_bild(reihe.get("discord_id"), reihe.get("avatar"), 64),
                }
            )
        return liste

    async def suchen(user_id: int) -> dict[str, Any]:
        """Eine Discord-ID ueber alle eingetragenen Bots suchen.

        Ergebnis sind oeffentliche Profildaten und — fuer die Server,
        in denen die eigenen Bots stecken — Mitgliedschaft, Rollen,
        Nickname und Beitrittsdatum. Keine E-Mail-Adressen: die gibt
        Discord ausschliesslich ueber das OAuth-Token der jeweiligen
        Person heraus, und das steht uns nicht zu.
        """
        bots = await bots_mit_token()
        ergebnis: dict[str, Any] = {
            "user": None,
            "treffer": [],
            "fehler": [],
            "anfragen": 0,
            "gebremst": False,
            "bots": len(bots),
            "summe_treffer": 0,
            "summe_server": 0,
        }
        if not bots:
            ergebnis["fehler"].append("Kein Bot eingetragen.")
            return ergebnis

        # Profil: erster Bot, der etwas liefert.
        for bot in bots:
            try:
                ergebnis["anfragen"] += 1
                profil = await api.profil(bot["token"], user_id, settings.louckup_lookup_timeout)
                if profil:
                    ergebnis["user"] = profil
                    ergebnis["avatar"] = api.avatar_url(profil)
                    ergebnis["abzeichen"] = api.abzeichen(profil.get("public_flags"))
                    erstellt = api.kontostand_aus_snowflake(profil.get("id"))
                    ergebnis["erstellt"] = (
                        erstellt.strftime("%d.%m.%Y %H:%M") if erstellt else "—"
                    )
                    ergebnis["seit"] = api.alter(erstellt)
                    ergebnis["farbe"] = api.farbe_als_hex(profil.get("accent_color"))
                    break
            except api.AnfrageFehler as exc:
                ergebnis["fehler"].append(f"{bot['label']}: {exc}")
        if not ergebnis["user"]:
            return ergebnis

        grenze = settings.louckup_lookup_max_requests
        sema = asyncio.Semaphore(5)

        for bot in bots:
            try:
                server = await api.bot_server(bot["token"], settings.louckup_lookup_timeout)
            except api.AnfrageFehler as exc:
                ergebnis["fehler"].append(f"{bot['label']}: {exc}")
                continue

            eintrag: dict[str, Any] = {
                "bot": bot["label"],
                "bild": bot.get("bild"),
                "server": len(server),
                "treffer": [],
                "ohne": [],
                "hauptbot": bool(bot.get("primary")),
            }
            ergebnis["summe_server"] += len(server)

            async def pruefe(guild: dict[str, Any]) -> tuple[dict, str, Any]:
                """Server -> (Server, Zustand, Mitgliedsdaten).

                Drei Zustaende: „dabei", „nicht dabei" und „nicht geprueft"
                — das letzte, wenn die Obergrenze erreicht war. Die Liste
                zeigt alle Server, also muss sie auch sagen duerfen, wo
                sie nichts weiss.
                """
                try:
                    gid = int(guild.get("id"))
                except (TypeError, ValueError):
                    return guild, "nicht geprueft", None
                if ergebnis["anfragen"] >= grenze:
                    ergebnis["gebremst"] = True
                    return guild, "nicht geprueft", None
                async with sema:
                    ergebnis["anfragen"] += 1
                    try:
                        mitglied = await api.mitglied(
                            bot["token"], gid, user_id, settings.louckup_lookup_timeout
                        )
                    except api.AnfrageFehler as exc:
                        return guild, "fehler", str(exc)
                if not mitglied:
                    return guild, "nicht dabei", None
                namen = (
                    await api.rollen(bot["token"], gid, settings.louckup_lookup_timeout)
                    if mitglied.get("roles")
                    else {}
                )
                return guild, "dabei", (mitglied, namen)

            geprueft = await asyncio.gather(*[pruefe(g) for g in server])

            for guild, zustand, daten in geprueft:
                if zustand != "dabei":
                    eintrag["ohne"].append(
                        {
                            "server": guild.get("name") or str(guild.get("id")),
                            "server_id": str(guild.get("id")),
                            "symbol": api.server_bild(guild),
                            "zustand": zustand,
                        }
                    )
                    continue

                mitglied, namen = daten
                eintrag["treffer"].append(
                    {
                        "server": guild.get("name") or str(guild.get("id")),
                        "server_id": str(guild.get("id")),
                        "symbol": api.server_bild(guild),
                        "nick": mitglied.get("nick"),
                        "beitritt": api.zeitpunkt(mitglied.get("joined_at")),
                        "stumm_bis": api.zeitpunkt(
                            mitglied.get("communication_disabled_until")
                        ),
                        "boost_seit": api.zeitpunkt(mitglied.get("premium_since")),
                        "ausstehend": bool(mitglied.get("pending")),
                        "rollen": api.rollen_zeigen(mitglied, namen),
                    }
                )

            ergebnis["summe_treffer"] += len(eintrag["treffer"])
            ergebnis["treffer"].append(eintrag)

        return ergebnis

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request):
        # Erst die Session pruefen und dann weiterleiten. Ohne das wuerde
        # ein nicht angemeldeter Besucher zwei Spruenge machen
        # (/dashboard -> /dashboard/self -> /login) statt einem.
        if not auth.get_session_user(request):
            return RedirectResponse(url=href("/login", request), status_code=302)
        return RedirectResponse(url=href("/dashboard/self", request), status_code=302)

    @app.get("/dashboard/{tab}", response_class=HTMLResponse)
    async def dashboard_tab(request: Request, tab: str):
        user = auth.get_session_user(request)
        if not user:
            return RedirectResponse(url=href("/login", request), status_code=302)

        # Zweite Prüfung: die Owner-Liste kann sich geändert haben, während
        # jemand eingeloggt war. Ein Cookie allein ist keine Berechtigung.
        if int(user["uid"]) not in settings.owner_ids:
            resp = RedirectResponse(url=settings.louckup_fallback_url or "/", status_code=302)
            clear_session(resp)
            return resp

        if tab not in TAB_TITEL:
            return RedirectResponse(url=href("/dashboard/self", request), status_code=302)

        uid = int(user["uid"])
        db = await get_db()
        record = await dbmod.get_user(db, uid)
        # Serverliste nur laden, wenn sie auch gebraucht wird.
        # Auf Self nur die eigenen Daten — inklusive der eigenen Logins.
        guilds = await dbmod.list_user_guilds(db, uid) if tab == "self" else []
        logins = await dbmod.own_attempts(db, uid, limit=10) if tab == "self" else []

        extra: dict[str, Any] = {
            "csrf": csrf(request),
            "tab_untertitel": TAB_UNTERTITEL.get(tab, ""),
            "tab_gruppen": TAB_GRUPPEN,
            "tab_symbol": TAB_SYMBOL,
            "tab_titel": TAB_TITEL,
        }

        if tab == "einstellungen":
            reihen = await dbmod.list_bots(db)
            for reihe in reihen:
                # Der Token selbst kommt nie ins HTML, nur die Maske.
                reihe["maske"] = krypto.maske(_token_lesen(reihe, settings) or "")
                reihe["bild"] = api.bot_bild(reihe.get("discord_id"), reihe.get("avatar"), 64)
            extra["bots"] = reihen
            extra["hauptbot"] = {
                "label": settings.louckup_primary_bot_label,
                "aktiv": bool(settings.primary_bot_token) and settings.louckup_primary_bot_enabled,
                "status": await hauptbot_info(),
            }

        if tab == "discord-ids":
            gesucht = (request.query_params.get("id") or "").strip()
            extra["gesucht"] = gesucht
            if gesucht and gesucht.isdigit():
                extra["ergebnis"] = await suchen(int(gesucht))
            elif gesucht:
                extra["ergebnis"] = {
                    "user": None,
                    "treffer": [],
                    "anfragen": 0,
                    "gebremst": False,
                    "fehler": ["Das ist keine Zahl — eine Discord-ID besteht nur aus Ziffern."],
                }

        resp = render(
            request,
            "dashboard.html",
            ctx(
                request,
                tab=tab,
                tab_title=TAB_TITEL[tab],
                tabs=TABS,
                record=record,
                guilds=guilds,
                logins=logins,
                scopes=(record or {}).get("scopes") or settings.scopes,
                **extra,
            ),
        )
        # Nichts hier darf im Browser-Cache landen, auch nicht auf
        # geteilten Rechnern.
        clear_flash(resp)
        return resp

    # ── Einstellungen: Bots verwalten ──────────────────────────────

    def _flash_zurueck(request: Request, text: str) -> RedirectResponse:
        antwort = RedirectResponse(url=href("/dashboard/einstellungen", request), status_code=303)
        flash(antwort, text, request)
        return antwort

    def _nur_owner(request: Request) -> bool:
        user = auth.get_session_user(request)
        return bool(user) and int(user["uid"]) in settings.owner_ids

    @app.post("/dashboard/einstellungen/bots")
    async def bot_hinzufuegen(request: Request):
        if not _nur_owner(request):
            return RedirectResponse(url=href("/login", request), status_code=302)

        formular = await request.form()
        if not csrf_stimmt(request, formular.get("csrf")):
            return _flash_zurueck(request, "Formular abgelaufen. Bitte nochmal.")

        # Nur der Token. Name und Bild holt der Bereich selbst bei
        # Discord — zweimal tippen, was dort schon steht, waere eine
        # Fehlerquelle mehr (und ein Name, der nicht zum Konto passt).
        token = str(formular.get("token") or "").strip()
        if not token:
            return _flash_zurueck(request, "Kein Token eingegeben.")
        if len(token) < 30:
            return _flash_zurueck(
                request, "Das ist zu kurz fuer einen Bot-Token. Bitte vollstaendig einfuegen."
            )

        try:
            info = await api.bot_selbst(token, settings.louckup_lookup_timeout)
        except api.AnfrageFehler as exc:
            return _flash_zurueck(request, f"Token abgelehnt: {exc}")
        except Exception as exc:
            return _flash_zurueck(request, f"Token nicht pruefbar: {type(exc).__name__}: {exc}")

        if not info or not info.get("id"):
            return _flash_zurueck(request, "Token gilt, liefert aber kein Bot-Konto.")

        anwendung = await api.anwendung(token, settings.louckup_lookup_timeout) or {}
        db = await get_db()
        try:
            geheim = krypto.verschluesseln(token, settings.secret_key)
        except krypto.KryptoFehler as exc:
            return _flash_zurueck(request, str(exc))

        # Der Anwendungsname ist das, was man im Entwicklerportal sieht
        # und damit das, wonach man den Bot in der Liste sucht. Erst
        # danach kommt der Kontoname.
        name = anwendung.get("name") or info.get("global_name") or info.get("username") or "Bot"
        user = auth.get_session_user(request)
        try:
            await dbmod.add_bot(
                db,
                label=name,
                discord_id=int(info["id"]),
                username=info.get("username"),
                application=anwendung.get("name"),
                avatar=info.get("avatar"),
                token_cipher=geheim,
                added_by=int(user["uid"]),
            )
        except Exception as exc:
            return _flash_zurueck(request, f"Speichern fehlgeschlagen: {exc}")

        await dbmod.record_attempt(
            db, user_id=int(user["uid"]), username=user.get("username"),
            is_owner=True, outcome="bot_added", detail=name,
        )
        return _flash_zurueck(request, f"{name} eingetragen.")

    @app.post("/dashboard/einstellungen/bots/{bot_id}/pruefen")
    async def bot_pruefen(request: Request, bot_id: int):
        if not _nur_owner(request):
            return RedirectResponse(url=href("/login", request), status_code=302)

        formular = await request.form()
        if not csrf_stimmt(request, formular.get("csrf")):
            return _flash_zurueck(request, "Formular abgelaufen. Bitte nochmal.")

        db = await get_db()
        reihe = await dbmod.get_bot(db, bot_id)
        if not reihe:
            return _flash_zurueck(request, "Dieser Eintrag existiert nicht mehr.")

        token = _token_lesen(reihe, settings)
        if not token:
            return _flash_zurueck(request, "Token nicht lesbar (Schluessel geaendert?)")

        try:
            info = (await api.bot_selbst(token, settings.louckup_lookup_timeout)) or {}
            anwendung = await api.anwendung(token, settings.louckup_lookup_timeout) or {}
            anwendungsname = anwendung.get("name")
            # Der Name folgt dem Konto, solange er von selbst kam. Stand
            # dort schon etwas Eigenes, bleibt es stehen.
            alter_name = reihe.get("label")
            automatisch = alter_name in (
                None, "", reihe.get("application"), reihe.get("username"),
            )
            await dbmod.note_check(
                db, bot_id, ok=True, text="Token gilt.",
                discord_id=int(info["id"]) if info.get("id") else None,
                username=info.get("username"),
                application=anwendungsname,
                avatar=info.get("avatar"),
                label=(
                    anwendungsname or info.get("global_name") or info.get("username")
                    if automatisch else None
                ),
            )
            return _flash_zurueck(request, f"{reihe['label']}: Token gilt.")
        except api.AnfrageFehler as exc:
            await dbmod.note_check(db, bot_id, ok=False, text=str(exc))
            return _flash_zurueck(request, f"{reihe['label']}: {exc}")
        except Exception as exc:
            await dbmod.note_check(db, bot_id, ok=False, text=f"{type(exc).__name__}: {exc}")
            return _flash_zurueck(request, f"{reihe['label']}: {type(exc).__name__}: {exc}")

    @app.post("/dashboard/einstellungen/bots/{bot_id}/entfernen")
    async def bot_entfernen(request: Request, bot_id: int):
        if not _nur_owner(request):
            return RedirectResponse(url=href("/login", request), status_code=302)

        formular = await request.form()
        if not csrf_stimmt(request, formular.get("csrf")):
            return _flash_zurueck(request, "Formular abgelaufen. Bitte nochmal.")

        db = await get_db()
        reihe = await dbmod.get_bot(db, bot_id)
        weg = await dbmod.remove_bot(db, bot_id)
        user = auth.get_session_user(request)
        if reihe and weg:
            await dbmod.record_attempt(
                db, user_id=int(user["uid"]), username=user.get("username"),
                is_owner=True, outcome="bot_removed", detail=str(reihe.get("label")),
            )
        return _flash_zurueck(request, f"{reihe['label'] if reihe else 'Eintrag'} entfernt.")

    @app.post("/dashboard/einstellungen/hauptbot/pruefen")
    async def hauptbot_pruefen(request: Request):
        global _primaer_status
        if not _nur_owner(request):
            return RedirectResponse(url=href("/login", request), status_code=302)

        formular = await request.form()
        if not csrf_stimmt(request, formular.get("csrf")):
            return _flash_zurueck(request, "Formular abgelaufen. Bitte nochmal.")

        zustand = await hauptbot_info(erzwingen=True)
        if zustand.get("ok"):
            return _flash_zurueck(request, f"{zustand.get('name')}: Token gilt.")
        return _flash_zurueck(request, zustand.get("text") or "Unbekannter Zustand.")

    @app.get("/logout")
    async def logout(request: Request):
        resp = RedirectResponse(url=href("/login", request), status_code=302)
        clear_session(resp)
        return resp

    @app.get("/healthz")
    async def healthz():
        return JSONResponse(
            {
                "ok": True,
                "area": "louckup",
                "oauth_configured": settings.oauth_configured,
                "owners": len(settings.owner_ids),
                "secret_is_dev": settings.secret_is_dev,
                "base_url": settings.base_url,
            }
        )

    return app


app = create_app()
