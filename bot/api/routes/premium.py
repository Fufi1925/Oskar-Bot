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

from fastapi import APIRouter, Depends, Header, HTTPException

from api.dependencies import get_bot
from utils import feature_audit
from utils import premium_store as store

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
    return {
        "template_bot": store.status(user_id, product="template_bot"),
        # The main bot has nothing to sell yet. Saying so here keeps the
        # dashboard from inventing an answer.
        "main_bot": {"premium": False, "coming_soon": True},
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
    Recent keys.

    Only hashes are stored, so the list can never show a key itself. A
    key the buyer lost has to be revoked and replaced.
    """
    return {"keys": store.list_keys(limit)}


@router.post("/revoke", summary="Revoke a key")
async def revoke_key(data: dict, bot: "universitybot" = Depends(get_bot)):
    key = str(data.get("key") or "").strip()
    key_hash = str(data.get("key_hash") or "").strip()

    if key:
        ok = store.revoke(key)
    elif key_hash:
        # From the admin list, where only the hash is known.
        store.ensure()
        import sqlite3
        with sqlite3.connect(store.DB_PATH) as conn:
            cur = conn.execute(
                "UPDATE premium_keys SET revoked = 1 WHERE key_hash = ?",
                (key_hash,),
            )
            ok = cur.rowcount > 0
    else:
        raise HTTPException(status_code=400, detail="Kein Key angegeben.")

    if not ok:
        raise HTTPException(status_code=404, detail="Diesen Key gibt es nicht.")

    await feature_audit.log_action("premium_revoked", actor="dashboard")
    return {"status": "success", "result": "Der Key wurde gesperrt."}
