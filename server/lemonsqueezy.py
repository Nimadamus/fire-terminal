"""Lemon Squeezy as an alternative seller.

Why this exists alongside Stripe: Lemon Squeezy is the merchant of record. It
is the party selling to the customer, so it owns the card, the sales tax and
the invoice, and it pays out to us. That removes the two things standing
between FIRE and a first customer, a dedicated Stripe account and a business
entity, in exchange for a few percent.

The licence side is identical either way. Both providers do one job here: tell
us a subscription started, changed or ended. Everything downstream, the key,
the signed token, the seat limit, is provider agnostic and untouched.

Webhooks are signed with HMAC-SHA256 over the raw body, hex encoded, in the
`X-Signature` header. The event name is at `meta.event_name`.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any, Optional

import licences
import store

log = logging.getLogger("fire.licence.ls")

SIGNING_SECRET = os.environ.get("LEMONSQUEEZY_SIGNING_SECRET", "")

# Statuses Lemon Squeezy reports that still mean "this person has paid".
# `past_due` is deliberately included: their dunning is still retrying the
# card, and cutting somebody off over a payment that will succeed on the second
# attempt is the worst thing this service can do.
LIVE_STATUSES = {"active", "on_trial", "past_due"}


def verify(raw_body: bytes, signature: str) -> bool:
    """Constant time check of the webhook signature."""
    if not SIGNING_SECRET or not signature:
        return False
    expected = hmac.new(SIGNING_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def _attr(payload: dict, key: str, default=None):
    return ((payload.get("data") or {}).get("attributes") or {}).get(key, default)


def _subscription_id(payload: dict) -> str:
    return str((payload.get("data") or {}).get("id") or "")


def _plan_name(payload: dict) -> str:
    """Monthly or annual, from whatever the variant is called."""
    variant = str(_attr(payload, "variant_name") or "")
    lowered = variant.lower()
    if "annual" in lowered or "year" in lowered:
        return "FIRE Annual"
    if "month" in lowered:
        return "FIRE Monthly"
    return "FIRE"


def _expires(payload: dict) -> Optional[float]:
    """When access should end.

    `ends_at` is set once a subscription is cancelled and is the date access
    actually stops; `renews_at` is the next billing date while it is running.
    Taking renews_at on a cancelled subscription would extend access past the
    point the customer stopped paying.
    """
    from datetime import datetime

    stamp = _attr(payload, "ends_at") or _attr(payload, "renews_at")
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def handle(event: str, payload: dict, event_id: str = "") -> dict[str, Any]:
    """One webhook. Idempotent, and never raises at the caller."""
    if event_id and store.seen_event(event_id, event):
        return {"ok": True, "duplicate": True}

    subscription_id = _subscription_id(payload)
    email = str(_attr(payload, "user_email") or "")

    if event in ("subscription_created", "order_created"):
        return _issue(subscription_id, email, payload)

    if event in ("subscription_updated", "subscription_resumed",
                 "subscription_unpaused", "subscription_payment_success"):
        return _sync(subscription_id, payload)

    if event in ("subscription_cancelled", "subscription_expired",
                 "subscription_paused"):
        return _sync(subscription_id, payload, force_status="expired"
                     if event == "subscription_expired" else None)

    if event == "subscription_payment_failed":
        # Their dunning is still running. Do nothing and let it retry.
        log.info("payment failed for %s, leaving active during retries",
                 subscription_id)
        return {"ok": True, "noted": True}

    return {"ok": True, "ignored": event}


def _issue(subscription_id: str, email: str, payload: dict) -> dict[str, Any]:
    if subscription_id and store.licence_by_subscription(subscription_id):
        return {"ok": True, "duplicate": True}

    key = licences.new_key()
    store.create_licence(
        key, email=email, plan=_plan_name(payload), expires=_expires(payload),
        stripe_customer=str(_attr(payload, "customer_id") or ""),
        stripe_sub=subscription_id,
        # The success page looks a purchase up by order id, the way it does
        # with a Stripe checkout session.
        checkout_session=str(_attr(payload, "order_id") or ""))
    log.info("issued licence for lemonsqueezy subscription %s", subscription_id)
    return {"ok": True, "issued": True}


def _sync(subscription_id: str, payload: dict,
          force_status: Optional[str] = None) -> dict[str, Any]:
    record = store.licence_by_subscription(subscription_id) if subscription_id else None
    if record is None:
        # A subscription we have never seen: treat the first event we do see as
        # the purchase, rather than dropping a paying customer on the floor.
        return _issue(subscription_id, str(_attr(payload, "user_email") or ""),
                      payload)

    state = str(_attr(payload, "status") or "")
    status = force_status or ("active" if state in LIVE_STATUSES else "expired")
    store.set_status(str(record["key"]), status, _expires(payload))

    plan = _plan_name(payload)
    if plan != "FIRE" and plan != record.get("plan"):
        store.set_plan(str(record["key"]), plan)
    return {"ok": True, "status": status}


def licence_for_order(order_id: str) -> Optional[dict]:
    return store.licence_by_session(order_id) if order_id else None
