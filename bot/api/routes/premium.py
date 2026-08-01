# ╔══════════════════════════════════════════════════════════════════╗
# ║   Premium licence keys API                                       ║
# ╚══════════════════════════════════════════════════════════════════╝

"""
Licence keys for the template bot's premium features.

Three audiences, three levels of access:

  * the dashboard, for a user redeeming their own key
  * the admin panel, for listing and revoking
  * the template bot itself, asking whether a user has premium

That last one is the only endpoint reachable by a different program, so
it authenticates separately with a shared secret and is read-only. It
cannot mint, redeem or revoke anything.
"""

from __future__ import annotations

import hmac
import os
from typing import TYPE_CHECKING, Optional

import aiohttp
import discord
from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import get_bot
from discord.ui import Separator, TextDisplay
from utils.cv2 import build_container
from utils.emoji import NEXT_ALT1 as NEXT, PREMIUM, STAR, UPTIME, ZBOT, ZSAFE, ZWARNING
from utils.links import dashboard_url
from utils import bot_settings
from utils import feature_audit
from utils import premium_store as store

# The support server, same default as the compose route.
HOME_GUILD_ID = int(os.getenv("HOME_GUILD_ID") or 1530378233579704370)

if TYPE_CHECKING:
    from core.universitybot import universitybot

router = APIRouter()

PARTNER_TOKEN_ENV = "PREMIUM_PARTNER_TOKEN"


def _require_partner_token(token: Optional[str]) -> None:
    """
    Authenticate the template bot.

    compare_digest, not ==: string comparison returns early on the first
    wrong byte, which leaks the prefix over enough attempts.
    """
    expected = os.getenv(PARTNER_TOKEN_ENV, "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail=f"{PARTNER_TOKEN_ENV} ist nicht gesetzt — die Abfrage "
                   "ist deaktiviert, bis ein Token konfiguriert wurde.",
        )
    if not token or not hmac.compare_digest(token.strip(), expected):
        raise HTTPException(status_code=401, detail="Ungültiges Partner-Token.")


# ══════════════════════════════════════════════════════════════════════
#  For the template bot
# ══════════════════════════════════════════════════════════════════════


@router.get("/check/{user_id}", summary="Does this user have premium?")
async def check_premium(
    user_id: int,
    product: str = "template_bot",
    x_partner_token: Optional[str] = Header(default=None),
):
    """
    The question the template bot asks.

    Read-only and deliberately boring: a plain yes/no plus an expiry.
    """
    _require_partner_token(x_partner_token)
    return store.status(user_id, product=product)


# ══════════════════════════════════════════════════════════════════════
#  For the dashboard
# ══════════════════════════════════════════════════════════════════════


@router.get("/me/{user_id}", summary="Own premium status")
async def my_premium(user_id: int):
    """What the Premium tab shows the signed-in user."""
    client_id = os.getenv("PARTNER_BOT_CLIENT_ID", "").strip()

    # No guild_id and no preselection: premium follows the account, so
    # the buyer picks whichever server they want the bot on. The link is
    # offered whether or not the bot is already somewhere — that is how
    # you add it to a second server.
    invite = ""
    if client_id.isdigit():
        invite = (
            "https://discord.com/oauth2/authorize"
            f"?client_id={client_id}&permissions=8"
            "&scope=bot%20applications.commands"
        )

    return {
        "template_bot": store.status(user_id, product="template_bot"),
        # The main bot has nothing to sell yet. Saying so here keeps the
        # dashboard from inventing an answer.
        "main_bot": {"premium": False, "coming_soon": True},
        "template_invite": invite,
    }


@router.post("/redeem", summary="Redeem a licence key")
async def redeem_key(data: dict):
    """
    Bind a key to the account that redeemed it.

    The user id comes from the dashboard's session, not from the form,
    so nobody can redeem onto someone else's account.
    """
    user_id = str(data.get("user_id") or "").strip()
    key = str(data.get("key") or "").strip()

    if not user_id.isdigit():
        raise HTTPException(status_code=400, detail="Keine gültige Benutzer-ID.")
    if not key:
        raise HTTPException(status_code=400, detail="Bitte einen Key eingeben.")

    result = store.redeem(key, user_id)

    if not result["ok"]:
        messages = {
            "invalid_format": "Der Key hat nicht die richtige Länge. "
                              "Er besteht aus 16 Zeichen.",
            "unknown": "Diesen Key gibt es nicht. Bitte die Eingabe prüfen.",
            "revoked": "Dieser Key wurde gesperrt.",
            "already_used": "Dieser Key gehört bereits einem anderen Konto.",
        }
        raise HTTPException(
            status_code=400,
            detail=messages.get(result["error"], "Der Key konnte nicht eingelöst werden."),
        )

    await feature_audit.log_action(
        "premium_redeemed", actor=user_id,
        detail=f"product={result['product']}",
    )

    return {
        "status": "success",
        "already": result["already"],
        "expires_at": result["expires_at"],
        "product": result["product"],
        "result": (
            "Dieser Key war bereits für dein Konto aktiv."
            if result["already"] else "Premium ist jetzt für dein Konto aktiv."
        ),
    }


# ══════════════════════════════════════════════════════════════════════
#  For the admin panel
# ══════════════════════════════════════════════════════════════════════


@router.get("/keys", summary="List issued keys")
async def list_keys(limit: int = 100, bot: "universitybot" = Depends(get_bot)):
    """
    Recent keys, with the names behind the ids.

    Only hashes are stored, so the list can never show a key itself. A
    key the buyer lost has to be revoked and replaced.
    """
    keys = store.list_keys(limit)

    # Ids alone are useless for support work. Resolve what the bot
    # already has cached; anything unknown simply stays an id.
    for row in keys:
        for field, out in (("redeemed_by", "redeemed_name"),
                           ("created_by", "created_name")):
            value = row.get(field)
            row[out] = ""
            if not value:
                continue
            try:
                user = bot.get_user(int(value))
            except (TypeError, ValueError):
                continue
            if user is not None:
                row[out] = user.display_name or user.name

    return {
        "keys": keys,
        "role": _role_state(bot),
        "stats": store.stats(),
        "pepper_set": bool(os.getenv(store.PEPPER_ENV, "").strip()),
        "partner_token_set": bool(os.getenv(PARTNER_TOKEN_ENV, "").strip()),
        # Without this a revoke only lands when the other side's cache
        # expires, so the dashboard says whether it is configured.
        "template_url_set": bool((os.getenv("TEMPLATE_BOT_URL") or "").strip()),
    }


def _role_state(bot) -> dict:
    """
    Whether the premium role can actually be handed out.

    Three things go wrong in practice and all three look identical from
    the dashboard — no role, no permission, or a role above the bot — so
    they are reported apart.
    """
    role_id = bot_settings.get("premium_role", "").strip()
    state: dict = {"configured": role_id.isdigit(), "id": role_id, "name": "",
                   "ok": False, "problem": ""}
    if not state["configured"]:
        state["problem"] = "Keine Premium-Rolle eingestellt."
        return state

    guild = bot.get_guild(HOME_GUILD_ID)
    if guild is None:
        state["problem"] = "Der Bot ist nicht auf dem Support-Server."
        return state

    role = guild.get_role(int(role_id))
    if role is None:
        state["problem"] = "Die eingestellte Rolle gibt es nicht mehr."
        return state

    state["name"] = role.name
    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        state["problem"] = "Dem Bot fehlt das Recht „Rollen verwalten“."
        return state
    if role >= me.top_role:
        state["problem"] = (
            "Die Rolle steht über der Bot-Rolle — Discord lässt sie so "
            "nicht vergeben. Bot-Rolle höher ziehen."
        )
        return state

    state["ok"] = True
    state["members"] = len(role.members)
    return state


def _key_dm(key: str, laufzeit: str) -> discord.ui.LayoutView:
    """
    The DM carrying a fresh licence key.

    Components V2 with the bot's own emojis, like the rest of what it
    sends — a plain wall of markdown in the middle of a bot that speaks
    in panels everywhere else reads like a phishing attempt.

    The key sits in a code block so a phone keyboard does not autocorrect
    it and so it can be tapped to copy.
    """
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(build_container(
        TextDisplay(f"## {PREMIUM} Dein Premium-Key"),
        Separator(visible=True),
        TextDisplay(f"```\n{key}\n```"),
        Separator(visible=True),
        TextDisplay(
            f"{UPTIME} **Laufzeit:** {laufzeit}\n"
            f"{ZBOT} **Gilt für:** Template-Bot"
        ),
        Separator(visible=True),
        TextDisplay(
            f"{NEXT} **So löst du ihn ein**\n"
            f"> {STAR} Dashboard öffnen → Reiter **Premium**\n"
            f"> {STAR} Key eintragen und auf **Einlösen** klicken\n"
            f"> {STAR} Danach erscheint der Einladungslink für den Bot"
        ),
        Separator(visible=True),
        TextDisplay(
            f"{ZSAFE} Der Key wird beim Einlösen fest an dein "
            "Discord-Konto gebunden und lässt sich danach nicht mehr "
            "übertragen."
        ),
        TextDisplay(
            f"-# {ZWARNING} Wir speichern den Key nur verschlüsselt — "
            "diese Nachricht ist die einzige Kopie. Bitte gut aufheben."
        ),
        accent_color=0xFAA61A,
    ))

    dashboard = dashboard_url()
    if dashboard:
        view.add_item(discord.ui.ActionRow(
            discord.ui.Button(
                label="Zum Dashboard",
                style=discord.ButtonStyle.link,
                url=f"{dashboard}/dashboard/premium",
            )
        ))
    return view


@router.post("/keys", summary="Mint a new key")
async def create_key(data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Create a licence key and optionally DM it to the buyer.

    Replaces the old /key command. Minting a licence is billing work: it
    belongs in one place, with an audit entry, rather than in a chat
    command only three people may run.
    """
    if not os.getenv(store.PEPPER_ENV, "").strip():
        # Setting the pepper later would invalidate every key issued
        # before it, so refuse rather than produce worthless keys.
        raise HTTPException(
            status_code=503,
            detail=f"{store.PEPPER_ENV} ist nicht gesetzt. Ohne diesen Wert "
                   "wären die Keys unsicher gespeichert — und wird er später "
                   "gesetzt, verfallen alle vorher erstellten Keys.",
        )

    try:
        days = int(data.get("days", 30))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Laufzeit muss eine Zahl sein.")
    if days < 0 or days > 3650:
        raise HTTPException(
            status_code=400, detail="Laufzeit: 0 (unbegrenzt) bis 3650 Tage."
        )

    note = str(data.get("note") or "")[:200]
    actor = str(data.get("actor") or "dashboard")
    recipient = str(data.get("user_id") or "").strip()

    created = store.create_key(created_by=actor, duration_days=days, note=note)
    laufzeit = "unbegrenzt" if days == 0 else f"{days} Tage ab Einlösung"

    # Delivery is best effort and reported honestly: the key exists
    # either way, and pretending otherwise would lose it.
    delivery = "none"
    if recipient.isdigit():
        user = bot.get_user(int(recipient))
        if user is None:
            try:
                user = await bot.fetch_user(int(recipient))
            except discord.HTTPException:
                user = None

        if user is None:
            delivery = "unknown_user"
        else:
            try:
                await user.send(view=_key_dm(created["key"], laufzeit))
                delivery = "sent"
            except discord.Forbidden:
                delivery = "dms_closed"
            except discord.HTTPException:
                delivery = "failed"

    await feature_audit.log_action(
        "premium_key_created", actor=actor,
        detail=f"days={days} delivery={delivery}",
    )

    messages = {
        "sent": "Key erstellt und per DM verschickt.",
        "dms_closed": "Key erstellt — die DM kam nicht an, die "
                      "Privatnachrichten sind zu. Bitte von Hand weitergeben.",
        "unknown_user": "Key erstellt — diese Benutzer-ID kennt Discord "
                        "nicht. Bitte von Hand weitergeben.",
        "failed": "Key erstellt — die DM ist fehlgeschlagen. Bitte von "
                  "Hand weitergeben.",
        "none": "Key erstellt. Bitte weitergeben — er wird nirgends "
                "gespeichert.",
    }

    return {
        "status": "success",
        # The one and only time the key is ever readable.
        "key": created["key"],
        "duration_days": days,
        "delivery": delivery,
        "result": messages[delivery],
    }


@router.post("/revoke", summary="Revoke a key")
async def revoke_key(data: dict, bot: "universitybot" = Depends(get_bot)):
    key = str(data.get("key") or "").strip()
    key_hash = str(data.get("key_hash") or "").strip()

    undo = bool(data.get("undo"))

    if key:
        key_hash = store.hash_key(key)

    if not key_hash:
        raise HTTPException(status_code=400, detail="Kein Key angegeben.")

    # Read the owner *before* changing anything: the template bot has to
    # be told which account lost its licence.
    owner = store.owner_of_hash(key_hash)

    ok = store.unrevoke_hash(key_hash) if undo else store.revoke_hash(key_hash)
    if not ok:
        raise HTTPException(status_code=404, detail="Diesen Key gibt es nicht.")

    await feature_audit.log_action(
        "premium_unrevoked" if undo else "premium_revoked", actor="dashboard"
    )

    result = "Die Sperre wurde aufgehoben." if undo else "Der Key wurde gesperrt."
    notified = None

    if owner:
        now_premium = store.status(owner)["premium"]

        if undo:
            # Lifting a block used to tell the other side nothing at all.
            # Its cache still held "no premium" for up to five minutes,
            # so the dashboard said active while the bot said no — the
            # worst kind of wrong, because it looks fixed.
            if now_premium:
                notified = await _tell_partner("licence-refresh", owner)
                if notified is True:
                    result += " Premium gilt im Template-Bot wieder sofort."
                elif notified is False:
                    result += (
                        " Der Template-Bot konnte nicht benachrichtigt werden —"
                        " dort greift es spätestens nach 5 Minuten."
                    )
        else:
            # Only when nothing valid is left: somebody may hold two
            # licences, and revoking one must not cut the other.
            if not now_premium:
                notified = await _tell_partner("licence-revoked", owner)
                if notified is False:
                    result += (
                        " Der Template-Bot konnte nicht benachrichtigt werden — "
                        "dort greift es, sobald er erneut nachfragt "
                        "(spätestens nach 5 Minuten)."
                    )
                elif notified is True:
                    result += " Premium wurde im Template-Bot sofort entzogen."

    return {"status": "success", "result": result, "notified": notified}


@router.post("/delete", summary="Delete a key for good")
async def delete_key(data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Remove a key row entirely.

    Revoking keeps the history; deleting is for rows that should never
    have existed. If the row was still granting premium, the template
    bot is told, or the licence would live on there until its cache
    expires.
    """
    key_hash = str(data.get("key_hash") or "").strip()
    if not key_hash:
        raise HTTPException(status_code=400, detail="Kein Key angegeben.")

    owner = store.owner_of_hash(key_hash)
    was_active = bool(owner) and store.status(owner)["premium"]

    if not store.delete_hash(key_hash):
        raise HTTPException(status_code=404, detail="Diesen Key gibt es nicht.")

    result = "Der Key wurde endgültig gelöscht."
    notified = None
    if was_active and owner and not store.status(owner)["premium"]:
        notified = await _tell_partner("licence-revoked", owner)
        if notified is True:
            result += " Premium wurde im Template-Bot sofort entzogen."
        elif notified is False:
            result += (
                " Der Template-Bot konnte nicht benachrichtigt werden — "
                "dort greift es spätestens nach 5 Minuten."
            )

    await feature_audit.log_action("premium_key_deleted", actor="dashboard")
    return {"status": "success", "result": result, "notified": notified}


@router.post("/purge", summary="Delete a whole group of keys")
async def purge_keys(data: dict, bot: "universitybot" = Depends(get_bot)):
    """
    Bulk cleanup: revoked, expired or never-redeemed keys.

    There is no "delete everything" on purpose — that would take the
    rows currently granting people premium with it.
    """
    what = str(data.get("what") or "").strip()
    try:
        removed = store.purge(what)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Unbekannte Gruppe. Erlaubt: revoked, expired, unclaimed.",
        )

    labels = {
        "revoked": "gesperrte",
        "expired": "abgelaufene",
        "unclaimed": "nicht eingelöste",
    }
    await feature_audit.log_action(
        "premium_keys_purged", actor="dashboard", detail=f"{what}={removed}"
    )
    return {
        "status": "success",
        "removed": removed,
        "result": f"{removed} {labels[what]} Keys gelöscht."
                  if removed else f"Keine {labels[what]} Keys vorhanden.",
    }


async def _tell_partner(endpoint: str, user_id: str) -> Optional[bool]:
    """
    Tell the template bot that an account's licence changed.

    `endpoint` is "licence-revoked" or "licence-refresh". Both clear the
    other side's cache; the first also drops any local unlock.

    Returns True on success, False when the call failed, and None when
    no template bot URL is configured — three different situations, and
    the dashboard says which one happened rather than claiming success.

    Without this a change only takes effect once the other side's cache
    expires, up to five minutes later.
    """
    base = (os.getenv("TEMPLATE_BOT_URL") or "").strip().rstrip("/")
    token = os.getenv(PARTNER_TOKEN_ENV, "").strip()
    if not base or not token:
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{base}/internal/{endpoint}",
                headers={"X-Partner-Token": token},
                json={"user_id": str(user_id)},
            ) as response:
                return response.status == 200
    except Exception:  # noqa: BLE001 - the revoke must not fail on this
        return False
