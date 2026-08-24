"""The Lemon Squeezy seller path.

Same two failures matter as with Stripe: wrongly saying somebody paid, and
wrongly saying they stopped. The second is the expensive one, because it takes
access away from a customer who is still paying.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient           # noqa: E402

SERVER = Path(__file__).resolve().parents[1] / "server"
SECRET = "ls_test_signing_secret"


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    tmp = tmp_path_factory.mktemp("ls")
    private = Ed25519PrivateKey.generate()
    os.environ["FIRE_SIGNING_KEY"] = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    os.environ["FIRE_DB"] = str(tmp / "ls.db")
    os.environ["LEMONSQUEEZY_SIGNING_SECRET"] = SECRET
    os.environ.pop("DATABASE_URL", None)
    public = base64.urlsafe_b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)).decode().rstrip("=").encode()

    sys.path.insert(0, str(SERVER))
    for name in ("app", "store", "licences", "lemonsqueezy"):
        sys.modules.pop(name, None)
    import app as service_app
    import store as store_mod

    store_mod.init()
    client = TestClient(service_app.app)
    yield client, store_mod, public
    client.close()
    sys.path.remove(str(SERVER))


def _post(client, event: str, attributes: dict, sub_id: str = "sub_1",
          event_id: str = "", secret: str = SECRET):
    payload = {"meta": {"event_name": event, "webhook_id": event_id or event + sub_id},
               "data": {"id": sub_id, "attributes": attributes}}
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/ls/webhook", content=body,
                       headers={"X-Signature": signature})


def _payload(token, public, install=""):
    from fire.entitlement.token import verify
    return verify(token, public, install)


# -- signature -------------------------------------------------------------
def test_an_unsigned_webhook_is_refused(service):
    client, _, _ = service
    r = client.post("/ls/webhook", content=b"{}",
                    headers={"X-Signature": "nonsense"})
    assert r.status_code == 400


def test_a_webhook_signed_with_the_wrong_secret_is_refused(service):
    client, _, _ = service
    r = _post(client, "subscription_created", {"user_email": "a@b.com"},
              secret="not-our-secret")
    assert r.status_code == 400


# -- purchase --------------------------------------------------------------
def test_a_new_subscription_issues_a_licence(service):
    client, store_mod, public = service
    renews = "2027-01-01T00:00:00.000000Z"
    r = _post(client, "subscription_created",
              {"user_email": "buyer@example.com", "status": "active",
               "variant_name": "FIRE Monthly", "renews_at": renews,
               "order_id": "ord_1"}, sub_id="sub_new")
    assert r.status_code == 200 and r.json().get("issued") is True

    record = store_mod.licence_by_subscription("sub_new")
    assert record and record["plan"] == "FIRE Monthly"
    assert record["status"] == "active"
    assert record["expires"] > time.time()

    activated = client.post("/activate",
                            json={"key": record["key"], "install": "ls-1"})
    assert activated.status_code == 200
    assert _payload(activated.json()["token"], public, "ls-1").status == "active"


def test_the_same_event_twice_issues_one_licence(service):
    client, store_mod, _ = service
    args = ("subscription_created",
            {"user_email": "dupe@example.com", "status": "active",
             "variant_name": "FIRE Annual"})
    first = _post(client, *args, sub_id="sub_dupe", event_id="evt_dupe")
    second = _post(client, *args, sub_id="sub_dupe", event_id="evt_dupe")
    assert first.json().get("issued") is True
    assert second.json().get("duplicate") is True


def test_the_annual_variant_is_recognised(service):
    client, store_mod, _ = service
    _post(client, "subscription_created",
          {"user_email": "y@example.com", "status": "active",
           "variant_name": "FIRE Annual Plan"}, sub_id="sub_year")
    assert store_mod.licence_by_subscription("sub_year")["plan"] == "FIRE Annual"


# -- staying alive ---------------------------------------------------------
def test_a_failed_payment_does_not_cut_anybody_off(service):
    """Their dunning is still retrying. Only give up when they do."""
    client, store_mod, _ = service
    _post(client, "subscription_created",
          {"user_email": "f@example.com", "status": "active",
           "variant_name": "FIRE Monthly"}, sub_id="sub_fail")
    _post(client, "subscription_payment_failed",
          {"status": "past_due"}, sub_id="sub_fail")
    assert store_mod.licence_by_subscription("sub_fail")["status"] == "active"


def test_past_due_still_counts_as_paid(service):
    client, store_mod, _ = service
    _post(client, "subscription_created",
          {"user_email": "p@example.com", "status": "active",
           "variant_name": "FIRE Monthly"}, sub_id="sub_pd")
    _post(client, "subscription_updated", {"status": "past_due"}, sub_id="sub_pd")
    assert store_mod.licence_by_subscription("sub_pd")["status"] == "active"


# -- ending ----------------------------------------------------------------
def test_cancellation_uses_the_end_date_not_the_renewal_date(service):
    """A cancelled subscription runs to ends_at. Taking renews_at would give
    away access past the point the customer stopped paying."""
    client, store_mod, _ = service
    _post(client, "subscription_created",
          {"user_email": "c@example.com", "status": "active",
           "variant_name": "FIRE Monthly",
           "renews_at": "2030-01-01T00:00:00.000000Z"}, sub_id="sub_cancel")
    _post(client, "subscription_cancelled",
          {"status": "cancelled", "ends_at": "2026-09-01T00:00:00.000000Z",
           "renews_at": "2030-01-01T00:00:00.000000Z"}, sub_id="sub_cancel")

    record = store_mod.licence_by_subscription("sub_cancel")
    assert record["status"] == "expired"
    from datetime import datetime, timezone
    expected = datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp()
    assert record["expires"] == pytest.approx(expected)


def test_expiry_stops_live_trading_for_the_client(service):
    client, store_mod, public = service
    _post(client, "subscription_created",
          {"user_email": "e@example.com", "status": "active",
           "variant_name": "FIRE Monthly"}, sub_id="sub_exp")
    key = store_mod.licence_by_subscription("sub_exp")["key"]
    client.post("/activate", json={"key": key, "install": "ls-exp"})

    _post(client, "subscription_expired", {"status": "expired"}, sub_id="sub_exp")
    after = client.post("/entitlement", json={"install": "ls-exp"})
    assert _payload(after.json()["token"], public, "ls-exp").status == "expired"


def test_an_event_for_an_unknown_subscription_still_produces_a_licence(service):
    """Never drop a paying customer because we missed the first event."""
    client, store_mod, _ = service
    _post(client, "subscription_updated",
          {"user_email": "late@example.com", "status": "active",
           "variant_name": "FIRE Monthly"}, sub_id="sub_late")
    assert store_mod.licence_by_subscription("sub_late") is not None


def test_an_unknown_event_is_ignored_quietly(service):
    client, _, _ = service
    r = _post(client, "license_key_created", {}, sub_id="sub_x")
    assert r.status_code == 200 and "ignored" in r.json()
