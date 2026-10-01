"""One Lemon Squeezy purchase, one licence. Whatever order the events come in.

A subscription purchase sends order_created (data is the order, data.id is the
ORDER id) and subscription_created (data is the subscription, data.id is the
SUBSCRIPTION id, attributes.order_id links back). Both are subscribed, and
before this was fixed each issued its own key.

Payloads below follow Lemon Squeezy's real shapes, including data.type.
Runs on SQLite by default and on Postgres when FIRE_TEST_DATABASE_URL is set.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient           # noqa: E402

SERVER = Path(__file__).resolve().parents[1] / "server"
SECRET = "ls_purchase_secret"
_ids = itertools.count(500000)
_events = itertools.count(1)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


def _load(tmp_path_factory=None):
    sys.path.insert(0, str(SERVER))
    for name in ("app", "store", "licences", "lemonsqueezy"):
        sys.modules.pop(name, None)
    import app as service_app
    import lemonsqueezy as ls_mod
    import store as store_mod
    store_mod.init()
    return TestClient(service_app.app), store_mod, ls_mod


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    tmp = tmp_path_factory.mktemp("purchases")
    private = Ed25519PrivateKey.generate()
    os.environ["FIRE_SIGNING_KEY"] = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    os.environ["LEMONSQUEEZY_SIGNING_SECRET"] = SECRET
    from conftest import use_test_database
    use_test_database(str(tmp / "purchases.db"))
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode().rstrip("=").encode()

    client, store_mod, ls_mod = _load()
    state = {"client": client, "store": store_mod, "ls": ls_mod, "public": public}
    yield state
    state["client"].close()
    sys.path.remove(str(SERVER))


# -- Lemon Squeezy shaped payloads ------------------------------------------
class Purchase:
    """The ids one real checkout produces."""

    def __init__(self, product: str = "FIRE Monthly", email: str = "buyer@example.com",
                 customer: int = 0):
        self.order = next(_ids)
        self.sub = next(_ids)
        self.customer = customer or next(_ids)
        self.product = product
        self.email = email
        self.renews = time.time() + 30 * 86400

    def order_created(self, status: str = "paid") -> tuple[str, dict]:
        return "order_created", {"data": {"type": "orders", "id": str(self.order),
            "attributes": {"store_id": 1, "customer_id": self.customer,
                           "identifier": f"uuid-{self.order}",
                           "order_number": self.order, "user_email": self.email,
                           "status": status,
                           "first_order_item": {"order_id": self.order,
                                                "product_name": self.product,
                                                "variant_name": "Default"}}}}

    def subscription(self, event: str = "subscription_created", status: str = "active",
                     renews: float | None = None, ends: float | None = None) -> tuple[str, dict]:
        return event, {"data": {"type": "subscriptions", "id": str(self.sub),
            "attributes": {"store_id": 1, "customer_id": self.customer,
                           "order_id": self.order, "order_item_id": self.order + 1,
                           "product_name": self.product, "variant_name": "Default",
                           "user_email": self.email, "status": status,
                           "renews_at": _iso(renews or self.renews),
                           "ends_at": _iso(ends) if ends else None}}}

    def invoice(self, event: str = "subscription_payment_success") -> tuple[str, dict]:
        return event, {"data": {"type": "subscription-invoices", "id": str(next(_ids)),
            "attributes": {"store_id": 1, "subscription_id": self.sub,
                           "customer_id": self.customer, "user_email": self.email,
                           "billing_reason": "renewal", "status": "paid"}}}


def send(service, event_and_payload, event_id: str = ""):
    event, payload = event_and_payload
    payload = dict(payload)
    payload["meta"] = {"event_name": event,
                       "webhook_id": event_id or f"evt_{next(_events)}"}
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    r = service["client"].post("/ls/webhook", content=body, headers={"X-Signature": sig})
    assert r.status_code == 200, r.text
    assert "key" not in r.json()                  # never echo a key to the sender
    return r.json()


def licences_for(service, purchase: Purchase) -> list[dict]:
    s = service["store"]
    rows = []
    with s.connect() as conn:
        cur = conn.cursor()
        cur.execute(s.q("SELECT key, stripe_sub, checkout_session, status, expires,"
                        " plan FROM licences WHERE checkout_session = ?"
                        " OR stripe_sub = ?"), (str(purchase.order), str(purchase.sub)))
        for r in cur.fetchall():
            rows.append(dict(zip(("key", "sub", "order", "status", "expires", "plan"), r)))
    return rows


def only_licence(service, purchase: Purchase) -> dict:
    rows = licences_for(service, purchase)
    assert len(rows) == 1, rows
    return rows[0]


# -- subscription purchase -------------------------------------------------------
def test_order_then_subscription_is_one_licence(service):
    p = Purchase()
    assert send(service, p.order_created()).get("issued")
    assert send(service, p.subscription()).get("status") == "active"
    lic = only_licence(service, p)
    assert lic["sub"] == str(p.sub) and lic["order"] == str(p.order)
    assert lic["expires"] == pytest.approx(p.renews, abs=1)   # provisional replaced
    assert lic["plan"] == "FIRE Monthly"


def test_subscription_then_order_is_one_licence(service):
    p = Purchase(product="FIRE Annual")
    assert send(service, p.subscription()).get("issued")
    assert send(service, p.order_created()).get("duplicate")
    lic = only_licence(service, p)
    assert lic["sub"] == str(p.sub) and lic["plan"] == "FIRE Annual"


def test_the_success_page_finds_the_key_by_order_id_either_way(service):
    for first_order in (True, False):
        p = Purchase()
        events = [p.order_created(), p.subscription()]
        for e in (events if first_order else events[::-1]):
            send(service, e)
        r = service["client"].get("/licence", params={"session_id": str(p.order)})
        assert r.status_code == 200
        assert r.json()["key"] == only_licence(service, p)["key"]


def test_duplicate_and_retried_deliveries_never_add_a_licence(service):
    p = Purchase()
    order, sub = p.order_created(), p.subscription()
    send(service, order, "evt_dup_o")
    send(service, order, "evt_dup_o")            # same delivery id again
    send(service, order)                          # a retry with a fresh id
    send(service, sub, "evt_dup_s")
    send(service, sub, "evt_dup_s")
    send(service, sub)
    send(service, order)
    only_licence(service, p)


@pytest.mark.parametrize("sequence", [
    ("subscription_updated", "order_created", "subscription_created"),
    ("subscription_updated", "subscription_created", "order_created"),
    ("subscription_cancelled_future", "order_created", "subscription_created"),
    ("order_created", "subscription_updated", "subscription_created"),
])
def test_events_out_of_order_still_one_licence(service, sequence):
    p = Purchase()
    for name in sequence:
        if name == "order_created":
            send(service, p.order_created())
        elif name == "subscription_cancelled_future":
            send(service, p.subscription("subscription_cancelled", "cancelled",
                                         ends=time.time() + 5 * 86400))
        else:
            send(service, p.subscription(name))
    lic = only_licence(service, p)
    assert lic["sub"] == str(p.sub)


def test_a_restart_between_events_still_one_licence(service):
    p = Purchase()
    send(service, p.order_created())
    service["client"].close()
    service["client"], service["store"], service["ls"] = _load()   # new process state
    send(service, p.subscription())
    send(service, p.order_created())
    only_licence(service, p)


def test_simultaneous_order_and_subscription_events_one_licence(service):
    for _ in range(10):
        p = Purchase()
        deliveries = [p.order_created(), p.subscription(), p.order_created(),
                      p.subscription("subscription_updated")]
        barrier = threading.Barrier(len(deliveries))

        def go(e):
            barrier.wait()
            send(service, e)
        threads = [threading.Thread(target=go, args=(e,)) for e in deliveries]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        lic = only_licence(service, p)
        assert lic["sub"] == str(p.sub)


# -- the database refuses a second licence on its own --------------------------
def test_the_database_rejects_a_second_licence_for_one_order(service):
    s = service["store"]
    import licences
    p = Purchase()
    assert s.create_licence(licences.new_key(), "", "FIRE", None,
                            checkout_session=str(p.order))
    assert not s.create_licence(licences.new_key(), "", "FIRE", None,
                                stripe_sub=str(p.sub), checkout_session=str(p.order))
    assert len(licences_for(service, p)) == 1


def test_the_database_rejects_a_second_licence_for_one_subscription(service):
    s = service["store"]
    import licences
    p = Purchase()
    assert s.create_licence(licences.new_key(), "", "FIRE", None, stripe_sub=str(p.sub))
    assert not s.create_licence(licences.new_key(), "", "FIRE", None, stripe_sub=str(p.sub))
    assert len(licences_for(service, p)) == 1


def test_a_raw_insert_bypassing_the_code_is_refused_by_the_index(service):
    """The rule lives in the database, not only in Python."""
    s = service["store"]
    p = Purchase()
    sql = ("INSERT INTO licences (key, email, plan, status, expires, seats,"
           " stripe_customer, stripe_sub, checkout_session, created)"
           " VALUES (?, '', 'FIRE', 'active', NULL, 3, '', ?, ?, 0)")
    s.execute(sql, ("RAW-1", "", str(p.order)))
    with pytest.raises(Exception):
        s.execute(sql, ("RAW-2", "", str(p.order)))
    s.execute(sql, ("RAW-3", str(p.sub), ""))
    with pytest.raises(Exception):
        s.execute(sql, ("RAW-4", str(p.sub), ""))


def test_one_order_never_moves_to_a_second_subscription(service):
    p = Purchase()
    send(service, p.subscription())
    other = Purchase()
    other.order = p.order                          # a different subscription claiming it
    r = send(service, other.subscription())
    assert r.get("conflict")
    assert only_licence(service, p)["sub"] == str(p.sub)
    assert licences_for(service, other) == [only_licence(service, p)]


# -- renewals and cancellation -------------------------------------------------
def _activate(service, key: str, install: str):
    r = service["client"].post("/activate", json={"key": key, "install": install})
    assert r.status_code == 200
    from fire.entitlement.token import verify
    return verify(r.json()["token"], service["public"], install)


def test_renewals_keep_the_original_key(service):
    p = Purchase()
    send(service, p.order_created())
    send(service, p.subscription())
    key = only_licence(service, p)["key"]
    _activate(service, key, "renew-pc")

    for month in (1, 2, 3):
        next_end = p.renews + month * 30 * 86400
        send(service, p.invoice())                                 # payment
        send(service, p.subscription("subscription_updated", renews=next_end))
        lic = only_licence(service, p)
        assert lic["key"] == key
        assert lic["status"] == "active"
        assert lic["expires"] == pytest.approx(next_end, abs=1)

    r = service["client"].post("/entitlement", json={"install": "renew-pc"})
    from fire.entitlement.token import verify
    assert verify(r.json()["token"], service["public"], "renew-pc").status == "active"


def test_a_payment_for_an_unknown_subscription_issues_nothing(service):
    p = Purchase()
    assert send(service, p.invoice()).get("unknown_subscription")
    assert licences_for(service, p) == []


def test_cancelling_keeps_access_until_the_paid_period_ends(service):
    p = Purchase()
    send(service, p.subscription())
    key = only_licence(service, p)["key"]
    ends = time.time() + 10 * 86400
    send(service, p.subscription("subscription_cancelled", "cancelled", ends=ends))
    lic = only_licence(service, p)
    assert lic["status"] == "active" and lic["expires"] == pytest.approx(ends, abs=1)

    send(service, p.subscription("subscription_expired", "expired", ends=time.time() - 1))
    lic = only_licence(service, p)
    assert lic["key"] == key and lic["status"] == "expired"
    _activate(service, key, "cancel-pc")
    r = service["client"].post("/entitlement", json={"install": "cancel-pc"})
    from fire.entitlement.token import verify
    assert verify(r.json()["token"], service["public"], "cancel-pc").status == "expired"


def test_a_subscription_order_alone_is_provisional_not_perpetual(service):
    p = Purchase(product="FIRE Monthly")
    send(service, p.order_created())
    lic = only_licence(service, p)
    assert lic["expires"] is not None
    assert lic["expires"] == pytest.approx(time.time() + 3 * 86400, abs=60)


# -- one time purchases --------------------------------------------------------------
def test_a_one_time_order_issues_a_licence_that_does_not_expire(service):
    p = Purchase(product="FIRE Lifetime")
    assert send(service, p.order_created()).get("issued")
    lic = only_licence(service, p)
    assert lic["expires"] is None and lic["sub"] == ""
    assert _activate(service, lic["key"], "lifetime-pc").status == "active"


def test_a_duplicated_one_time_order_is_still_one_licence(service):
    p = Purchase(product="FIRE Lifetime")
    send(service, p.order_created(), "evt_life")
    send(service, p.order_created(), "evt_life")
    send(service, p.order_created())
    send(service, p.order_created())
    only_licence(service, p)


@pytest.mark.parametrize("status", ["failed", "refunded"])
def test_an_unpaid_order_issues_nothing(service, status):
    p = Purchase(product="FIRE Lifetime")
    send(service, p.order_created(status))
    assert licences_for(service, p) == []


# -- separate purchases ----------------------------------------------------------
def test_two_real_purchases_by_one_customer_are_two_licences(service):
    first = Purchase(email="same@example.com", customer=424242)
    second = Purchase(email="same@example.com", customer=424242)
    for p in (first, second):
        send(service, p.order_created())
        send(service, p.subscription())
    a, b = only_licence(service, first), only_licence(service, second)
    assert a["key"] != b["key"]


def test_a_subscription_and_a_one_time_purchase_are_two_licences(service):
    sub = Purchase(product="FIRE Monthly", email="both@example.com")
    once = Purchase(product="FIRE Lifetime", email="both@example.com")
    send(service, sub.order_created())
    send(service, sub.subscription())
    send(service, once.order_created())
    assert only_licence(service, sub)["key"] != only_licence(service, once)["key"]
