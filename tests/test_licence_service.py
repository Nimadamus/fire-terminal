"""The licence service, end to end against a real SQLite database.

This is the part of the product that decides whether somebody has paid, so the
tests are about the ways it could wrongly say yes, and the ways it could
wrongly say no. Both are expensive: the first gives the product away, the
second locks a paying customer out of a live position.
"""
from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient           # noqa: E402

from cryptography.hazmat.primitives import serialization                # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (          # noqa: E402
    Ed25519PrivateKey,
)

SERVER = Path(__file__).resolve().parents[1] / "server"


@pytest.fixture(scope="module")
def service(tmp_path_factory):
    """A running service with its own database and its own signing key."""
    tmp = tmp_path_factory.mktemp("licence")
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode("ascii")
    public = base64.urlsafe_b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)).decode("ascii").rstrip("=")

    os.environ["FIRE_SIGNING_KEY"] = pem
    os.environ["FIRE_DB"] = str(tmp / "licences.db")
    os.environ.pop("DATABASE_URL", None)

    sys.path.insert(0, str(SERVER))
    for name in ("app", "store", "licences"):
        sys.modules.pop(name, None)
    import app as service_app                       # noqa: E402
    import licences as licence_mod                  # noqa: E402
    import store as store_mod                       # noqa: E402

    store_mod.init()
    client = TestClient(service_app.app)
    yield client, store_mod, licence_mod, public.encode("ascii")
    client.close()
    sys.path.remove(str(SERVER))


def _payload(token: str, public: bytes, install: str = ""):
    from fire.entitlement.token import verify
    return verify(token, public, install)


# -- key format ------------------------------------------------------------
def test_keys_avoid_characters_a_human_would_misread(service):
    _, _, licence_mod, _ = service
    for _ in range(50):
        key = licence_mod.new_key()
        body = key.replace("FIRE-", "").replace("-", "")
        assert not set(body) & set("O0I1L"), key
        assert len(body) == 20


def test_a_key_is_accepted_however_a_human_types_it(service):
    _, _, licence_mod, _ = service
    key = licence_mod.new_key()
    for typed in (key.lower(), key.replace("-", " "), key.replace("FIRE-", ""),
                  f"  {key}  "):
        assert licence_mod.normalise(typed) == key, typed


def test_rubbish_is_not_normalised_into_something_valid(service):
    _, _, licence_mod, _ = service
    for junk in ("", "hello", "FIRE-1234", "x" * 40):
        assert licence_mod.normalise(junk) == ""


# -- activation ------------------------------------------------------------
def test_an_unknown_key_is_refused(service):
    client, _, _, _ = service
    r = client.post("/activate", json={"key": "FIRE-ABCDE-ABCDE-ABCDE-ABCDE",
                                       "install": "i1"})
    assert r.status_code == 404


def test_a_paid_key_activates_and_the_token_verifies(service):
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "buyer@example.com", "FIRE Monthly",
                             time.time() + 30 * 86400, "cus_1", "sub_1", "cs_1")

    r = client.post("/activate", json={"key": key, "install": "install-a"})
    assert r.status_code == 200
    payload = _payload(r.json()["token"], public, "install-a")
    assert payload.status == "active"
    assert payload.plan == "FIRE Monthly"
    assert payload.key_tail == key[-4:]
    # Nothing about the person may be inside a token that lands on their disk.
    assert "buyer@example.com" not in r.json()["token"]


def test_a_token_minted_for_one_install_does_not_unlock_another(service):
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() + 86400)
    token = client.post("/activate",
                        json={"key": key, "install": "mine"}).json()["token"]

    from fire.entitlement.token import TokenInvalid
    with pytest.raises(TokenInvalid):
        _payload(token, public, "theirs")


def test_the_seat_limit_holds_and_says_something_useful(service):
    client, store_mod, licence_mod, _ = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() + 86400,
                             seats=2)
    assert client.post("/activate", json={"key": key, "install": "s1"}).status_code == 200
    assert client.post("/activate", json={"key": key, "install": "s2"}).status_code == 200

    third = client.post("/activate", json={"key": key, "install": "s3"})
    assert third.status_code == 409
    assert "support" in third.json()["detail"].lower()

    # An already bound machine must keep working, not be counted again.
    assert client.post("/activate", json={"key": key, "install": "s1"}).status_code == 200


def test_an_expired_licence_still_activates_but_says_expired(service):
    """Refusing outright would leave the customer with nothing to act on."""
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() - 86400)
    store_mod.set_status(key, "expired")

    r = client.post("/activate", json={"key": key, "install": "gone"})
    assert r.status_code == 200
    assert _payload(r.json()["token"], public, "gone").status == "expired"


# -- periodic re-check -----------------------------------------------------
def test_an_unknown_install_is_given_a_trial_not_a_refusal(service):
    client, _, _, public = service
    r = client.post("/entitlement", json={"install": "brand-new"})
    assert r.status_code == 200
    payload = _payload(r.json()["token"], public, "brand-new")
    assert payload.status == "trial"
    assert payload.expires and payload.expires > time.time()


def test_a_cancelled_subscription_stops_the_next_recheck(service):
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() + 86400,
                             stripe_sub="sub_cancel")
    client.post("/activate", json={"key": key, "install": "c1"})

    fresh = client.post("/entitlement", json={"install": "c1"})
    assert _payload(fresh.json()["token"], public, "c1").status == "active"

    store_mod.set_status(key, "expired", time.time())
    after = client.post("/entitlement", json={"install": "c1"})
    assert _payload(after.json()["token"], public, "c1").status == "expired"


def test_the_recheck_remembers_the_key_so_the_client_need_not_send_it(service):
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Annual", time.time() + 86400)
    client.post("/activate", json={"key": key, "install": "remembered"})

    r = client.post("/entitlement", json={"install": "remembered"})
    assert _payload(r.json()["token"], public, "remembered").plan == "FIRE Annual"


# -- webhook safety --------------------------------------------------------
def test_a_repeated_stripe_event_does_not_issue_a_second_licence(service):
    _, store_mod, _, _ = service
    assert store_mod.seen_event("evt_dupe", "checkout.session.completed") is False
    assert store_mod.seen_event("evt_dupe", "checkout.session.completed") is True


def test_an_unsigned_webhook_is_refused(service):
    client, _, _, _ = service
    r = client.post("/stripe/webhook", content=b"{}",
                    headers={"stripe-signature": "nonsense"})
    # 503 when no webhook secret is configured, 400 when the check fails.
    assert r.status_code in (400, 503)


def test_the_success_page_waits_rather_than_saying_no(service):
    """The webhook can land after the redirect. 202 means keep polling."""
    client, _, _, _ = service
    r = client.get("/licence", params={"session_id": "cs_never"})
    assert r.status_code == 202


def test_the_success_page_returns_the_key_once_the_webhook_lands(service):
    client, store_mod, licence_mod, _ = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "b@example.com", "FIRE Monthly",
                             time.time() + 86400, checkout_session="cs_ok")
    r = client.get("/licence", params={"session_id": "cs_ok"})
    assert r.status_code == 200 and r.json()["key"] == key


def test_health_reports_what_is_actually_configured(service):
    client, _, _, _ = service
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["signing_key"] is True
    assert body["billing"] is False      # no Stripe key in the test environment
