"""Hosted Stripe Checkout and durable, payment-backed Premium entitlements.

No card data or event payloads are stored locally. Only signed webhooks may
grant access; browser redirects and subscription status alone never do.
"""
from __future__ import annotations

import os
import asyncio
import re
import secrets
import string
import time
import uuid
import weakref
from urllib.parse import urlsplit

import stripe
from utils import premium_membership as membership
from utils.links import dashboard_url

API_VERSION = "2026-09-30.endive"
PLANS = {
    "monthly": {"amount": 299, "interval": "month", "env": "STRIPE_PRICE_MONTHLY"},
    "yearly": {"amount": 1299, "interval": "year", "env": "STRIPE_PRICE_YEARLY"},
    "lifetime": {"amount": 2999, "interval": None, "env": "STRIPE_PRICE_LIFETIME"},
}
EVENTS = (
    "checkout.session.completed", "checkout.session.async_payment_succeeded",
    "checkout.session.async_payment_failed", "invoice.paid", "invoice.payment_failed",
    "customer.subscription.created", "customer.subscription.updated",
    "customer.subscription.deleted", "customer.subscription.paused",
    "customer.subscription.resumed", "charge.refunded", "charge.dispute.created",
    "radar.early_fraud_warning.created",
)
_http_clients = weakref.WeakKeyDictionary()


class BillingError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def mode():
    value = os.getenv("STRIPE_MODE", "test").strip()
    if value not in {"test", "live"}:
        raise BillingError("billing_configuration", 503)
    return value


def configured():
    return bool(os.getenv("STRIPE_SECRET_KEY") and os.getenv("STRIPE_WEBHOOK_SECRET")
                and os.getenv("STRIPE_PORTAL_CONFIGURATION")
                and all(os.getenv(p["env"]) for p in PLANS.values()))


def client():
    key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not key.startswith((f"sk_{mode()}_", f"rk_{mode()}_")):
        raise BillingError("billing_unavailable", 503)
    loop = asyncio.get_running_loop()
    http = _http_clients.get(loop)
    if http is None:
        http = stripe.HTTPXClient(timeout=15)
        _http_clients[loop] = http
    return stripe.StripeClient(key, stripe_version=API_VERSION, max_network_retries=2, http_client=http)


async def close_client():
    http = _http_clients.pop(asyncio.get_running_loop(), None)
    if http:
        await http.close_async()


def origin():
    value = os.getenv("STRIPE_PUBLIC_URL") or os.getenv("NEXTAUTH_URL") or dashboard_url()
    parsed = urlsplit(value or "")
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}):
        raise BillingError("billing_configuration", 503)
    return value.rstrip("/")


def user_id(value):
    uid = str(value or "")
    if not re.fullmatch(r"[0-9]{17,20}", uid):
        raise BillingError("billing_authentication", 401)
    return uid


def object_id(value):
    return value.get("id", "") if hasattr(value, "get") else str(value or "")


def as_dict(value):
    # Stripe Python 16 resources intentionally no longer implement dict.get().
    return value.to_dict() if isinstance(value, stripe.StripeObject) else value


def ensure():
    membership.ensure()
    with membership._connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS stripe_customers (
          user_id TEXT NOT NULL, mode TEXT NOT NULL, customer_id TEXT NOT NULL UNIQUE,
          PRIMARY KEY(user_id,mode));
        CREATE TABLE IF NOT EXISTS stripe_intents (
          user_id TEXT NOT NULL, mode TEXT NOT NULL, plan TEXT NOT NULL,
          nonce TEXT NOT NULL UNIQUE, locale TEXT NOT NULL, created_at INTEGER NOT NULL,
          session_id TEXT, completed INTEGER NOT NULL DEFAULT 0,
          PRIMARY KEY(user_id,mode));
        CREATE TABLE IF NOT EXISTS stripe_subscriptions (
          id TEXT PRIMARY KEY,user_id TEXT NOT NULL,mode TEXT NOT NULL,plan TEXT NOT NULL,
          status TEXT NOT NULL,cancel_at_period_end INTEGER NOT NULL,period_end INTEGER NOT NULL,
          updated_at INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS stripe_payments (
          id TEXT PRIMARY KEY,user_id TEXT NOT NULL,mode TEXT NOT NULL,plan TEXT NOT NULL,
          subscription_id TEXT NOT NULL DEFAULT '',charge_id TEXT NOT NULL DEFAULT '',
          expires_at INTEGER NOT NULL,lifetime INTEGER NOT NULL,blocked INTEGER NOT NULL DEFAULT 0);
        CREATE INDEX IF NOT EXISTS stripe_payments_user ON stripe_payments(user_id,mode);
        CREATE TABLE IF NOT EXISTS stripe_risks (charge_id TEXT PRIMARY KEY,kind TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stripe_events (id TEXT PRIMARY KEY,type TEXT NOT NULL,received_at INTEGER NOT NULL);
        """)


def catalog():
    return {"enabled": configured(), "mode": mode(), "currency": "eur", "slots": membership.MAX_SLOTS,
            "plans": [{"id": name, "amount": value["amount"], "interval": value["interval"]}
                      for name, value in PLANS.items()]}


def summary(uid):
    uid = user_id(uid); ensure()
    with membership._connect() as db:
        customer = db.execute("SELECT 1 FROM stripe_customers WHERE user_id=? AND mode=?", (uid, mode())).fetchone()
        subs = db.execute("SELECT plan,status,cancel_at_period_end,period_end FROM stripe_subscriptions WHERE user_id=? AND mode=?", (uid, mode())).fetchall()
    return {**catalog(), "has_customer": bool(customer), "subscriptions": [dict(r) for r in subs]}


async def validate_price(api, plan):
    expected = PLANS[plan]; price_id = os.getenv(expected["env"], "")
    if not price_id:
        raise BillingError("billing_unavailable", 503)
    price = as_dict(await api.v1.prices.retrieve_async(price_id))
    recurring = price.get("recurring") or {}
    if (not price.get("active") or price.get("currency") != "eur"
            or price.get("unit_amount") != expected["amount"]
            or bool(price.get("livemode")) != (mode() == "live")
            or recurring.get("interval") != expected["interval"]
            or (recurring and recurring.get("interval_count") != 1)
            or price.get("tax_behavior") != "inclusive"):
        raise BillingError("billing_configuration", 503)
    return price_id


async def checkout(uid, plan, locale="en"):
    uid = user_id(uid)
    if plan not in PLANS:
        raise BillingError("billing_plan")
    if not configured():
        raise BillingError("billing_unavailable", 503)
    public = origin(); api = client(); ensure(); now = int(time.time())
    # Durable reservation + Stripe idempotency work across workers and retries.
    with membership._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT expires_at,revoked FROM premium_accounts WHERE user_id=?", (uid,)).fetchone()
        active_sub = db.execute("SELECT 1 FROM stripe_subscriptions WHERE user_id=? AND mode=? AND status NOT IN ('canceled','incomplete_expired')", (uid, mode())).fetchone()
        if (current and not current["revoked"] and current["expires_at"] > now) or active_sub:
            raise BillingError("billing_already_active", 409)
        previous = db.execute("SELECT * FROM stripe_intents WHERE user_id=? AND mode=?", (uid, mode())).fetchone()
        if previous and not previous["completed"] and previous["created_at"] + 3600 > now:
            if previous["plan"] != plan:
                raise BillingError("billing_checkout_pending", 409)
            intent = dict(previous)
        else:
            intent = {"nonce": str(uuid.uuid4()), "locale": "de" if locale == "de" else "en", "created_at": now}
            db.execute("INSERT INTO stripe_intents(user_id,mode,plan,nonce,locale,created_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id,mode) DO UPDATE SET plan=excluded.plan,nonce=excluded.nonce,locale=excluded.locale,created_at=excluded.created_at,session_id=NULL,completed=0",
                       (uid, mode(), plan, intent["nonce"], intent["locale"], now))
        row = db.execute("SELECT customer_id FROM stripe_customers WHERE user_id=? AND mode=?", (uid, mode())).fetchone()
        customer_id = row[0] if row else None
        label = db.execute("SELECT value FROM premium_v2_meta WHERE key='stripe_integration_identifier'").fetchone()
        identifier = label[0] if label else "university_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(8))
        db.execute("INSERT OR IGNORE INTO premium_v2_meta(key,value) VALUES('stripe_integration_identifier',?)", (identifier,))
    price_id = await validate_price(api, plan)
    if not customer_id:
        customer = as_dict(await api.v1.customers.create_async({"metadata": {"discord_user_id": uid, "application": "university_bot"}},
                                                       options={"idempotency_key": f"university-customer-{mode()}-{uid}"}))
        customer_id = customer["id"]
        with membership._connect() as db:
            if not db.execute("SELECT 1 FROM stripe_intents WHERE nonce=?", (intent["nonce"],)).fetchone():
                raise BillingError("billing_checkout_cancelled", 409)
            db.execute("INSERT OR IGNORE INTO stripe_customers VALUES(?,?,?)", (uid, mode(), customer_id))
    metadata = {"discord_user_id": uid, "plan": plan, "application": "university_bot"}
    params = {"mode": "payment" if plan == "lifetime" else "subscription", "customer": customer_id,
              "client_reference_id": uid, "line_items": [{"price": price_id, "quantity": 1}],
              "metadata": metadata, "locale": intent["locale"], "integration_identifier": identifier,
              "expires_at": intent["created_at"] + 3600,
              "success_url": public + "/dashboard/premium?payment=success&session_id={CHECKOUT_SESSION_ID}",
              "cancel_url": public + "/dashboard/premium?payment=cancelled"}
    params["payment_intent_data" if plan == "lifetime" else "subscription_data"] = {"metadata": metadata}
    session = as_dict(await api.v1.checkout.sessions.create_async(params, options={"idempotency_key": intent["nonce"]}))
    with membership._connect() as db:
        stored = db.execute("UPDATE stripe_intents SET session_id=? WHERE nonce=?", (session["id"], intent["nonce"])).rowcount
    if not stored:
        if session.get("status") == "open":
            as_dict(await api.v1.checkout.sessions.expire_async(session["id"]))
        raise BillingError("billing_checkout_cancelled", 409)
    return {"url": hosted_url(session.get("url"), "checkout.stripe.com")}


def hosted_url(value, hostname):
    parsed = urlsplit(value or "")
    if parsed.scheme != "https" or parsed.hostname != hostname or parsed.username or parsed.password:
        raise BillingError("billing_provider", 502)
    return value


async def portal(uid):
    uid = user_id(uid); ensure()
    with membership._connect() as db:
        row = db.execute("SELECT customer_id FROM stripe_customers WHERE user_id=? AND mode=?", (uid, mode())).fetchone()
    if not row:
        raise BillingError("billing_customer", 404)
    config = os.getenv("STRIPE_PORTAL_CONFIGURATION")
    if not config:
        raise BillingError("billing_unavailable", 503)
    session = as_dict(await client().v1.billing_portal.sessions.create_async({"customer": row[0], "configuration": config,
                                                                    "return_url": origin() + "/dashboard/premium"}))
    return {"url": hosted_url(session.get("url"), "billing.stripe.com")}


async def checkout_status(uid, session_id):
    uid = user_id(uid); ensure()
    if not re.fullmatch(r"cs_[A-Za-z0-9_]{1,200}", session_id):
        raise BillingError("billing_session", 404)
    with membership._connect() as db:
        row = db.execute("SELECT customer_id FROM stripe_customers WHERE user_id=? AND mode=?", (uid, mode())).fetchone()
    if not row:
        raise BillingError("billing_session", 404)
    session = as_dict(await client().v1.checkout.sessions.retrieve_async(session_id))
    if session.get("client_reference_id") != uid or object_id(session.get("customer")) != row[0]:
        raise BillingError("billing_session", 404)
    # This endpoint reports only. It can never grant Premium.
    account = membership.account_status(uid)
    return {"payment_status": session.get("payment_status"), "fulfilled": bool(account["premium"]),
            "session_status": session.get("status")}


async def cancel_for_erasure(uid):
    """Stop open checkouts and recurring charges before an approved erasure."""
    uid = user_id(uid); ensure()
    with membership._connect() as db:
        customers = db.execute("SELECT * FROM stripe_customers WHERE user_id=?", (uid,)).fetchall()
        intents = db.execute("SELECT session_id FROM stripe_intents WHERE user_id=?", (uid,)).fetchall()
    if not customers:
        return
    if any(row["mode"] != mode() for row in customers):
        raise BillingError("billing_erasure_mode", 409)
    api = client()
    for intent in intents:
        if intent[0]:
            session = as_dict(await api.v1.checkout.sessions.retrieve_async(intent[0]))
            if session.get("status") == "open":
                as_dict(await api.v1.checkout.sessions.expire_async(intent[0]))
    for customer in customers:
        subscriptions = await api.v1.subscriptions.list_async({"customer": customer["customer_id"], "status": "all", "limit": 100})
        async for subscription in subscriptions.auto_paging_iter():
            subscription = as_dict(subscription)
            if subscription.get("status") not in {"canceled", "incomplete_expired"}:
                as_dict(await api.v1.subscriptions.cancel_async(subscription["id"], {"invoice_now": False, "prorate": False}))


def owner(customer_id):
    with membership._connect() as db:
        row = db.execute("SELECT user_id FROM stripe_customers WHERE customer_id=? AND mode=?", (customer_id, mode())).fetchone()
    return row[0] if row else None


async def subscription_snapshot(api, value):
    sub = as_dict(await api.v1.subscriptions.retrieve_async(object_id(value)))
    uid = owner(object_id(sub.get("customer")))
    meta = sub.get("metadata") or {}; plan = meta.get("plan")
    if not uid or meta.get("application") != "university_bot" or meta.get("discord_user_id") != uid or plan not in {"monthly", "yearly"}:
        return None
    items = sub.get("items", {}).get("data", [])
    if len(items) != 1 or object_id(items[0].get("price")) != os.getenv(PLANS[plan]["env"]) or items[0].get("quantity") != 1:
        raise BillingError("billing_subscription", 409)
    return {"id": sub["id"], "user_id": uid, "mode": mode(), "plan": plan,
            "status": sub["status"], "cancel_at_period_end": int(bool(sub.get("cancel_at_period_end"))),
            "period_end": int(items[0].get("current_period_end") or 0)}


async def charges_for_invoice(api, invoice_id):
    result = as_dict(await api.v1.invoice_payments.list_async({"invoice": invoice_id, "status": "paid", "limit": 100}))
    charges = []
    for item in result.get("data", []):
        payment = item.get("payment") or {}
        if payment.get("type") == "payment_intent":
            intent = as_dict(await api.v1.payment_intents.retrieve_async(object_id(payment.get("payment_intent")), {"expand": ["latest_charge"]}))
            charge = intent.get("latest_charge")
        elif payment.get("type") == "charge":
            charge = as_dict(await api.v1.charges.retrieve_async(object_id(payment.get("charge"))))
        else:
            charge = None
        if charge:
            charges.append(charge)
    return charges


def sync_account(db, uid):
    """Recalculate from absolute paid periods, never extend by event count."""
    current = db.execute("SELECT * FROM premium_accounts WHERE user_id=?", (uid,)).fetchone()
    # An administrator's later override takes precedence over billing events.
    if current and current["source"] != f"stripe:{mode()}" and not current["revoked"] and current["expires_at"] > int(time.time()):
        return
    payments = db.execute("SELECT * FROM stripe_payments WHERE user_id=? AND mode=? AND blocked=0 ORDER BY expires_at DESC", (uid, mode())).fetchall()
    best = payments[0] if payments else None
    now = int(time.time()); expires = int(best["expires_at"]) if best else now
    lifetime = int(bool(best and best["lifetime"]))
    if current and current["source"] == f"stripe:{mode()}" and current["expires_at"] == expires and current["revoked"] == int(not best) and current["lifetime"] == lifetime:
        return
    db.execute("""INSERT INTO premium_accounts(user_id,granted_at,expires_at,duration_days,source,note,notice_pending,revoked,lifetime)
      VALUES(?,?,?,?,?,'Stripe payment',1,?,?) ON CONFLICT(user_id) DO UPDATE SET expires_at=excluded.expires_at,
      granted_at=CASE WHEN premium_accounts.source=excluded.source AND premium_accounts.expires_at>? THEN premium_accounts.granted_at ELSE excluded.granted_at END,
      duration_days=excluded.duration_days,source=excluded.source,note=excluded.note,
      notice_pending=CASE WHEN excluded.revoked=0 THEN 1 ELSE 0 END,revoked=excluded.revoked,lifetime=excluded.lifetime""",
      (uid, now, expires, 0 if lifetime else max(0, (expires - now) // 86400), f"stripe:{mode()}", int(not best), lifetime, now))


async def process_event(event):
    """Reconcile with current Stripe objects before atomic, deduplicated writes."""
    event = as_dict(event)
    ensure()
    if bool(event.get("livemode")) != (mode() == "live"):
        raise BillingError("billing_mode", 400)
    kind = event.get("type", ""); eid = event.get("id", "")
    if kind not in EVENTS:
        return {"received": True}
    if not re.fullmatch(r"evt_[A-Za-z0-9]+", eid):
        raise BillingError("billing_event")
    with membership._connect() as db:
        if db.execute("SELECT 1 FROM stripe_events WHERE id=?", (eid,)).fetchone():
            return {"received": True, "duplicate": True}
    api = client(); obj = event["data"]["object"]; payment = None; sub = None; uid = None; risk = None; completed = None
    if kind.startswith("checkout.session."):
        session = as_dict(await api.v1.checkout.sessions.retrieve_async(obj["id"]))
        uid = owner(object_id(session.get("customer")))
        meta = session.get("metadata") or {}; plan = meta.get("plan")
        if not uid or session.get("client_reference_id") != uid or meta.get("application") != "university_bot" or plan not in PLANS:
            return {"received": True}
        completed = session["id"] if session.get("status") in {"complete", "expired"} else None
        if session.get("subscription"):
            sub = await subscription_snapshot(api, session["subscription"])
        elif plan == "lifetime" and session.get("payment_status") == "paid":
            lines = as_dict(await api.v1.checkout.sessions.list_line_items_async(session["id"], {"limit": 2}))
            items = lines.get("data", [])
            if (session.get("amount_total") != 2999 or session.get("currency") != "eur" or len(items) != 1
                    or object_id(items[0].get("price")) != os.getenv(PLANS[plan]["env"]) or items[0].get("quantity") != 1):
                raise BillingError("billing_payment", 409)
            intent = as_dict(await api.v1.payment_intents.retrieve_async(object_id(session.get("payment_intent")), {"expand": ["latest_charge"]}))
            charge = intent.get("latest_charge") or {}
            payment = {"id": session["id"], "user_id": uid, "mode": mode(), "plan": plan, "subscription_id": "",
                       "charge_id": charge.get("id", ""), "expires_at": membership.LIFETIME_EXPIRES_AT, "lifetime": 1,
                       "blocked": int(bool(charge.get("disputed") or charge.get("refunded")))}
    elif kind.startswith("invoice."):
        invoice = as_dict(await api.v1.invoices.retrieve_async(obj["id"]))
        sid = object_id(((invoice.get("parent") or {}).get("subscription_details") or {}).get("subscription"))
        if sid:
            sub = await subscription_snapshot(api, sid)
        if sub and kind == "invoice.paid" and invoice.get("status") == "paid":
            uid = sub["user_id"]; plan = sub["plan"]
            lines = invoice.get("lines", {}).get("data", [])
            matching = [line for line in lines if object_id(((line.get("pricing") or {}).get("price_details") or {}).get("price")) == os.getenv(PLANS[plan]["env"])]
            if invoice.get("currency") != "eur" or len(matching) != 1 or int(invoice.get("amount_paid") or 0) < PLANS[plan]["amount"]:
                raise BillingError("billing_invoice", 409)
            charges = await charges_for_invoice(api, invoice["id"])
            # Ordinary Checkout invoices have one successful payment. Ignore unrelated plans.
            if len(charges) != 1:
                raise BillingError("billing_invoice_payment", 409)
            charge = charges[0]
            payment = {"id": invoice["id"], "user_id": uid, "mode": mode(), "plan": plan, "subscription_id": sid,
                       "charge_id": charge["id"], "expires_at": int(matching[0].get("period", {}).get("end") or 0),
                       "lifetime": 0, "blocked": int(bool(charge.get("disputed") or charge.get("refunded")))}
    elif kind.startswith("customer.subscription."):
        sub = await subscription_snapshot(api, obj["id"])
    elif kind in {"charge.refunded", "charge.dispute.created", "radar.early_fraud_warning.created"}:
        cid = obj["id"] if kind == "charge.refunded" else object_id(obj.get("charge"))
        charge = as_dict(await api.v1.charges.retrieve_async(cid))
        if owner(object_id(charge.get("customer"))) and (kind != "charge.refunded" or charge.get("refunded")):
            risk = (cid, kind)
    affected = set(); new_payment = False
    with membership._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM stripe_events WHERE id=?", (eid,)).fetchone():
            return {"received": True, "duplicate": True}
        # An erasure may have removed the binding while Stripe was queried.
        subject = payment["user_id"] if payment else sub["user_id"] if sub else None
        if subject and not db.execute("SELECT 1 FROM stripe_customers WHERE user_id=? AND mode=?", (subject, mode())).fetchone():
            return {"received": True}
        if sub:
            sub["updated_at"] = int(event.get("created") or 0)
            db.execute("INSERT INTO stripe_subscriptions VALUES(:id,:user_id,:mode,:plan,:status,:cancel_at_period_end,:period_end,:updated_at) ON CONFLICT(id) DO UPDATE SET status=excluded.status,cancel_at_period_end=excluded.cancel_at_period_end,period_end=excluded.period_end,updated_at=excluded.updated_at WHERE excluded.updated_at>=stripe_subscriptions.updated_at AND (stripe_subscriptions.status!='canceled' OR excluded.status='canceled')", sub)
        if payment:
            if db.execute("SELECT 1 FROM stripe_risks WHERE charge_id=?", (payment["charge_id"],)).fetchone():
                payment["blocked"] = 1
            new_payment = db.execute("INSERT OR IGNORE INTO stripe_payments VALUES(:id,:user_id,:mode,:plan,:subscription_id,:charge_id,:expires_at,:lifetime,:blocked)", payment).rowcount > 0
            # Later snapshots may revoke a payment, but must never clear a block.
            changed = db.execute("UPDATE stripe_payments SET blocked=? WHERE id=? AND blocked<?", (payment["blocked"], payment["id"], payment["blocked"])).rowcount
            if new_payment or changed:
                affected.add(payment["user_id"])
        if risk:
            db.execute("INSERT OR IGNORE INTO stripe_risks VALUES(?,?)", risk)
            affected.update(r[0] for r in db.execute("SELECT user_id FROM stripe_payments WHERE charge_id=?", (risk[0],)))
            db.execute("UPDATE stripe_payments SET blocked=1 WHERE charge_id=?", (risk[0],))
        if completed:
            db.execute("UPDATE stripe_intents SET completed=1 WHERE session_id=?", (completed,))
        for affected_uid in affected:
            sync_account(db, affected_uid)
        db.execute("INSERT INTO stripe_events VALUES(?,?,?)", (eid, kind, int(time.time())))
    return {"received": True, "notify_user": uid if new_payment and payment and not payment["blocked"] else None,
            "changed": bool(affected)}
