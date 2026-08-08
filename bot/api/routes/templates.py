# ╔══════════════════════════════════════════════════════════════════╗
# ║   Community-Vorlagen                                             ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Server einscannen, als Vorlage teilen, auf andere Server holen.

Zwei Reiter im Dashboard:

  **Hochladen** -- den eigenen Server scannen, auswaehlen was mit
  soll, benennen, offen oder mit Zugangscode veroeffentlichen.

  **Community-Vorlagen** -- durchsuchen, ansehen, anwenden.

Warum das Anwenden zwei Aufrufe braucht
---------------------------------------
Erst `/preview`, dann `/apply`. Der erste sagt, was passieren wuerde
und was dem Bot fehlt; der zweite tut es. Ein einzelner Aufruf haette
bedeutet, dass ein Klick sofort Kanaele loescht -- ohne Chance, vorher
zu sehen, ob der Bot ueberhaupt die Rechte dafuer hat.

Warum die Vorschau bei Code-Vorlagen leer bleibt
------------------------------------------------
Ein Zugangscode, dessen Inhalt man auch ohne ihn sieht, ist keiner.
Die Liste zeigt Name, Beschreibung und Zahlen -- alles Weitere erst
nach Eingabe.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from api.db_manager import db_manager
from api.dependencies import get_bot
from utils import feature_audit
from utils import template_apply as applier
from utils import template_scan as scanner
from utils import template_store as store

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

# Wie lange der Loesch-Knopf gesperrt bleibt, in Sekunden.
#
# Die Zahl steht hier und nicht nur im Dashboard: die Oberflaeche
# holt sie sich ueber `preview` ab, damit beide Seiten dieselbe
# Wartezeit meinen. Zwei Konstanten waeren frueher oder spaeter
# verschieden.
WIPE_DELAY_SECONDS = 10

# Wie lange eine Pruefung gilt. Danach muss neu geprueft werden --
# eine Stunde alte Vorschau sagt nichts mehr darueber, was gerade auf
# dem Server steht.
WIPE_WINDOW_SECONDS = 900


async def _db():
    connection = await db_manager.get_connection(store.DB_PATH)
    await store.ensure_schema(connection)
    return connection


def _guild_or_404(bot, guild_id: int):
    guild = bot.get_guild(guild_id)
    if guild is None:
        raise HTTPException(
            status_code=404, detail="Der Bot ist nicht auf diesem Server."
        )
    return guild


# ── Verwaltung ───────────────────────────────────────────────────────
#
# Diese Routen liegen hinter /templates/admin/*. Der Proxy im
# Dashboard laesst dorthin nur globale Admins durch -- dieselbe Regel
# wie bei /speedrun/admin/*. Hier steht keine zweite Rechtepruefung,
# weil der Bot die Dashboard-Sitzung des Aufrufers gar nicht kennt.
#
# Warum sie GANZ OBEN stehen
# --------------------------
# FastAPI prueft die Routen in der Reihenfolge, in der sie angemeldet
# wurden. Weiter unten steht `/{guild_id}/list` mit `guild_id: int`.
# Stuenden die Admin-Routen dahinter, liefe `/admin/list` zuerst in
# diese Regel, wollte "admin" als Zahl lesen und antwortete mit 422 --
# der Reiter waere kaputt, ohne dass jemand sieht, warum.


@router.get("/admin/list", summary="Alle Vorlagen, mit Code")
async def admin_list(search: str = "", sort: str = "neu",
                     bot: "universitybot" = Depends(get_bot)):
    """Jede hochgeladene Vorlage -- auch die privaten und die mit Code.

    Der Zugangscode kommt im Klartext mit. Das ist der Sinn des
    Reiters: das Bot-Team soll pruefen koennen, was auf den eigenen
    Servern verteilt wird, ohne jeden Hochlader fragen zu muessen.
    """

    db = await _db()
    entries = await store.list_for_admin(db, search=search, sort=sort)

    # Servernamen dazu. Eine Liste aus achtzehnstelligen Zahlen ist
    # zum Verwalten unbrauchbar -- welcher davon war noch gleich der,
    # der Aerger gemacht hat?
    for entry in entries:
        guild = None
        try:
            guild = bot.get_guild(int(entry["source_guild_id"]))
        except (TypeError, ValueError):
            pass
        entry["source_guild_name"] = getattr(guild, "name", "")
        entry["bot_present"] = guild is not None

    return {
        "templates": entries,
        "stats": await store.admin_stats(db),
        "sorts": list(store.SORTS),
    }


@router.get("/admin/{template_id}/history", summary="Wer hat sie angewendet")
async def admin_history(template_id: int):
    db = await _db()
    return {"events": await store.history_for(db, template_id)}


@router.get("/admin/{template_id}/payload", summary="Der volle Inhalt")
async def admin_payload(template_id: int):
    """Was wirklich in der Vorlage steht -- ohne Zugangscode.

    Ein Admin muss hineinsehen koennen, bevor er ueber eine Meldung
    entscheidet. Der Code ist dafuer nicht noetig: die Route liest
    direkt aus der Datenbank.
    """

    db = await _db()
    found = await store.get_template(db, template_id, key=None, owner_guild_id=None)
    if found is None:
        raise HTTPException(404, "Diese Vorlage gibt es nicht.")

    payload = found.get("payload") or {}
    return {
        "categories": [c.get("name") for c in payload.get("categories") or []],
        "channels": [
            {"name": c.get("name"), "kind": c.get("kind"),
             "category": c.get("category")}
            for c in payload.get("channels") or []
        ],
        "roles": [
            {"name": r.get("name"), "colour": r.get("colour")}
            for r in payload.get("roles") or []
        ],
        "features": scanner.describe_features(payload.get("features") or {}),
    }


@router.post("/admin/{template_id}/block", summary="Sperren oder freigeben")
async def admin_block(template_id: int, data: dict):
    """Sperren statt loeschen, wo es geht.

    Eine gesperrte Vorlage bleibt sichtbar, laesst sich aber nicht
    mehr anwenden, und ihr Hochlader sieht den Grund. Ein Irrtum ist
    damit zuruecknehmbar -- geloescht ist geloescht.
    """

    db = await _db()
    blocked = bool((data or {}).get("blocked", True))
    reason = str((data or {}).get("reason") or "").strip()

    if blocked and not reason:
        raise HTTPException(
            400,
            "Bitte einen Grund angeben. Ohne ihn sieht der Hochlader nur, "
            "dass etwas nicht mehr geht, und meldet es als Fehler.",
        )

    if not await store.set_blocked(
        db,
        template_id,
        blocked=blocked,
        reason=reason,
        actor=str((data or {}).get("actor") or ""),
    ):
        raise HTTPException(404, "Diese Vorlage gibt es nicht.")

    await feature_audit.log_action(
        "template_block" if blocked else "template_unblock",
        actor=str((data or {}).get("actor") or ""),
        detail=f"{template_id}: {reason}" if reason else str(template_id),
    )
    return {"status": "success", "blocked": blocked}


@router.delete("/admin/{template_id}", summary="Endgueltig loeschen")
async def admin_delete(template_id: int, actor: str = ""):
    """Loeschen, egal wem sie gehoert.

    Getrennt von der normalen Loeschroute, damit der Besitzcheck dort
    nicht aus Versehen umgangen werden kann: ein Aufruf von
    `force_delete` ist im Quelltext sofort als Admin-Weg erkennbar.
    """

    db = await _db()
    if not await store.force_delete(db, template_id):
        raise HTTPException(404, "Diese Vorlage gibt es nicht.")

    await feature_audit.log_action(
        "template_admin_delete", actor=actor, detail=str(template_id)
    )
    return {"status": "success"}


# ── Scannen ──────────────────────────────────────────────────────────


@router.get("/{guild_id}/scan", summary="Diesen Server einlesen")
async def scan(guild_id: int, bot: "universitybot" = Depends(get_bot)):
    """Was auf diesem Server steht -- als Vorschau vor dem Hochladen.

    Es wird noch nichts gespeichert. Der Nutzer soll erst sehen, was
    mitginge, und dann entscheiden.
    """

    guild = _guild_or_404(bot, guild_id)

    payload = await scanner.build_payload(guild, include_features=True)
    labels = scanner.id_labels(guild)
    clean = store.sanitise(payload, labels)

    return {
        "preview": {
            "name": guild.name,
            "categories": [c["name"] for c in clean.get("categories") or []],
            "channels": [
                {"name": c["name"], "kind": c["kind"], "category": c.get("category")}
                for c in clean.get("channels") or []
            ],
            "roles": [
                {"name": r["name"], "colour": r.get("colour")}
                for r in clean.get("roles") or []
            ],
            "features": scanner.describe_features(clean.get("features") or {}),
        },
        "counts": {
            "categories": len(clean.get("categories") or []),
            "channels": len(clean.get("channels") or []),
            "roles": len(clean.get("roles") or []),
            "features": len(clean.get("features") or {}),
        },
        "limits": {
            "max_per_guild": store.MAX_TEMPLATES_PER_GUILD,
            "max_name": store.MAX_NAME,
            "max_description": store.MAX_DESCRIPTION,
        },
        "already": await store.count_for_guild(await _db(), guild_id),
    }


# ── Hochladen ────────────────────────────────────────────────────────


@router.post("/{guild_id}/upload", summary="Als Vorlage veroeffentlichen")
async def upload(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    name = str((data or {}).get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Die Vorlage braucht einen Namen.")

    if await store.count_for_guild(db, guild_id) >= store.MAX_TEMPLATES_PER_GUILD:
        raise HTTPException(
            400,
            f"Mehr als {store.MAX_TEMPLATES_PER_GUILD} Vorlagen pro Server sind "
            "nicht vorgesehen. Bitte zuerst eine löschen.",
        )

    include = (data or {}).get("include") or {}
    payload = await scanner.build_payload(
        guild, include_features=bool(include.get("features", True))
    )

    if not include.get("roles", True):
        payload["roles"] = []
    if not include.get("channels", True):
        payload["categories"] = []
        payload["channels"] = []
    if not include.get("permissions", True):
        payload["categories"] = [
            {**c, "overwrites": []} for c in payload.get("categories") or []
        ]
        payload["channels"] = [
            {**c, "overwrites": []} for c in payload.get("channels") or []
        ]

    # Einzelne Funktionen abwaehlbar.
    wanted = (data or {}).get("feature_keys")
    if isinstance(wanted, dict) and payload.get("features"):
        payload["features"] = {
            key: block
            for key, block in payload["features"].items()
            if wanted.get(key, True)
        }

    labels = scanner.id_labels(guild)
    clean = store.sanitise(payload, labels)

    # Gegenprobe. Findet sie noch etwas, wird abgelehnt statt
    # stillschweigend veroeffentlicht -- lieber eine Fehlermeldung als
    # ein Leck.
    if store.contains_secret(clean):
        raise HTTPException(
            400,
            "In den Einstellungen steckt noch ein Zugangsdatum (Webhook, Token "
            "oder Einladung). Aus Sicherheitsgründen wird nicht hochgeladen. "
            "Bitte die Dashboard-Einstellungen abwählen und erneut versuchen.",
        )

    if not (clean.get("channels") or clean.get("roles") or clean.get("features")):
        raise HTTPException(400, "Es wurde nichts ausgewählt.")

    visibility = str((data or {}).get("visibility") or "public")
    if visibility not in ("public", "key", "private"):
        visibility = "public"

    template_id, plain_key = await store.create_template(
        db,
        name=name,
        description=str((data or {}).get("description") or ""),
        author_id=(data or {}).get("author_id"),
        author_name=str((data or {}).get("author_name") or ""),
        source_guild_id=guild_id,
        payload=clean,
        visibility=visibility,
        key=(data or {}).get("key"),
    )

    await feature_audit.log_action(
        "template_upload", guild_id=guild_id, detail=f"{name} ({visibility})"
    )

    return {
        "status": "success",
        "id": template_id,
        # Genau einmal -- danach steht nur noch der Hash in der
        # Datenbank.
        "key": plain_key,
    }


# ── Stoebern ─────────────────────────────────────────────────────────


@router.get("/{guild_id}/list", summary="Community-Vorlagen")
async def list_all(
    guild_id: int,
    search: str = "",
    sort: str = "neu",
    bot: "universitybot" = Depends(get_bot),
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    return {
        "templates": await store.list_templates(db, search=search, sort=sort),
        "own": await store.list_own(db, guild_id),
        "sorts": list(store.SORTS),
        # Damit die eigene Liste weiss, ob sie den Knopf »Code
        # anzeigen« ueberhaupt einblenden darf.
        "limits": {
            "max_per_guild": store.MAX_TEMPLATES_PER_GUILD,
        },
    }


@router.get("/{guild_id}/template/{template_id}", summary="Eine Vorlage ansehen")
async def detail(
    guild_id: int,
    template_id: int,
    key: str = "",
    bot: "universitybot" = Depends(get_bot),
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    found = await store.get_template(
        db, template_id, key=key or None, owner_guild_id=guild_id
    )
    if found is None:
        raise HTTPException(404, "Diese Vorlage gibt es nicht.")

    if found["locked"]:
        # Bewusst 200 statt 403: die Vorlage existiert, sie ist nur
        # verschlossen. Ein Fehler waere hier die falsche Auskunft.
        return {"template": found, "features": []}

    payload = found.get("payload") or {}
    return {
        "template": found,
        "features": scanner.describe_features(payload.get("features") or {}),
    }


@router.delete("/{guild_id}/template/{template_id}", summary="Eigene Vorlage loeschen")
async def remove(
    guild_id: int, template_id: int, bot: "universitybot" = Depends(get_bot)
):
    _guild_or_404(bot, guild_id)
    db = await _db()

    if not await store.delete_template(db, template_id, guild_id):
        raise HTTPException(
            404, "Diese Vorlage gibt es nicht — oder sie gehört einem anderen Server."
        )

    await feature_audit.log_action(
        "template_delete", guild_id=guild_id, detail=str(template_id)
    )
    return {"status": "success"}


@router.get("/{guild_id}/template/{template_id}/key", summary="Eigenen Code anzeigen")
async def show_key(
    guild_id: int, template_id: int, bot: "universitybot" = Depends(get_bot)
):
    """Den Zugangscode der **eigenen** Vorlage noch einmal ansehen.

    Bisher gab es ihn genau einmal, direkt nach dem Hochladen. Wer das
    Fenster schloss, ohne ihn zu notieren, musste die Vorlage neu
    hochladen -- der Code lag nur als Hash in der Datenbank.

    Jetzt liegt er zusaetzlich verschluesselt daneben. Die Sperre ist
    `owner_guild_id`: nur der Server, der hochgeladen hat, bekommt
    ihn. Die IDs sind fortlaufend, ohne diese Bedingung reichte eine
    geratene Zahl, um jeden fremden Code zu lesen.
    """

    _guild_or_404(bot, guild_id)
    db = await _db()

    found, plain = await store.reveal_key(db, template_id, owner_guild_id=guild_id)
    if not found:
        raise HTTPException(
            404, "Diese Vorlage gibt es nicht — oder sie gehört einem anderen Server."
        )

    await feature_audit.log_action(
        "template_key_shown", guild_id=guild_id, detail=str(template_id)
    )

    return {
        "key": plain,
        # Ehrlich statt raetselhaft: ohne Grund sieht ein leeres Feld
        # nach einem Fehler aus.
        "reason": (
            ""
            if plain
            else "Der Code lässt sich nicht mehr anzeigen. Er stammt aus der "
            "Zeit vor dieser Funktion, oder der Schlüssel des Bots hat "
            "gewechselt. Die Vorlage funktioniert weiter — nur nachschlagen "
            "geht nicht mehr."
        ),
    }


# ── Anwenden ─────────────────────────────────────────────────────────


@router.post("/{guild_id}/preview", summary="Was wuerde passieren?")
async def preview(
    guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)
):
    """Der Blick vor dem Sprung.

    Sagt, was angelegt wuerde, was geloescht wuerde -- und was dem Bot
    fehlt. Ohne diesen Schritt waere ein Klick sofort endgueltig.
    """

    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    try:
        template_id = int((data or {}).get("template_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "»template_id« muss eine Zahl sein.")

    found = await store.get_template(
        db, template_id, key=(data or {}).get("key"), owner_guild_id=guild_id
    )
    if found is None:
        raise HTTPException(404, "Diese Vorlage gibt es nicht.")
    if found["locked"]:
        raise HTTPException(403, "Diese Vorlage braucht einen Zugangscode.")

    payload = found.get("payload") or {}
    wipe = bool((data or {}).get("wipe"))

    problems = await applier.precheck(guild, payload, wipe=wipe)

    would_delete = []
    if wipe:
        protected = applier._protected_channels(guild)
        would_delete = [
            f"Kanal {c.name}"
            for c in getattr(guild, "channels", [])
            if int(c.id) not in protected
        ] + [
            f"Rolle {r.name}"
            for r in getattr(guild, "roles", [])
            if not getattr(r, "is_default", lambda: False)()
            and not getattr(r, "managed", False)
        ]

    return {
        "problems": problems,
        "will_create": {
            "categories": [c["name"] for c in payload.get("categories") or []],
            "channels": [c["name"] for c in payload.get("channels") or []],
            "roles": [r["name"] for r in payload.get("roles") or []],
        },
        "will_delete": would_delete,
        "features": scanner.describe_features(payload.get("features") or {}),
        "guild_name": guild.name,
        # Ab hier laeuft die Wartezeit. Der Wert geht beim Anwenden
        # zurueck an den Server, der nachrechnet -- so kann ein
        # direkter Aufruf der Route die Sperre nicht ueberspringen.
        "armed_at": time.time(),
        "wipe_delay": WIPE_DELAY_SECONDS,
        "wipe_window": WIPE_WINDOW_SECONDS,
        "blocked": bool(found.get("blocked")),
        "blocked_reason": found.get("blocked_reason") or "",
    }


@router.post("/{guild_id}/apply", summary="Vorlage anwenden")
async def apply(guild_id: int, data: dict, bot: "universitybot" = Depends(get_bot)):
    guild = _guild_or_404(bot, guild_id)
    db = await _db()

    try:
        template_id = int((data or {}).get("template_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "»template_id« muss eine Zahl sein.")

    found = await store.get_template(
        db, template_id, key=(data or {}).get("key"), owner_guild_id=guild_id
    )
    if found is None:
        raise HTTPException(404, "Diese Vorlage gibt es nicht.")
    if found["locked"]:
        raise HTTPException(403, "Diese Vorlage braucht einen Zugangscode.")

    options = {
        "roles": bool((data or {}).get("roles", True)),
        "channels": bool((data or {}).get("channels", True)),
        "permissions": bool((data or {}).get("permissions", True)),
        "features": bool((data or {}).get("features", False)),
        "wipe": bool((data or {}).get("wipe")),
        "feature_keys": (data or {}).get("feature_keys") or {},
    }

    # Eine gesperrte Vorlage laesst sich nicht mehr anwenden.
    #
    # Die Pruefung steht hier und nicht nur in der Oberflaeche: der
    # Knopf im Dashboard ist ausgegraut, aber ein direkter Aufruf der
    # Route umginge das mit einer Zeile.
    if found.get("blocked"):
        raise HTTPException(
            403,
            "Diese Vorlage wurde vom Bot-Team gesperrt"
            + (f": {found.get('blocked_reason')}" if found.get("blocked_reason") else "")
            + ".",
        )

    # Beim Loeschen entscheidet die Wartezeit, nicht das Abtippen.
    #
    # Der Servername war eine Huerde, die niemanden aufgehalten hat:
    # er stand als Platzhalter direkt im Feld darueber, abtippen
    # dauert drei Sekunden und man liest dabei nichts. Auf Wunsch
    # ersetzt durch zehn Sekunden Wartezeit -- die vergehen, ob man
    # will oder nicht, und in ihnen liest man tatsaechlich, was da
    # steht.
    #
    # Der Zeitstempel kommt aus der `preview`. Die Oberflaeche sperrt
    # den Knopf ohnehin; diese Pruefung ist die zweite Instanz, damit
    # ein direkter Aufruf der Route nicht sofort loeschen kann.
    if options["wipe"]:
        try:
            started = float((data or {}).get("armed_at") or 0)
        except (TypeError, ValueError):
            started = 0.0

        waited = time.time() - started
        if started <= 0:
            raise HTTPException(
                400,
                "Zum Löschen muss vorher geprüft werden — der Ablauf startet "
                "mit »Prüfen«.",
            )
        if waited < WIPE_DELAY_SECONDS:
            raise HTTPException(
                400,
                f"Bitte noch {WIPE_DELAY_SECONDS - int(waited)} Sekunden warten. "
                "Die Wartezeit ist Absicht: gelöschte Kanäle sind samt Verlauf "
                "endgültig weg.",
            )
        # Eine Vorschau von vorgestern ist keine Vorschau. In der Zeit
        # kann sich auf dem Server alles geaendert haben.
        if waited > WIPE_WINDOW_SECONDS:
            raise HTTPException(
                400,
                "Die Prüfung ist zu alt. Bitte noch einmal »Prüfen« drücken — "
                "auf dem Server kann sich inzwischen etwas geändert haben.",
            )

    report = await applier.apply_template(guild, found.get("payload") or {}, options)

    await store.bump_uses(db, template_id)
    await store.log_apply(
        db,
        template_id=template_id,
        guild_id=guild_id,
        actor_id=(data or {}).get("actor_id"),
        options=options,
        wiped=options["wipe"],
    )
    await feature_audit.log_action(
        "template_apply",
        guild_id=guild_id,
        detail=f"{found['name']}{' (geleert)' if options['wipe'] else ''}",
    )

    return {"status": "success", "report": report}
