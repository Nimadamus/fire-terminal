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
import time
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


def _data(payload: dict) -> dict:
    return payload.get("data") or {}


def _attr(payload: dict, key: str, default=None):
    return (_data(payload).get("attributes") or {}).get(key, default)


def _id(value: Any) -> str:
    """Lemon Squeezy ids arrive as numbers in some places and strings in others."""
    return "" if value in (None, "") else str(value)


def _kind(event: str, payload: dict) -> str:
    """What the payload's data object is: an order, a subscription or an invoice.

    Read from data.type, which Lemon Squeezy always sends. The event name is the
    fallback for hand written payloads that leave the type out.
    """
    declared = str(_data(payload).get("type") or "")
    if declared in ("orders", "subscriptions", "subscription-invoices"):
        return declared
    if event.startswith("order_"):
        return "orders"
    if event.startswith("subscription_payment_"):
        return "subscription-invoices"
    return "subscriptions"


def _ids(event: str, payload: dict) -> tuple[str, str]:
    """(order id, subscription id) for whatever this payload describes.

    These are the stable ids every event about one purchase shares:

      * an order: data.id IS the order id; it carries no subscription id
      * a subscription: data.id is the subscription, attributes.order_id the
        order that created it
      * a subscription invoice (renewal payments): attributes.subscription_id

    The order id is the purchase. One order, one licence, whichever of its
    events arrives first.
    """
    kind = _kind(event, payload)
    if kind == "orders":
        return _id(_data(payload).get("id")), ""
    if kind == "subscription-invoices":
        return "", _id(_attr(payload, "subscription_id"))
    return _id(_attr(payload, "order_id")), _id(_data(payload).get("id"))


def _plan_name(payload: dict) -> str:
    """Monthly or annual.

    Read from the product name as well as the variant. A single price product
    gets a variant called "Default", so the variant name alone tells you
    nothing and every plan would come through as a bare "FIRE". An order keeps
    them on its first item.
    """
    item = _attr(payload, "first_order_item") or {}
    lowered = " ".join(str(_attr(payload, key) or item.get(key) or "")
                       for key in ("variant_name", "product_name")).lower()
    if "annual" in lowered or "year" in lowered:
        return "FIRE Annual"
    if "month" in lowered:
        return "FIRE Monthly"
    return "FIRE"


def _stamp(key: str, payload: dict) -> Optional[float]:
    from datetime import datetime

    stamp = _attr(payload, key)
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _expires(payload: dict) -> Optional[float]:
    """When access should end.

    `ends_at` is set once a subscription is cancelled and is the date access
    actually stops; `renews_at` is the next billing date while it is running.
    Taking renews_at on a cancelled subscription would extend access past the
    point the customer stopped paying.
    """
    return _stamp("ends_at", payload) or _stamp("renews_at", payload)


def _status(payload: dict, force_status: Optional[str]) -> str:
    if force_status:
        return force_status
    state = str(_attr(payload, "status") or "")
    if state in LIVE_STATUSES:
        return "active"
    if state == "cancelled":
        # Cancelling stops the renewal, not the period they already paid for.
        # Access runs to ends_at; subscription_expired closes it then.
        ends = _stamp("ends_at", payload)
        return "active" if ends and ends > time.time() else "expired"
    return "expired"


# A subscription's own order is issued a licence that lapses after this long
# unless its subscription event confirms it. Normally that is seconds later;
# the window only matters if that event is lost, and then access stops instead
# of running forever on an order that was never meant to be perpetual.
PROVISIONAL_S = 3 * 86400

# Orders in these states never earn a licence.
DEAD_ORDER_STATUSES = {"failed", "refunded", "fraudulent"}


def handle(event: str, payload: dict, event_id: str = "") -> dict[str, Any]:
    """One webhook. Idempotent. Raises only if the database is unreachable,
    which the service answers with a 503 so Lemon Squeezy retries."""
    if event_id and store.seen_event(event_id, event):
        return {"ok": True, "duplicate": True}
    result = _dispatch(event, payload)
    # Recorded only after the work is done, so a failure part way is retried.
    if event_id:
        store.mark_event(event_id, event)
    return result


def _dispatch(event: str, payload: dict) -> dict[str, Any]:
    order_id, subscription_id = _ids(event, payload)

    if event == "order_created":
        return _on_order(order_id, payload)

    if event == "subscription_payment_failed":
        # Their dunning is still running. Do nothing and let it retry.
        log.info("payment failed for %s, leaving active during retries",
                 subscription_id)
        return {"ok": True, "noted": True}

    if event == "subscription_payment_success":
        # A renewal was paid. The key never changes; the new period end comes
        # with the subscription_updated that Lemon Squeezy sends alongside.
        record = store.licence_by_subscription(subscription_id) if subscription_id else None
        if record is None:
            return {"ok": True, "unknown_subscription": True}
        store.set_status(str(record["key"]), "active")
        return {"ok": True, "status": "active"}

    if event in ("subscription_created", "subscription_updated",
                 "subscription_resumed", "subscription_unpaused",
                 "subscription_cancelled", "subscription_paused"):
        return _on_subscription(order_id, subscription_id, payload)

    if event == "subscription_expired":
        return _on_subscription(order_id, subscription_id, payload,
                                force_status="expired")

    return {"ok": True, "ignored": event}


def _on_order(order_id: str, payload: dict) -> dict[str, Any]:
    """An order: a one time purchase, or the first payment of a subscription.

    Issues the licence unless this order already has one, whichever event made
    it. For a subscription's order the licence is provisional until the
    subscription event attaches itself and sets the real period end.
    """
    if not order_id:
        log.warning("lemonsqueezy order event without an order id")
        return {"ok": True, "ignored": "no order id"}
    if str(_attr(payload, "status") or "") in DEAD_ORDER_STATUSES:
        return {"ok": True, "ignored": "order not paid"}
    if store.licence_by_session(order_id):
        return {"ok": True, "duplicate": True}

    plan = _plan_name(payload)
    expires = time.time() + PROVISIONAL_S if plan != "FIRE" else None
    return _public(_create(order_id, "", plan, expires, payload))


def _on_subscription(order_id: str, subscription_id: str, payload: dict,
                     force_status: Optional[str] = None) -> dict[str, Any]:
    """Any subscription event, in any order relative to the others.

    Finds the purchase's licence by subscription id, then by order id, and only
    issues a new one if neither exists. Rather than drop a paying customer
    because an earlier event was missed, an unknown subscription is treated as
    the purchase.
    """
    if not subscription_id:
        log.warning("lemonsqueezy subscription event without an id")
        return {"ok": True, "ignored": "no subscription id"}

    # Twice at most: the second pass runs only when a simultaneous delivery of
    # the same purchase inserted first, and then the lookups find its row.
    for _ in range(2):
        record = store.licence_by_subscription(subscription_id)
        if record is None and order_id:
            record = store.licence_by_session(order_id)
            if record is not None and not store.attach_subscription(
                    str(record["key"]), subscription_id):
                # This order's licence already belongs to a different
                # subscription. Never move it, never issue a second key.
                log.error("order %s is linked to another subscription; "
                          "subscription %s left unlinked", order_id, subscription_id)
                return {"ok": False, "conflict": True}
        if record is not None:
            return _sync(record, payload, force_status)

        result = _create(order_id, subscription_id, _plan_name(payload),
                         _expires(payload), payload)
        if result.get("issued"):
            status = _status(payload, force_status)
            if status != "active":
                store.set_status(result["key"], status, _expires(payload))
            return _public(result)
    raise RuntimeError("licence for subscription %s could not be created or found"
                       % subscription_id)


def _create(order_id: str, subscription_id: str, plan: str,
            expires: Optional[float], payload: dict) -> dict[str, Any]:
    key = licences.new_key()
    created = store.create_licence(
        key, email=str(_attr(payload, "user_email") or ""), plan=plan,
        expires=expires, stripe_customer=_id(_attr(payload, "customer_id")),
        stripe_sub=subscription_id,
        # The success page looks a purchase up by order id, the way it does
        # with a Stripe checkout session.
        checkout_session=order_id)
    if not created:
        # Another delivery of this purchase won. The unique indexes decided.
        return {"ok": True, "duplicate": True}
    log.info("issued licence for lemonsqueezy order %s subscription %s",
             order_id or "-", subscription_id or "-")
    return {"ok": True, "issued": True, "key": key}


def _public(result: dict) -> dict[str, Any]:
    """Never echo a licence key back to the webhook sender."""
    return {k: v for k, v in result.items() if k != "key"}


def _sync(record: dict, payload: dict,
          force_status: Optional[str] = None) -> dict[str, Any]:
    status = _status(payload, force_status)
    store.set_status(str(record["key"]), status, _expires(payload))

    plan = _plan_name(payload)
    if plan != "FIRE" and plan != record.get("plan"):
        store.set_plan(str(record["key"]), plan)
    return {"ok": True, "status": status}


def licence_for_order(order_id: str) -> Optional[dict]:
    return store.licence_by_session(order_id) if order_id else None
