"""Session-scoped billing API and independently signed public webhook."""
import logging
import os

import stripe
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from api.dependencies import get_bot, run_on_bot_loop, security, verify_api_key
from utils import stripe_billing as billing, feature_gates, premium_membership

def require_billing_key(request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(security)):
    # Billing never inherits the general API's keyless local-development mode.
    if not os.getenv("DASHBOARD_API_KEY"):
        raise HTTPException(503, "billing_authentication")
    return verify_api_key(request, credentials)


router = APIRouter(dependencies=[Depends(require_billing_key)])
webhook_router = APIRouter()
logger = logging.getLogger(__name__)


class CheckoutInput(BaseModel):
    plan: str
    locale: str = "en"


async def call(operation):
    try:
        return await operation
    except billing.BillingError as exc:
        raise HTTPException(exc.status, exc.code) from None
    except stripe.StripeError as exc:
        logger.warning("Stripe API failure: %s", type(exc).__name__)
        raise HTTPException(502, "billing_provider") from None


@router.get("/catalog")
async def catalog(actor: str):
    try:
        billing.user_id(actor)
        return billing.catalog()
    except billing.BillingError as exc:
        raise HTTPException(exc.status, exc.code) from None


@router.get("/me")
async def me(actor: str):
    try:
        return billing.summary(actor)
    except billing.BillingError as exc:
        raise HTTPException(exc.status, exc.code) from None


@router.post("/checkout")
async def checkout(data: CheckoutInput, actor: str):
    return await call(billing.checkout(actor, data.plan, data.locale))


@router.post("/portal")
async def portal(actor: str):
    return await call(billing.portal(actor))


@router.get("/checkout-status")
async def checkout_status(actor: str, session_id: str):
    return await call(billing.checkout_status(actor, session_id))


async def payment_notice(uid):
    # Discord objects belong to the bot's loop; failure must not roll back payment.
    from utils.premium_notifications import notify_payment
    try:
        await run_on_bot_loop(notify_payment(get_bot(), premium_membership.account_status(uid)))
    except Exception as exc:
        logger.warning("Stripe Premium notice unavailable: %s", type(exc).__name__)


@webhook_router.post("/webhook")
async def webhook(request: Request, background: BackgroundTasks):
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "billing_unavailable")
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 1_048_576:
            raise HTTPException(413, "billing_payload")
    try:
        event = stripe.Webhook.construct_event(bytes(payload), request.headers.get("stripe-signature", ""), secret)
    except (ValueError, stripe.SignatureVerificationError):
        raise HTTPException(400, "billing_signature") from None
    try:
        result = await billing.process_event(event)
    except billing.BillingError as exc:
        logger.warning("Stripe webhook reconciliation: %s", exc.code)
        raise HTTPException(exc.status, exc.code) from None
    except stripe.StripeError as exc:
        logger.warning("Stripe webhook provider failure: %s", type(exc).__name__)
        raise HTTPException(503, "billing_retry") from None
    if result.get("changed"):
        await run_on_bot_loop(feature_gates.refresh_premium_guilds())
    if result.get("notify_user"):
        background.add_task(payment_notice, result["notify_user"])
    return {"received": True}
