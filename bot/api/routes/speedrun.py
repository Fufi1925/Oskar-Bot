"""
Speedrun: einen Server in einem Rutsch aufbauen.

Das Dashboard redet nur mit dem University Bot, nie direkt mit dem
Template-Bot. Zwei Gruende:

  * Die Absicherung steht hier schon. Jede /api/v1-Route haengt hinter
    verify_api_key; der Template-Bot muesste sonst eine zweite,
    parallele Zugangspruefung bekommen.
  * Der Browser darf den Partner-Token nie sehen. Wuerde das Dashboard
    den Template-Bot direkt aufrufen, muesste der Token entweder in den
    Browser oder in eine zweite Proxy-Schicht -- diese Route ist die
    zweite Schicht.

Der Ablauf in Stufen, wie ihn das Dashboard abbildet:

  1. /precheck   Sind beide Bots auf dem Server?
  2. /templates  Welche Templates darf dieser Nutzer waehlen?
  3. /start      Template-Bot baut. Antwortet sofort.
  4. /{id}       Fortschritt, Zeile fuer Zeile, fuers Terminal.

Die Uebergabe an den University Bot -- Verify, Anti-Nuke, Tickets --
kommt als zweiter Schritt. Was hier schon vorbereitet ist: der Bau
sammelt am Ende alle Rollen- und Kanalnamen ein, damit der Hauptbot
danach nicht raten muss.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import TYPE_CHECKING, Any

import aiohttp
from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_bot
from utils import premium_store as store
from utils import speedrun_access as access
from utils import speedrun_handover as handover

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

PARTNER_TOKEN_ENV = "PREMIUM_PARTNER_TOKEN"

# Welche Templates in der Beta gebaut werden duerfen -- auch fuer
# Premium.
#
# Die uebrigen sind fertig, aber noch nicht auf einem echten Server
# gelaufen, und ein halb geprueftes Template auf einem fremden Server
# anzuwenden laesst sich nicht rueckgaengig machen.
#
# Die drei neuen sind bewusst dabei: sie bestehen dieselben Pruefungen
# wie community (Bau-Simulation, Uebergabe-Landkarte, Rechte je
# Kategorie), und sie decken die Faelle ab, an denen die starre
# Schritt-Liste vorher aufgefallen ist -- "minimal" hat weder Verify
# noch Tickets noch Rollen-Vergabe.
BETA_TEMPLATES = {"community", "music", "dev", "minimal"}


def _template_base() -> str:
    return (os.getenv("TEMPLATE_BOT_URL") or "").strip().rstrip("/")


def _partner_token() -> str:
    return os.getenv(PARTNER_TOKEN_ENV, "").strip()


def _require_link() -> tuple[str, str]:
    """Adresse und Token, oder eine klare Fehlermeldung."""

    base = _template_base()
    token = _partner_token()
    if not base or not token:
        missing = []
        if not base:
            missing.append("TEMPLATE_BOT_URL")
        if not token:
            missing.append(PARTNER_TOKEN_ENV)
        raise HTTPException(
            status_code=503,
            detail=(
                "Die Verbindung zum Template-Bot ist nicht eingerichtet. "
                f"Fehlt in Railway: {', '.join(missing)}."
            ),
        )
    return base, token


async def _call_template(
    method: str, path: str, *, payload: dict | None = None, timeout: int = 15
) -> tuple[int, Any]:
    """Eine Anfrage an den Template-Bot.

    Netzwerkfehler werden zu 502 statt zu einem Traceback: das
    Dashboard soll "Template-Bot nicht erreichbar" anzeigen koennen,
    nicht eine leere Seite.
    """

    base, token = _require_link()
    url = f"{base}{path}"
    headers = {"X-Partner-Token": token}

    try:
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.request(
                method, url, headers=headers, json=payload
            ) as response:
                try:
                    body = await response.json()
                except Exception:
                    body = {"error": (await response.text())[:200]}
                return response.status, body
    except aiohttp.ClientError as exc:
        raise HTTPException(status_code=502, detail=_why_unreachable(exc, url)) from exc
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Der Template-Bot hat auf {url} nicht innerhalb von "
                f"{timeout} Sekunden geantwortet. Läuft der Dienst gerade hoch?"
            ),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Template-Bot antwortet nicht: {type(exc).__name__}: {exc}",
        ) from exc


def _why_unreachable(exc: Exception, url: str) -> str:
    """Aus einem Verbindungsfehler eine Anweisung machen.

    "Template-Bot nicht erreichbar" war die alte Meldung, und die ist
    wertlos: sie nennt drei voellig verschiedene Ursachen beim selben
    Namen. Auf Railway sind es praktisch immer diese hier, und sie
    lassen sich am Fehler unterscheiden.
    """

    errno = getattr(getattr(exc, "os_error", None), "errno", None)

    # -2/-5 = getaddrinfo: den Namen gibt es nicht.
    if isinstance(exc, aiohttp.ClientConnectorDNSError) or errno in (-2, -5):
        return (
            f"Die Adresse »{url}« gibt es nicht. Prüfe TEMPLATE_BOT_URL in "
            "Railway: sie muss auf den Template-Bot zeigen, also etwa "
            "http://<dienstname>.railway.internal:8080 — mit Port, denn ohne "
            "ihn versucht http Port 80."
        )

    # 111 = ECONNREFUSED: der Name stimmt, aber dort horcht nichts.
    if errno == 111 or isinstance(exc, ConnectionRefusedError):
        return (
            f"Unter »{url}« nimmt niemand die Verbindung an. Zwei häufige "
            "Gründe: der Template-Bot läuft nicht — oder er lauscht nur auf "
            "IPv4. Railways internes Netz ist IPv6-only, der Dienst muss "
            "deshalb auf :: (bzw. auf beiden Familien) horchen."
        )

    return f"Template-Bot nicht erreichbar ({url}): {exc}"


def _has_premium(user_id: str) -> bool:
    if not user_id:
        return False
    try:
        state = store.status(user_id, product="template_bot")
        return bool(state.get("active"))
    except Exception:
        # Im Zweifel kein Premium: eine kaputte Abfrage darf niemandem
        # etwas freischalten, das er nicht bezahlt hat.
        return False


# --------------------------------------------------------------------- #
# 1. Vorbedingungen
# --------------------------------------------------------------------- #


@router.get("/{guild_id}/precheck", summary="Sind beide Bots bereit?")
async def precheck(
    guild_id: int,
    user_id: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    """
    Prueft alles, was vor dem ersten Klick stimmen muss.

    Jede Bedingung kommt einzeln zurueck, damit das Dashboard genau
    sagen kann, was fehlt -- "irgendetwas stimmt nicht" ist die
    nutzloseste aller Fehlermeldungen.
    """

    guild = bot.get_guild(guild_id)
    main_present = guild is not None

    # Rechte des University Bots. Ohne die scheitert Schritt 2 mitten
    # drin, und dann steht der Server halb eingerichtet da.
    main_can_manage = False
    if guild is not None and guild.me is not None:
        perms = guild.me.guild_permissions
        main_can_manage = bool(
            perms.administrator
            or (perms.manage_roles and perms.manage_channels)
        )

    # Der Template-Bot wird gefragt, ob *er* auf dem Server ist -- das
    # kann der University Bot nicht von sich aus wissen.
    template_present = False
    template_reachable = False
    template_detail = ""
    try:
        status_code, body = await _call_template(
            "POST",
            "/internal/speedrun/precheck",
            payload={"guild_id": str(guild_id)},
            timeout=10,
        )
        template_reachable = True
        if status_code == 200:
            template_present = bool(body.get("present"))
            template_detail = str(body.get("detail") or "")
        else:
            template_detail = str(body.get("error") or f"HTTP {status_code}")
    except HTTPException as exc:
        template_detail = str(exc.detail)

    premium = _has_premium(str(user_id or ""))

    ready = main_present and main_can_manage and template_present

    return {
        "ready": ready,
        "checks": {
            "main_bot_present": main_present,
            "main_bot_can_manage": main_can_manage,
            "template_bot_present": template_present,
            "template_bot_reachable": template_reachable,
        },
        "premium": premium,
        "guild_name": getattr(guild, "name", ""),
        "detail": template_detail,
        # Die Einladung, damit das Dashboard direkt einen Knopf anbieten
        # kann statt "lade den Bot halt ein".
        "template_invite": _template_invite(),
    }


def _template_invite() -> str:
    client_id = (os.getenv("PARTNER_BOT_CLIENT_ID") or "").strip()
    if not client_id:
        return ""
    return (
        f"https://discord.com/oauth2/authorize?client_id={client_id}"
        "&scope=bot%20applications.commands&permissions=8"
    )


# --------------------------------------------------------------------- #
# 2. Templates
# --------------------------------------------------------------------- #


@router.get("/templates", summary="Waehlbare Templates")
async def templates(user_id: str = ""):
    """
    Die Template-Liste, angereichert um "darf dieser Nutzer das?".

    Die Sperre wird hier entschieden und nicht im Dashboard: eine
    Prüfung, die nur im Browser stattfindet, ist keine.
    """

    status_code, body = await _call_template(
        "GET", "/internal/speedrun/templates", timeout=10
    )
    if status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )

    premium = _has_premium(str(user_id or ""))
    items = []
    for entry in body.get("templates", []):
        key = str(entry.get("key") or "")
        in_beta = key in BETA_TEMPLATES

        if not in_beta:
            reason = "In der Beta ist erst dieses eine Template freigegeben."
        elif entry.get("premium") and not premium:
            reason = "Nur mit Premium."
        else:
            reason = ""

        items.append({**entry, "available": not reason, "locked_reason": reason})

    return {"templates": items, "premium": premium, "beta": sorted(BETA_TEMPLATES)}


# --------------------------------------------------------------------- #
# 2b. Die Code-Sperre
# --------------------------------------------------------------------- #
#
# Der Reiter ist zu, bis jemand den Beta-Code eingibt. Freigeschaltet
# wird ein *Server*, nicht ein Nutzer -- der Speedrun baut einen
# konkreten Server um.
#
# Die Pruefung liegt hier und nicht nur im Browser. Eine Sperre, die
# allein im Dashboard sitzt, ist keine: /start ist eine HTTP-Route, und
# curl fragt nicht nach einem Overlay.


@router.get("/{guild_id}/access", summary="Ist der Reiter für diesen Server offen?")
async def access_state(guild_id: int):
    """Der Zustand -- das Erste, was der Reiter beim Öffnen fragt."""

    state = access.state(guild_id)
    # Der Code selbst wird hier nicht mitgeschickt, auch nicht gehasht:
    # er steht auf der Seite im Klartext daneben, sobald er gilt, aber
    # eine Antwort, die ihn verraet, waere eine Vorlage zum Raten.
    return {
        "unlocked": state["unlocked"],
        "banned": state["banned"],
        "ban_reason": state.get("ban_reason", ""),
        "unlocked_at": state.get("unlocked_at"),
        "runs": state.get("runs", 0),
    }


@router.post("/{guild_id}/access", summary="Reiter mit dem Code freischalten")
async def access_unlock(guild_id: int, data: dict):
    """Den Code prüfen und den Server freischalten.

    Falsche Eingaben werden mitgeschrieben. Nicht um Leute zu
    verfolgen, sondern weil ein Server mit vierzig Fehlversuchen etwas
    anderes ist als einer mit einem Vertipper -- und das sieht man im
    Admin-Panel sonst nicht.
    """

    result = access.unlock(
        guild_id,
        str(data.get("code") or ""),
        str(data.get("user_id") or ""),
    )
    if not result["ok"]:
        raise HTTPException(status_code=403, detail=result["reason"])

    return {"unlocked": True, "already": result.get("already", False)}


def _require_unlocked(guild_id: int) -> None:
    """Abbrechen, wenn der Server nicht frei ist.

    Steht vor jedem Schritt, der etwas bewirkt. Ohne diese Zeile waere
    die Sperre eine Anzeige und keine Sperre.
    """

    state = access.state(guild_id)
    if state["banned"]:
        raise HTTPException(
            status_code=403,
            detail=(
                "Für diesen Server ist der Speedrun gesperrt. "
                + (state.get("ban_reason") or "Melde dich beim Team.")
            ),
        )
    if not state["unlocked"]:
        raise HTTPException(
            status_code=403,
            detail="Der Speedrun ist für diesen Server nicht freigeschaltet.",
        )


# --------------------------------------------------------------------- #
# 3. Start
# --------------------------------------------------------------------- #


@router.post("/{guild_id}/start", summary="Speedrun starten")
async def start(
    guild_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """Startet den Bau beim Template-Bot. Antwortet sofort."""

    # Zuerst: darf dieser Server überhaupt?
    _require_unlocked(guild_id)

    template_key = str(data.get("template") or "").strip()
    user_id = str(data.get("user_id") or "").strip()

    if template_key not in BETA_TEMPLATES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"»{template_key}« ist in der Beta nicht freigegeben. "
                f"Verfügbar: {', '.join(sorted(BETA_TEMPLATES))}."
            ),
        )

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der University Bot ist nicht auf diesem Server.",
        )

    options = dict(data.get("options") or {})

    # ------------------------------------------------------------------ #
    # "Alles löschen" -- der einzige Schritt, der Bestehendes zerstört
    # ------------------------------------------------------------------ #
    #
    # Im Aufbau-Modus kommt das Template zum Server dazu. Mit rebuild
    # wird vorher jeder Kanal und jede Rolle gelöscht, die der Bot
    # anfassen darf -- auch die, die nichts mit dem Template zu tun
    # haben. Nachrichtenverläufe sind danach weg, endgültig; Discord
    # hat keinen Papierkorb.
    #
    # Deshalb reicht ein Häkchen im Browser hier nicht. Wer den
    # Endpunkt direkt mit curl aufruft, umgeht jede Abfrage im
    # Dashboard, und ein "options.rebuild=true" ist schnell getippt.
    # Die Bestätigung wird darum hier verlangt: der Servername, genau
    # so geschrieben, wie er in Discord steht.
    if options.get("rebuild"):
        confirm = str(data.get("confirm") or "").strip()
        if confirm != guild.name.strip():
            raise HTTPException(
                status_code=400,
                detail=(
                    "»Alles löschen« braucht eine Bestätigung: schicke den "
                    "Servernamen genau so mit, wie er in Discord steht. "
                    f"Erwartet: »{guild.name}«."
                ),
            )

        # Was der Bot nicht löschen kann, bleibt stehen -- und dann
        # steht der Server halb leer da. Lieber vorher sagen.
        me = guild.me
        perms = me.guild_permissions if me is not None else None
        if perms is None or not (
            perms.administrator or (perms.manage_channels and perms.manage_roles)
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Für »Alles löschen« braucht der Bot »Kanäle verwalten« "
                    "und »Rollen verwalten«."
                ),
            )

    status_code, body = await _call_template(
        "POST",
        "/internal/speedrun/start",
        payload={
            "guild_id": str(guild_id),
            "template": template_key,
            "options": options,
            "user_id": user_id,
        },
        timeout=20,
    )

    if status_code != 200:
        raise HTTPException(
            status_code=status_code if status_code in (400, 404, 409) else 502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )

    # Ab hier wartet der Bot selbst auf das Ende des Baus und richtet
    # danach ein. Der Browser ruft /finish nicht mehr auf -- er schaut
    # nur noch zu. Wer den Tab zumacht, bekommt trotzdem einen fertigen
    # Server statt eines halben.
    run_id = str(body.get("run_id") or "")

    # Mitzaehlen, dass hier gebaut wird. Erst jetzt, nachdem der
    # Template-Bot zugesagt hat -- ein abgelehnter Start ist kein Lauf.
    try:
        access.note_run(guild_id, user_id)
    except Exception:  # pragma: no cover - Buchhaltung darf nie den Bau kippen
        pass

    _cancel_tasks(guild_id)
    job = {
        "state": "waiting",
        "lines": [],
        "report": None,
        "started": time.time(),
        "finished": 0.0,
        "error": "",
        "run_id": run_id,
        "cancelled": False,
        "step": 0,
        "total": 0,
        "options": handover.normalise_options(data.get("steps")),
    }
    _MAIN_JOBS[guild_id] = job

    _spawn(
        bot,
        _watch_build(bot, guild, job, job["options"], run_id),
        guild_id,
    )

    return body


# --------------------------------------------------------------------- #
# 4. Die zweite Haelfte: was der University Bot danach einrichtet
# --------------------------------------------------------------------- #
#
# Der Zustand liegt im Arbeitsspeicher, aus demselben Grund wie beim
# Template-Bot: laeuft der Bot neu an, ist die Uebergabe ohnehin
# abgebrochen, und ein auf Platte gespeicherter Job stuende dann fuer
# immer auf "laeuft".

# guild_id -> {"state", "lines", "report", "started", "finished"}
#
# Zustaende:
#   waiting  Der Template-Bot baut noch; dieser Bot wartet darauf.
#   running  Die Einrichtung laeuft.
#   done     Alle gewaehlten Schritte sind durch.
#   partial  Gelaufen, aber einzelne Schritte haben nicht geklappt.
#   failed   Abgebrochen oder gescheitert.
_MAIN_JOBS: dict[int, dict] = {}

# Laufende Hintergrund-Tasks (Waechter und Einrichtung), damit ein
# Abbruch sie wirklich erreicht. asyncio haelt auf Tasks nur eine
# schwache Referenz -- ohne dieses Dict kann ein Lauf mitten drin
# eingesammelt werden.
_MAIN_TASKS: dict[int, set] = {}

# Wie lange der Waechter auf das Ende des Baus wartet, bevor er
# aufgibt. Der laengste Bau (rp, 101 Kanaele) braucht mit Discords
# Rate-Limits gut zehn Minuten; dreissig lassen Luft, ohne dass ein
# haengender Job ewig als "laeuft" dasteht.
WATCH_TIMEOUT = 30 * 60

# Abstand zwischen zwei Nachfragen des Waechters beim Template-Bot.
WATCH_INTERVAL = 3.0


def _remember_task(guild_id: int, task) -> None:
    tasks = _MAIN_TASKS.setdefault(guild_id, set())
    tasks.add(task)
    task.add_done_callback(lambda finished: tasks.discard(finished))


def _spawn(bot, coro, guild_id: int):
    """Eine Coroutine auf der Bot-Schleife starten und festhalten.

    Alles, was discord.py anfasst, gehoert auf die Schleife des Bots --
    die API laeuft in einem eigenen Thread. ``run_coroutine_threadsafe``
    liefert ein concurrent.futures.Future, kein Task; abbrechen laesst
    sich beides ueber ``.cancel()``.
    """

    loop = getattr(bot, "loop", None)
    if loop is not None and not loop.is_closed():
        handle = asyncio.run_coroutine_threadsafe(coro, loop)
    else:  # Tests und lokaler Betrieb ohne laufenden Bot
        handle = asyncio.ensure_future(coro)
    _remember_task(guild_id, handle)
    return handle


def _cancel_tasks(guild_id: int) -> None:
    for task in list(_MAIN_TASKS.get(guild_id, ())):
        try:
            task.cancel()
        except Exception:  # pragma: no cover - ein toter Task ist egal
            pass
    _MAIN_TASKS.pop(guild_id, None)

# Wie lange eine fertige Uebergabe abrufbar bleibt. Gleicher Wert wie
# beim Template-Bot, damit beide Haelften zusammen ablaufen.
KEEP_FINISHED = 15 * 60
MAX_LINES = 500


def _prune_main_jobs() -> None:
    now = time.time()
    for guild_id, job in list(_MAIN_JOBS.items()):
        if job["state"] == "running":
            continue
        if job.get("finished") and now - job["finished"] > KEEP_FINISHED:
            del _MAIN_JOBS[guild_id]


def _main_job(guild_id: int) -> dict | None:
    _prune_main_jobs()
    return _MAIN_JOBS.get(guild_id)


async def _run_main_phase(bot, guild, job: dict, options: dict, payload: dict) -> None:
    """Die Schritte des University Bots, im Hintergrund.

    Laeuft als Task, damit die HTTP-Antwort sofort raus kann -- Verify
    postet ein Panel, Tickets legen Tabellen an, das dauert.
    """

    async def log(text: str, level: str = "info") -> None:
        if len(job["lines"]) >= MAX_LINES:
            return
        job["lines"].append(
            {"text": text, "source": "main", "level": level, "at": time.time()}
        )

    # Der Fortschritt der zweiten Haelfte. Ohne ihn stand der Balken
    # waehrend der gesamten Einrichtung still: er kam nur vom
    # Template-Bot, und der ist zu diesem Zeitpunkt schon fertig.
    chosen = handover.normalise_options(options)
    planned = [key for key in handover.ORDER if chosen.get(key)]
    job["total"] = len(planned)
    job["step"] = 0

    async def step_done(_key: str) -> None:
        job["step"] = min(job.get("step", 0) + 1, job["total"])

    try:
        await log("University Bot übernimmt")
        report = await handover.run_handover(
            bot, guild, payload, options=options, log=log, on_step=step_done
        )
        job["report"] = report.as_dict()
        job["state"] = "done" if not report.failed else "partial"
        job["step"] = job["total"]

        done = sum(1 for step in report.steps if step.ok)
        if report.failed:
            await log(
                f"Fertig mit Lücken — {done} von {len(report.steps)} Schritten",
                "warn",
            )
        else:
            await log(f"Fertig — {done} Schritte eingerichtet", "success")
    except asyncio.CancelledError:
        # Abgebrochen. Der Zustand steht schon auf "failed" -- ihn hier
        # zu ueberschreiben wuerde den Abbruch verschlucken.
        await log("Einrichtung abgebrochen.", "warn")
        job["finished"] = time.time()
        raise
    except Exception as exc:
        job["state"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        await log(f"Abbruch: {type(exc).__name__}: {exc}", "error")
    finally:
        # Ein abgebrochener Lauf bleibt abgebrochen.
        #
        # Vorher stand hier nur ``job["finished"] = ...``, und der
        # Zustand wurde oben bedingungslos auf "done" gesetzt. Wer
        # waehrend der Einrichtung auf Abbrechen klickte, sah den Reiter
        # kurz auf "Abgebrochen" springen und zwei Sekunden spaeter auf
        # "Fertig" -- obwohl die Haelfte fehlte. Nachgestellt in
        # repro/bug_cancel.py.
        if job.get("cancelled"):
            job["state"] = "failed"
        job["finished"] = time.time()


async def _fetch_build(guild_id: int) -> dict:
    """Den Stand des Baus beim Template-Bot holen."""

    status_code, body = await _call_template(
        "GET", f"/internal/speedrun/{guild_id}?since=0", timeout=10
    )
    if status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )
    return body


def _begin_handover(bot, guild, job: dict, options: dict, result: dict) -> None:
    """Die Einrichtung starten und den Task festhalten."""

    job["state"] = "running"
    job["started_main"] = time.time()

    async def runner():
        await _run_main_phase(bot, guild, job, options, result)

    _spawn(bot, runner(), guild.id)


async def _watch_build(bot, guild, job: dict, options: dict, run_id: str) -> None:
    """Auf das Ende des Baus warten und dann selbst uebernehmen.

    Der Grund, warum es diesen Waechter gibt:

    Vorher stiess ausschliesslich der Browser die zweite Haelfte an --
    das Panel fragte den Fortschritt ab, sah "fertig" und rief /finish.
    Wer den Tab zumachte, das Handy sperrte oder unterwegs das Netz
    verlor, bekam einen halb eingerichteten Server: Rollen und Kanaele
    standen, aber Verify, Tickets, Logs, Anti-Nuke und die Begruessung
    fehlten -- ohne jede Meldung, und ein zweiter Versuch haette alles
    doppelt angelegt. Ein Bau dauert ueber eine Minute; einen Tab so
    lange offen zu halten ist keine Bedingung, die man Leuten stellen
    kann. Nachgestellt in repro/bug_tab_closed.py.

    Der Waechter laeuft im Bot. Er ueberlebt jeden geschlossenen Tab und
    braucht den Browser nur noch zum Zuschauen.
    """

    deadline = time.time() + WATCH_TIMEOUT

    async def log(text: str, level: str = "info") -> None:
        if len(job["lines"]) < MAX_LINES:
            job["lines"].append(
                {"text": text, "source": "main", "level": level, "at": time.time()}
            )

    try:
        while True:
            if job.get("cancelled"):
                return

            if time.time() > deadline:
                job["state"] = "failed"
                job["error"] = "Der Bau hat zu lange gebraucht."
                job["finished"] = time.time()
                await log(
                    "Der Template-Bot ist seit 30 Minuten nicht fertig geworden — "
                    "aufgegeben. Was gebaut wurde, bleibt stehen.",
                    "error",
                )
                return

            try:
                body = await _fetch_build(guild.id)
            except HTTPException:
                # Ein Aussetzer ist kein Grund aufzugeben: der
                # Template-Bot startet nach einem Deploy neu, und der Bau
                # laeuft dort weiter. Erst die Frist beendet das Warten.
                await asyncio.sleep(WATCH_INTERVAL)
                continue

            state = body.get("state")
            actual_run = str(body.get("run_id") or "")

            # Gehoert der Bau, den wir sehen, noch zu unserem Lauf? Nach
            # einem Neustart des Template-Bots kann dort ein voellig
            # anderer Job liegen.
            if run_id and actual_run and actual_run != run_id:
                job["state"] = "failed"
                job["error"] = "Der Bau gehört zu einem anderen Durchlauf."
                job["finished"] = time.time()
                await log(
                    "Beim Template-Bot läuft inzwischen ein anderer Durchlauf — "
                    "diese Einrichtung wurde abgebrochen.",
                    "error",
                )
                return

            if state == "running":
                await asyncio.sleep(WATCH_INTERVAL)
                continue

            if state == "failed":
                job["state"] = "failed"
                job["error"] = str(body.get("error") or "Der Bau ist gescheitert.")
                job["finished"] = time.time()
                await log(
                    "Der Bau ist gescheitert — es wird nichts eingerichtet.", "error"
                )
                return

            if state != "done":
                # "none" heisst: der Job ist beim Template-Bot abgelaufen
                # oder wurde vergessen. Ohne die Landkarte laesst sich
                # nichts einrichten.
                job["state"] = "failed"
                job["error"] = f"Unerwarteter Zustand beim Template-Bot: {state}."
                job["finished"] = time.time()
                await log(
                    "Der Template-Bot kennt diesen Bau nicht mehr — "
                    "die Einrichtung lässt sich nicht nachholen.",
                    "error",
                )
                return

            result = body.get("result") or {}
            if not result.get("roles") and not result.get("channels"):
                job["state"] = "failed"
                job["error"] = "Der Bau hat keine Rollen und Kanäle gemeldet."
                job["finished"] = time.time()
                await log(
                    "Der Template-Bot hat keine Rollen und Kanäle gemeldet.", "error"
                )
                return

            if job.get("cancelled"):
                return

            _begin_handover(bot, guild, job, options, result)
            return
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # pragma: no cover - der Waechter darf nie platzen
        job["state"] = "failed"
        job["error"] = f"{type(exc).__name__}: {exc}"
        job["finished"] = time.time()
        await log(f"Warten auf den Bau fehlgeschlagen: {exc}", "error")


@router.post("/{guild_id}/finish", summary="Hauptbot-Einrichtung starten")
async def finish(
    guild_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """
    Nimmt die Landkarte des Template-Bots und richtet damit ein.

    Im Normalfall wird dieser Endpunkt nicht mehr gebraucht: seit dem
    Waechter (``_watch_build``) uebernimmt der Bot von selbst, sobald
    der Bau fertig ist. Er bleibt als Nachhol-Weg fuer den Fall, dass
    der Waechter den Bau verpasst hat -- etwa weil der Bot mitten im Bau
    neu gestartet ist. Dann steht der Server gebaut, aber nicht
    eingerichtet da, und dieser Aufruf holt es nach.
    """

    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404,
            detail="Der University Bot ist nicht auf diesem Server.",
        )

    existing = _main_job(guild_id)
    if existing and existing["state"] in ("running", "waiting"):
        # "waiting" heisst: der Waechter sitzt schon dran. Ein zweiter
        # Anlauf wuerde alles doppelt anlegen.
        raise HTTPException(
            status_code=409,
            detail=(
                "Die Einrichtung läuft für diesen Server schon."
                if existing["state"] == "running"
                else "Der Bot wartet bereits auf das Ende des Baus."
            ),
        )

    # Die Landkarte kommt vom Template-Bot, nicht aus dem Browser. Sonst
    # koennte jeder mit curl beliebige Kanal-IDs schicken und den Bot
    # dazu bringen, das Verify-Panel in einen fremden Kanal zu posten.
    status_code, body = await _call_template(
        "GET", f"/internal/speedrun/{guild_id}?since=0", timeout=10
    )
    if status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )

    if body.get("state") == "running":
        raise HTTPException(
            status_code=409,
            detail="Der Template-Bot baut noch. Warte, bis er fertig ist.",
        )
    if body.get("state") != "done":
        raise HTTPException(
            status_code=400,
            detail=(
                "Es liegt kein fertiger Bau vor. "
                f"Zustand beim Template-Bot: {body.get('state') or 'unbekannt'}."
            ),
        )

    # Die Übergabe muss zu dem Bau gehören, den der Aufrufer gestartet
    # hat.
    #
    # Ein fertiger Job bleibt beim Template-Bot 15 Minuten abrufbar.
    # Ohne diese Prüfung erfüllt auch ein alter Bau die Bedingung
    # "fertig", und das Dashboard würde die Einrichtung ein zweites Mal
    # anstoßen -- Panels doppelt, Rollen neu vergeben, ohne dass jemand
    # etwas gestartet hat.
    wanted_run = str(data.get("run_id") or "").strip()
    actual_run = str(body.get("run_id") or "")
    if wanted_run and actual_run and wanted_run != actual_run:
        raise HTTPException(
            status_code=409,
            detail=(
                "Der fertige Bau beim Template-Bot gehört zu einem anderen "
                "Durchlauf. Starte den Speedrun neu."
            ),
        )

    result = body.get("result") or {}
    if not result.get("roles") and not result.get("channels"):
        raise HTTPException(
            status_code=400,
            detail="Der Template-Bot hat keine Rollen und Kanäle gemeldet.",
        )

    options = handover.normalise_options(data.get("options"))

    _cancel_tasks(guild_id)
    job = {
        "state": "running",
        "lines": [],
        "report": None,
        "started": time.time(),
        "finished": 0.0,
        "error": "",
        # Zu welchem Bau diese Einrichtung gehört. Das Dashboard
        # vergleicht damit, ob der Zustand, den es sieht, seiner ist.
        "run_id": actual_run or wanted_run,
        "cancelled": False,
        "step": 0,
        "total": 0,
        "options": options,
    }
    _MAIN_JOBS[guild_id] = job

    # Auf der Schleife des Bots, nicht auf der des API-Threads: alles,
    # was discord.py anfasst (Panel posten, Rollen lesen), ist an die
    # Bot-Schleife gebunden.
    _begin_handover(bot, guild, job, options, result)

    return {"status": "started", "guild_id": str(guild_id), "options": options}


@router.get("/steps", summary="Welche Schritte der Hauptbot anbietet")
async def steps(template: str = ""):
    """Der Baukasten fürs Dashboard: Name, Erklärung, Standardzustand.

    Mit ``?template=`` kommt dazu, ob der Schritt bei *dieser* Vorlage
    überhaupt möglich ist.

    Ohne diese Angabe bot der Reiter alle dreizehn Schritte an, egal
    was die Vorlage baut. Bei neun von zehn standen dadurch Schalter
    auf »an« für Sachen, die nie entstehen: ``rp`` hat keinen
    Rollen-Kanal, ``business`` kein Ticket-Panel, einen Zähl-Kanal hat
    nur ``community``. Wer sie anließ, las hinterher im Bericht
    »Übersprungen« -- und hatte etwas eingeschaltet, das gar nicht
    gehen konnte.

    Der Parameter ist absichtlich freiwillig: ohne ihn verhält sich die
    Route wie vorher, damit ein alter Browser-Stand nicht auf einmal
    leere Listen bekommt.
    """

    supported: dict[str, bool] = {}
    template_key = str(template or "").strip()
    template_error = ""

    if template_key:
        try:
            status_code, body = await _call_template(
                "GET", "/internal/speedrun/templates", timeout=10
            )
            if status_code == 200:
                for entry in body.get("templates", []):
                    if str(entry.get("key") or "") == template_key:
                        supported = dict(entry.get("capabilities") or {})
                        break
        except HTTPException as exc:
            # Der Template-Bot ist weg. Dann lieber alle Schritte
            # anbieten als keinen: eine unvollständige Liste wäre
            # schlimmer als eine, die einen Schritt zu viel zeigt.
            template_error = str(exc.detail)

    entries = []
    for key, spec in handover.STEPS.items():
        # Nicht in der Auskunft = kein Kanalbedarf = geht immer.
        possible = supported.get(key, True)
        entries.append(
            {
                "key": key,
                "label": spec["label"],
                "description": spec["description"],
                # Was die Vorlage nicht hergibt, steht auch nicht auf
                # "an" -- sonst schickt das Dashboard einen Schritt
                # los, der nur übersprungen werden kann.
                "default": bool(spec["default"]) and possible,
                "supported": possible,
            }
        )

    return {
        "steps": entries,
        "order": list(handover.ORDER),
        "template": template_key,
        "template_error": template_error,
    }


# --------------------------------------------------------------------- #
# 5. Fortschritt -- beide Haelften in einer Antwort
# --------------------------------------------------------------------- #


@router.post("/{guild_id}/cancel", summary="Laufenden Speedrun abbrechen")
async def cancel(guild_id: int):
    """
    Bricht den Bau beim Template-Bot ab und vergisst die Einrichtung.

    Der Server bleibt halb gebaut stehen -- Discord kennt kein Zurück.
    Trotzdem nötig: hängt der Bau an einem Rate-Limit oder einem
    Netzproblem, steht der Reiter sonst für immer auf "läuft" und ein
    zweiter Versuch ist gesperrt.
    """

    # Die zweite Hälfte zuerst stoppen, dann den Bau.
    #
    # Die Marke muss *vor* dem Abbruch der Tasks stehen: `_run_main_phase`
    # liest sie in seinem finally-Zweig, und nur so bleibt "failed" auch
    # stehen. Vorher wurde hier bloß der Zustand gesetzt -- die
    # Einrichtung lief seelenruhig weiter und schrieb am Ende "done"
    # darüber. Auf dem Bildschirm sprang der Reiter von "Abgebrochen"
    # zurück auf "Fertig", während der halbe Server fehlte.
    # Nachgestellt in repro/bug_cancel.py.
    job = _MAIN_JOBS.get(guild_id)
    if job is not None and job["state"] in ("running", "waiting"):
        job["cancelled"] = True
        job["state"] = "failed"
        job["error"] = "Abgebrochen."
        job["finished"] = time.time()
        job["lines"].append(
            {
                "text": "Abgebrochen.",
                "source": "main",
                "level": "warn",
                "at": time.time(),
            }
        )

    # Den Wächter und eine laufende Einrichtung wirklich beenden.
    _cancel_tasks(guild_id)

    status_code, body = await _call_template(
        "POST", f"/internal/speedrun/{guild_id}/cancel", payload={}, timeout=10
    )

    if status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
        )
    return {"cancelled": bool(body.get("cancelled")), "guild_id": str(guild_id)}


@router.get("/{guild_id}/status", summary="Fortschritt abholen")
async def status_route(guild_id: int, since: int = 0, since_main: int = 0):
    """
    Der Stand beider Bots, in einer Antwort.

    ``since`` zaehlt die Zeilen des Template-Bots, ``since_main`` die des
    University Bots. Zwei Zaehler, weil beide unabhaengig voneinander
    wachsen -- ein gemeinsamer wuerde Zeilen verschlucken, sobald beide
    gleichzeitig schreiben.
    """

    job = _main_job(guild_id)

    # Den Template-Bot fragen -- aber sein Ausfall darf nicht die ganze
    # Antwort kosten.
    #
    # Vorher warf diese Route 502, sobald der Template-Bot nicht
    # antwortete. Genau in der Einrichtungsphase ist das falsch: da
    # arbeitet nur noch dieser Bot, sein Stand liegt hier im
    # Arbeitsspeicher, und der Template-Bot wird nicht mehr gebraucht.
    # Ein Neustart drüben ließ den Reiter trotzdem ins Leere laufen und
    # der Nutzer sah die Einrichtung nicht mehr.
    # Nachgestellt in repro/bug_status_502.py.
    template_error = ""
    try:
        status_code, body = await _call_template(
            "GET",
            f"/internal/speedrun/{guild_id}?since={max(since, 0)}",
            timeout=10,
        )
        if status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=str(body.get("error") or f"Template-Bot: HTTP {status_code}"),
            )
    except HTTPException as exc:
        # Ohne eigenen Job gibt es nichts zu retten: dann ist der
        # Ausfall die ganze Nachricht.
        if job is None:
            raise
        template_error = str(exc.detail)
        body = {
            "state": "unreachable",
            "lines": [],
            "line_count": max(since, 0),
            "error": template_error,
        }

    body["template_error"] = template_error

    if job is None:
        body["main"] = {"state": "none", "lines": [], "line_count": 0, "report": None}
    else:
        start = max(since_main, 0)
        body["main"] = {
            "state": job["state"],
            "lines": job["lines"][start:],
            "line_count": len(job["lines"]),
            "report": job["report"],
            "error": job.get("error", ""),
            "run_id": job.get("run_id", ""),
            # Fortschritt der zweiten Hälfte. Ohne ihn stand der Balken
            # während der gesamten Einrichtung still.
            "step": job.get("step", 0),
            "total": job.get("total", 0),
        }

    return body


# --------------------------------------------------------------------- #
# 6. Verwaltung -- wer darf, wer nicht
# --------------------------------------------------------------------- #
#
# Diese Routen liegen hinter /speedrun/admin/*. Der Proxy im Dashboard
# laesst dorthin nur globale Admins durch; hier steht keine zweite
# Rechtepruefung, weil der Bot die Discord-Rollen des Aufrufers gar
# nicht kennt -- die Sitzung lebt im Dashboard.


@router.get("/admin/guilds", summary="Alle Server mit ihrem Zugang")
async def admin_guilds(
    limit: int = 200,
    bot: "universitybot" = Depends(get_bot),
):
    """Die Liste fuers Admin-Panel, angereichert um Namen und Groesse.

    Die Zugangstabelle kennt nur IDs. Eine Liste aus achtzehnstelligen
    Zahlen ist zum Verwalten unbrauchbar -- welcher davon war noch
    gleich der Server, der Aerger gemacht hat? Der Name kommt deshalb
    aus dem Bot-Cache dazu, soweit er dort steht.
    """

    entries = access.list_guilds(limit)

    for entry in entries:
        guild = None
        try:
            guild = bot.get_guild(int(entry["guild_id"]))
        except (TypeError, ValueError):
            pass

        entry["name"] = getattr(guild, "name", "")
        entry["members"] = getattr(guild, "member_count", None)
        # Ob der Bot ueberhaupt noch drauf ist. Ein Server, den er
        # verlassen hat, braucht keinen Bann mehr.
        entry["bot_present"] = guild is not None

    return {"guilds": entries, "stats": access.stats()}


@router.get("/admin/history", summary="Verlauf: wer wann was")
async def admin_history(guild_id: str = "", limit: int = 100):
    """Jede Freischaltung, jeder Fehlversuch, jeder Entzug, jeder Bann."""

    return {"events": access.history(guild_id, limit)}


@router.post("/admin/{guild_id}/revoke", summary="Freischaltung entziehen")
async def admin_revoke(
    guild_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """Den Code entziehen: der Server muss ihn neu eingeben.

    Ein laufender Bau wird dabei abgebrochen. Wer jemandem den Zugang
    nimmt, will nicht, dass der angefangene Umbau trotzdem zu Ende
    laeuft -- und der Bot arbeitet nach dem Entzug sonst noch Minuten
    weiter am Server.
    """

    actor = str(data.get("actor_id") or "")
    existed = access.revoke(guild_id, actor)
    stopped = await _stop_everything(guild_id)

    return {"revoked": existed, "run_cancelled": stopped}


@router.post("/admin/{guild_id}/ban", summary="Server dauerhaft sperren")
async def admin_ban(
    guild_id: int,
    data: dict,
    bot: "universitybot" = Depends(get_bot),
):
    """Sperren. Danach hilft kein Code mehr."""

    actor = str(data.get("actor_id") or "")
    reason = str(data.get("reason") or "").strip()

    access.ban(guild_id, actor, reason)
    stopped = await _stop_everything(guild_id)

    return {"banned": True, "run_cancelled": stopped}


@router.post("/admin/{guild_id}/unban", summary="Sperre aufheben")
async def admin_unban(guild_id: int, data: dict):
    """Den Bann loesen.

    Der Server ist danach **nicht** wieder frei -- der Code muss neu
    eingegeben werden. Alles andere waere ueberraschend: eine
    aufgehobene Sperre ist keine Freischaltung.
    """

    lifted = access.unban(guild_id, str(data.get("actor_id") or ""))
    return {"unbanned": lifted, "needs_code_again": True}


async def _stop_everything(guild_id: int) -> bool:
    """Einen laufenden Speedrun beenden, so weit es geht.

    Wird beim Entzug und beim Bann gerufen. Scheitert der Aufruf beim
    Template-Bot, ist das kein Grund, den Entzug zu verweigern -- der
    Zugang ist dann trotzdem weg, und das ist die Hauptsache.
    """

    job = _MAIN_JOBS.get(guild_id)
    running = job is not None and job["state"] in ("running", "waiting")

    if job is not None:
        job["cancelled"] = True
        if running:
            job["state"] = "failed"
            job["error"] = "Der Zugang wurde entzogen."
            job["finished"] = time.time()
            job["lines"].append(
                {
                    "text": "Abgebrochen — der Zugang für diesen Server wurde entzogen.",
                    "source": "main",
                    "level": "error",
                    "at": time.time(),
                }
            )

    _cancel_tasks(guild_id)

    try:
        await _call_template(
            "POST", f"/internal/speedrun/{guild_id}/cancel", payload={}, timeout=10
        )
    except HTTPException:
        # Der Template-Bot ist nicht erreichbar. Der Bau dort laeuft
        # dann weiter -- daran laesst sich von hier nichts aendern, und
        # der Entzug gilt trotzdem.
        pass

    return running
