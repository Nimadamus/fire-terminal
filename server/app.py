"""The FIRE licence service.

Small on purpose. It does four things:

  * turns a completed Stripe checkout into a licence key
  * hands that key back to the success page so nobody waits on an email
  * exchanges a key for a signed token the application will trust
  * keeps the token in step with what Stripe says about the subscription

Everything else, including the customer's card details, name and billing
address, stays with Stripe. This service never sees a card number and stores
nothing it does not need to answer "is this subscription live".

Failure posture: if this service is down, existing customers keep working until
their token's grace window runs out. New activations fail loudly. That is the
right way round for a trading tool.
"""
from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import licences
import store

log = logging.getLogger("fire.licence")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)-7s %(message)s")

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
PRICE_MONTHLY = os.environ.get("STRIPE_PRICE_MONTHLY", "")
PRICE_ANNUAL = os.environ.get("STRIPE_PRICE_ANNUAL", "")
SITE_URL = os.environ.get("FIRE_SITE_URL", "").rstrip("/")
TRIAL_DAYS = int(os.environ.get("FIRE_TRIAL_DAYS", "14"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    store.init()
    if not STRIPE_SECRET:
        log.warning("STRIPE_SECRET_KEY is not set: checkout is disabled")
    if not STRIPE_WEBHOOK_SECRET:
        log.warning("STRIPE_WEBHOOK_SECRET is not set: webhooks are disabled")
    yield


# No docs endpoints. This service has four routes and publishing a schema
# browser for them only advertises surface to probe.
app = FastAPI(title="FIRE licence service", docs_url=None, redoc_url=None,
              lifespan=lifespan)


def _stripe():
    if not STRIPE_SECRET:
        raise HTTPException(503, "Billing is not configured on this service.")
    import stripe
    stripe.api_key = STRIPE_SECRET
    return stripe


# --------------------------------------------------------------------------
# The application talks to these two
# --------------------------------------------------------------------------
class ActivateIn(BaseModel):
    key: str
    install: str


class EntitlementIn(BaseModel):
    install: str
    key: str = ""


@app.post("/activate")
def activate(body: ActivateIn) -> dict[str, Any]:
    """Bind a licence key to an installation and return a signed token."""
    key = licences.normalise(body.key)
    install = (body.install or "").strip()
    if not key or not install:
        raise HTTPException(400, "That licence key does not look right.")

    record = store.licence(key)
    if record is None:
        raise HTTPException(404, "We do not recognise that licence key.")

    # Seat limit exists so one key does not become a site licence, and it is
    # generous on purpose: a laptop, a desktop and a spare should all work
    # without anybody writing in.
    if not store.install_is_bound(install, key):
        if store.install_count(key) >= int(record.get("seats") or 3):
            raise HTTPException(
                409, "That licence is already in use on the maximum number of "
                     "computers. Contact support and we will free one up.")
    store.bind_install(install, key)

    if not licences.is_usable(record):
        # Still return a token. It carries the real status, and the
        # application shows the customer exactly why it will not trade.
        log.info("activation of a non active licence, status=%s",
                 record.get("status"))
    return {"token": licences.token_for(record, install)}


@app.post("/entitlement")
def entitlement(body: EntitlementIn) -> dict[str, Any]:
    """Re-check an installation. Called periodically by the application."""
    install = (body.install or "").strip()
    if not install:
        raise HTTPException(400, "Missing installation id.")

    key = licences.normalise(body.key) or store.key_for_install(install) or ""
    record = store.licence(key) if key else None

    if record is None:
        # Never seen: hand out a trial rather than a refusal, so a fresh
        # install can be evaluated without an account.
        return {"token": licences.trial_token(install, TRIAL_DAYS)}

    store.bind_install(install, key)
    return {"token": licences.token_for(record, install)}


# --------------------------------------------------------------------------
# Checkout and the success page
# --------------------------------------------------------------------------
class CheckoutIn(BaseModel):
    plan: str = "monthly"
    email: str = ""


@app.post("/checkout")
def checkout(body: CheckoutIn) -> dict[str, str]:
    """Start a Stripe Checkout session. The website calls this."""
    stripe = _stripe()
    price = PRICE_ANNUAL if body.plan == "annual" else PRICE_MONTHLY
    if not price:
        raise HTTPException(503, "That plan is not available yet.")

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price, "quantity": 1}],
        success_url=f"{SITE_URL}/welcome?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{SITE_URL}/pricing",
        customer_email=body.email or None,
        allow_promotion_codes=True,
        # Stripe collects and stores the billing details. We do not want them.
        billing_address_collection="auto",
    )
    return {"url": session.url or ""}


@app.get("/licence")
def licence_for_session(session_id: str) -> dict[str, str]:
    """Give the success page the key that was just bought.

    This is why FIRE does not depend on an email arriving. The customer sees
    the key on screen the moment they pay, and the receipt is a backup.
    """
    record = store.licence_by_session(session_id)
    if record is None:
        # The webhook may not have landed yet. Say so, do not say "no".
        raise HTTPException(202, "Still confirming your payment.")
    return {"key": str(record["key"]), "plan": str(record["plan"]),
            "email": str(record["email"])}


@app.get("/portal")
def portal(key: str) -> dict[str, str]:
    """A link to Stripe's own billing portal: cards, invoices, cancellation."""
    stripe = _stripe()
    record = store.licence(licences.normalise(key))
    if record is None or not record.get("stripe_customer"):
        raise HTTPException(404, "We do not recognise that licence key.")
    session = stripe.billing_portal.Session.create(
        customer=str(record["stripe_customer"]),
        return_url=f"{SITE_URL}/account" if SITE_URL else None)
    return {"url": session.url}


# --------------------------------------------------------------------------
# Stripe webhooks
# --------------------------------------------------------------------------
def _period_end(subscription: Any) -> Optional[float]:
    value = None
    if isinstance(subscription, dict):
        value = subscription.get("current_period_end")
    else:
        value = getattr(subscription, "current_period_end", None)
    return float(value) if value else None


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Webhooks are not configured.")
    import stripe
    stripe.api_key = STRIPE_SECRET

    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(
            payload, signature, STRIPE_WEBHOOK_SECRET)
    except Exception as exc:
        # An unverified webhook is somebody else's traffic. Refuse it.
        log.warning("rejected webhook: %s", type(exc).__name__)
        raise HTTPException(400, "Signature check failed.") from exc

    event_id = str(event.get("id") or "")
    kind = str(event.get("type") or "")
    if event_id and store.seen_event(event_id, kind):
        return JSONResponse({"ok": True, "duplicate": True})

    obj = event["data"]["object"]
    log.info("stripe event %s", kind)

    if kind == "checkout.session.completed":
        _on_checkout_complete(stripe, obj)
    elif kind in ("customer.subscription.updated",
                  "customer.subscription.created"):
        _on_subscription_change(obj)
    elif kind == "customer.subscription.deleted":
        _on_subscription_ended(obj)
    elif kind == "invoice.payment_failed":
        _on_payment_failed(obj)

    return JSONResponse({"ok": True})


def _on_checkout_complete(stripe, session: Any) -> None:
    session_id = str(session.get("id") or "")
    customer = str(session.get("customer") or "")
    sub_id = str(session.get("subscription") or "")
    email = str((session.get("customer_details") or {}).get("email") or "")

    if store.licence_by_session(session_id):
        return                          # already issued, nothing to do

    expires, plan = None, "FIRE"
    if sub_id:
        try:
            subscription = stripe.Subscription.retrieve(sub_id)
            expires = _period_end(subscription)
            interval = (subscription["items"]["data"][0]["price"]
                        ["recurring"]["interval"])
            plan = "FIRE Annual" if interval == "year" else "FIRE Monthly"
        except Exception:
            log.warning("could not read subscription %s", sub_id)

    key = licences.new_key()
    store.create_licence(key, email=email, plan=plan, expires=expires,
                         stripe_customer=customer, stripe_sub=sub_id,
                         checkout_session=session_id)
    log.info("issued licence for %s", session_id)


def _on_subscription_change(subscription: Any) -> None:
    record = store.licence_by_subscription(str(subscription.get("id") or ""))
    if record is None:
        return
    state = str(subscription.get("status") or "")
    # Stripe's own retry window is the grace period for a failed card. Only
    # a subscription Stripe has given up on becomes an expiry here.
    status = "active" if state in ("active", "trialing", "past_due") else "expired"
    store.set_status(str(record["key"]), status, _period_end(subscription))


def _on_subscription_ended(subscription: Any) -> None:
    record = store.licence_by_subscription(str(subscription.get("id") or ""))
    if record is not None:
        store.set_status(str(record["key"]), "expired", time.time())


def _on_payment_failed(invoice: Any) -> None:
    sub_id = str(invoice.get("subscription") or "")
    record = store.licence_by_subscription(sub_id) if sub_id else None
    if record is not None:
        log.info("payment failed for %s, leaving active during Stripe retries",
                 record["key"])


@app.get("/health")
def health() -> dict[str, Any]:
    ready = bool(os.environ.get("FIRE_SIGNING_KEY"))
    return {"ok": True, "signing_key": ready,
            "billing": bool(STRIPE_SECRET),
            "webhooks": bool(STRIPE_WEBHOOK_SECRET)}
