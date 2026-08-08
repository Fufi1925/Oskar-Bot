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
        # Der Name muss beim Loeschen abgetippt werden -- damit niemand
        # aus Versehen den falschen Server ausraeumt.
        "guild_name": guild.name,
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

    # Beim Loeschen muss der Servername stimmen. Dieselbe Sicherung
    # wie beim Verlassen eines Servers: ein Fehlklick soll nicht
    # reichen.
    if options["wipe"]:
        typed = str((data or {}).get("confirm") or "").strip()
        if typed.lower() != guild.name.strip().lower():
            raise HTTPException(
                400,
                "Zum Löschen muss der Servername genau eingetippt werden.",
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
