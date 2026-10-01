"""Licences must not disappear, and must not be issued twice.

Runs on SQLite by default and on Postgres when FIRE_TEST_DATABASE_URL is set.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient           # noqa: E402

SERVER = Path(__file__).resolve().parents[1] / "server"
SECRET = "ls_persistence_secret"


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    tmp = tmp_path_factory.mktemp("persist")
    os.environ["FIRE_SIGNING_KEY"] = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    os.environ["LEMONSQUEEZY_SIGNING_SECRET"] = SECRET
    from conftest import use_test_database
    use_test_database(str(tmp / "persist.db"))

    sys.path.insert(0, str(SERVER))
    for name in ("app", "store", "licences", "lemonsqueezy"):
        sys.modules.pop(name, None)
    import app as service_app
    import lemonsqueezy as ls_mod
    import store as store_mod

    store_mod.init()
    client = TestClient(service_app.app, raise_server_exceptions=False)
    yield client, store_mod, ls_mod
    client.close()
    sys.path.remove(str(SERVER))


def _signed(event: str, sub_id: str, attributes: dict, event_id: str):
    payload = {"meta": {"event_name": event, "webhook_id": event_id},
               "data": {"id": sub_id, "attributes": attributes}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return body, {"X-Signature": sig}


def _count(store_mod, sql, params=()):
    return int(store_mod.fetchone(sql, params)[0])


# -- configuration -----------------------------------------------------------
def test_a_deployed_service_without_postgres_refuses_to_start(service, monkeypatch):
    _, store_mod, _ = service
    monkeypatch.setattr(store_mod, "DATABASE_URL", "")
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(store_mod.ConfigurationError):
        store_mod.init()


def test_a_non_postgres_url_is_never_silently_replaced_by_sqlite(service, monkeypatch):
    _, store_mod, _ = service
    monkeypatch.setattr(store_mod, "DATABASE_URL", "sqlite:///tmp/x.db")
    with pytest.raises(store_mod.ConfigurationError):
        store_mod.init()


def test_the_backend_name_never_contains_the_url(service):
    _, store_mod, _ = service
    assert store_mod.backend() in ("postgres", "sqlite")


# -- failures ----------------------------------------------------------------
def test_an_unreachable_database_answers_503_so_the_sender_retries(service, monkeypatch):
    client, store_mod, _ = service

    def down():
        raise store_mod.DatabaseUnavailable("down")
    monkeypatch.setattr(store_mod, "connect", down)
    r = client.post("/waitlist", json={"email": "retry@example.com"})
    assert r.status_code == 503
    assert r.headers.get("retry-after") == "30"


def test_a_webhook_that_fails_halfway_is_processed_on_the_retry(service, monkeypatch):
    """The old code recorded the event before doing the work. A failure then
    meant the retry was answered "duplicate" and the customer got no key."""
    client, store_mod, ls_mod = service
    body, headers = _signed("subscription_created", "sub_halfway",
                            {"user_email": "half@example.com", "status": "active",
                             "order_id": 9001}, "evt_halfway")
    real = ls_mod._dispatch
    calls = {"n": 0}

    def flaky(event, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise store_mod.DatabaseUnavailable("dropped mid write")
        return real(event, payload)
    monkeypatch.setattr(ls_mod, "_dispatch", flaky)

    assert client.post("/ls/webhook", content=body, headers=headers).status_code == 503
    assert store_mod.licence_by_subscription("sub_halfway") is None
    r = client.post("/ls/webhook", content=body, headers=headers)
    assert r.status_code == 200 and r.json().get("issued")
    assert store_mod.licence_by_subscription("sub_halfway") is not None
    # And a third delivery is a duplicate, not a second licence.
    assert client.post("/ls/webhook", content=body, headers=headers).json()["duplicate"]


def test_simultaneous_deliveries_of_one_purchase_issue_one_licence(service):
    _, store_mod, ls_mod = service
    payload = {"data": {"id": "sub_race", "attributes": {
        "user_email": "race@example.com", "status": "active", "order_id": 9002}}}
    barrier = threading.Barrier(6)
    results = []

    def deliver():
        barrier.wait()
        results.append(ls_mod._issue("sub_race", "race@example.com", payload))
    threads = [threading.Thread(target=deliver) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert _count(store_mod, "SELECT COUNT(*) FROM licences WHERE stripe_sub = ?",
                  ("sub_race",)) == 1
    assert sum(1 for r in results if r.get("issued")) == 1


def test_waitlist_signup_twice_is_one_row(service):
    client, store_mod, _ = service
    assert client.post("/waitlist", json={"email": "twice@example.com"}).json()["new"]
    assert not client.post("/waitlist", json={"email": "Twice@example.com"}).json()["new"]
    assert _count(store_mod, "SELECT COUNT(*) FROM waitlist WHERE email = ?",
                  ("twice@example.com",)) == 1


def test_activating_the_same_machine_twice_uses_one_seat(service):
    client, store_mod, _ = service
    import licences
    key = licences.new_key()
    store_mod.create_licence(key, "seat@example.com", "FIRE", None, stripe_sub="sub_seat")
    for _ in range(3):
        assert client.post("/activate", json={"key": key, "install": "pc-1"}).status_code == 200
    assert store_mod.install_count(key) == 1


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN ISSUE, not fixed here: Lemon Squeezy sends order_created (data.id is "
    "the ORDER id) and subscription_created (data.id is the SUBSCRIPTION id) for "
    "one purchase, and both are subscribed. Each issues its own licence."))
def test_one_lemon_squeezy_purchase_issues_one_licence(service):
    client, store_mod, _ = service
    order = {"user_email": "one@example.com", "status": "paid",
             "first_order_item": {"product_name": "FIRE Monthly"}}
    sub = {"user_email": "one@example.com", "status": "active", "order_id": 777,
           "product_name": "FIRE Monthly"}
    client.post("/ls/webhook", *[], **dict(zip(("content", "headers"),
                _signed("order_created", "777", order, "evt_o777"))))
    client.post("/ls/webhook", *[], **dict(zip(("content", "headers"),
                _signed("subscription_created", "sub_777", sub, "evt_s777"))))
    assert _count(store_mod, "SELECT COUNT(*) FROM licences WHERE email = ?",
                  ("one@example.com",)) == 1
