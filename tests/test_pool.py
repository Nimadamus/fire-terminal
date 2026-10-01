"""Postgres connection reuse. Skipped unless FIRE_TEST_DATABASE_URL is set."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

from conftest import TEST_PG

pytestmark = pytest.mark.skipif(not TEST_PG, reason="Postgres only")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient           # noqa: E402

SERVER = Path(__file__).resolve().parents[1] / "server"
SECRET = "ls_pool_secret"
_n = [int(time.time() * 1000) % 10**9]


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    os.environ["FIRE_SIGNING_KEY"] = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    os.environ["LEMONSQUEEZY_SIGNING_SECRET"] = SECRET
    from conftest import use_test_database
    use_test_database(str(tmp_path_factory.mktemp("pool") / "unused.db"))
    sys.path.insert(0, str(SERVER))
    for name in ("app", "store", "licences", "lemonsqueezy"):
        sys.modules.pop(name, None)
    import app as service_app
    import store as store_mod
    store_mod.init()
    client = TestClient(service_app.app)
    yield client, store_mod
    client.close()
    store_mod.close()
    sys.path.remove(str(SERVER))


def purchase(client):
    _n[0] += 10
    order, sub = _n[0], _n[0] + 1
    payload = {"meta": {"event_name": "subscription_created", "webhook_id": f"pool_{sub}"},
               "data": {"type": "subscriptions", "id": str(sub), "attributes": {
                   "order_id": order, "user_email": "pool@example.com",
                   "status": "active", "product_name": "FIRE Monthly",
                   "renews_at": "2030-01-01T00:00:00.000000Z"}}}
    body = json.dumps(payload).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    r = client.post("/ls/webhook", content=body, headers={"X-Signature": sig})
    assert r.status_code == 200 and r.json().get("issued"), r.text
    return order, sub


def test_a_warm_webhook_opens_no_new_connection(service):
    client, store = service
    purchase(client)                                 # warm the pool
    before = store.connections_opened()
    for _ in range(5):
        purchase(client)
    assert store.connections_opened() == before


def test_the_pool_never_exceeds_its_size_under_a_burst(service):
    client, store = service
    import psycopg
    peak = [0]
    stop = threading.Event()

    def watch():
        with psycopg.connect(TEST_PG) as conn:
            while not stop.is_set():
                n = conn.execute("SELECT count(*) FROM pg_stat_activity"
                                 " WHERE application_name = 'fire-licence'").fetchone()[0]
                peak[0] = max(peak[0], n)
                time.sleep(0.02)
    w = threading.Thread(target=watch)
    w.start()
    threads = [threading.Thread(target=purchase, args=(client,)) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    stop.set()
    w.join()
    assert 1 <= peak[0] <= store.POOL_MAX


def test_a_connection_killed_by_the_server_is_replaced_not_reused(service):
    """Neon suspending its compute closes every connection we hold."""
    client, store = service
    import psycopg
    purchase(client)
    with psycopg.connect(TEST_PG, autocommit=True) as conn:
        killed = conn.execute("SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity"
                              " WHERE application_name = 'fire-licence'").fetchone()[0]
    assert killed >= 1
    order, _ = purchase(client)                       # must still work
    r = client.get("/licence", params={"session_id": str(order)})
    assert r.status_code == 200 and r.json()["key"]
