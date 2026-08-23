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


WEBHOOK_SECRET = "whsec_unit_test_secret"


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
    # A webhook secret, so the signed webhook path is actually exercised. It
    # was not, and a 500 in that handler lived here undetected: every purchase
    # would have failed and no customer would have received a licence.
    os.environ["STRIPE_WEBHOOK_SECRET"] = WEBHOOK_SECRET
    os.environ["STRIPE_SECRET_KEY"] = ""
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


# -- pre launch ------------------------------------------------------------
def test_the_waitlist_takes_an_address_and_nothing_else(service):
    client, store_mod, _, _ = service
    before = store_mod.waitlist_size()
    r = client.post("/waitlist", json={"email": "Trader@Example.com",
                                       "note": "trading BTC 15m",
                                       "source": "landing"})
    assert r.status_code == 200 and r.json()["new"] is True
    assert store_mod.waitlist_size() == before + 1


def test_signing_up_twice_is_not_an_error(service):
    """A customer who forgets they already joined must not see a failure."""
    client, _, _, _ = service
    client.post("/waitlist", json={"email": "twice@example.com"})
    again = client.post("/waitlist", json={"email": "TWICE@example.com"})
    assert again.status_code == 200
    assert again.json() == {"ok": True, "new": False}


def test_a_bad_address_is_refused(service):
    client, _, _, _ = service
    for junk in ("", "nope", "a@b", "x" * 400 + "@example.com"):
        assert client.post("/waitlist", json={"email": junk}).status_code == 400


# -- device handling -------------------------------------------------------
def test_a_customer_can_see_their_own_computers(service):
    client, store_mod, licence_mod, _ = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "who@example.com", "FIRE Monthly",
                             time.time() + 86400, "cus_x", "sub_x")
    client.post("/activate", json={"key": key, "install": "aaaaaaaabbbbbbbb"})

    body = client.get("/licence/state", params={"key": key}).json()
    assert body["seats_used"] == 1 and body["seats"] == 3
    assert body["computers"][0]["id"] == "aaaaaaaa"
    assert body["computers"][0]["handle"] == "aaaaaaaabbbbbbbb"
    # A key found written down must not become a way to read the account.
    assert "who@example.com" not in str(body)
    assert "cus_x" not in str(body)


def test_replacing_a_laptop_does_not_need_a_support_ticket(service):
    client, store_mod, licence_mod, _ = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() + 86400,
                             seats=2)
    client.post("/activate", json={"key": key, "install": "old-machine-1111"})
    client.post("/activate", json={"key": key, "install": "old-machine-2222"})
    assert client.post("/activate", json={"key": key, "install": "new"}).status_code == 409

    # An ambiguous prefix must say so, not claim the computer does not exist.
    freed = client.post("/licence/release", json={"key": key, "install": "old-mach"})
    assert freed.status_code == 409, "an ambiguous prefix must not free a seat"
    assert "more than one" in freed.json()["detail"].lower()

    freed = client.post("/licence/release",
                        json={"key": key, "install": "old-machine-1111"})
    assert freed.status_code == 200 and freed.json()["seats_used"] == 1
    assert client.post("/activate", json={"key": key, "install": "new"}).status_code == 200


def test_releasing_a_computer_that_is_not_there_says_so(service):
    client, store_mod, licence_mod, _ = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() + 86400)
    assert client.post("/licence/release",
                       json={"key": key, "install": "never"}).status_code == 404


def test_an_unknown_key_reveals_nothing(service):
    client, _, _, _ = service
    assert client.get("/licence/state",
                      params={"key": "FIRE-ZZZZZ-ZZZZZ-ZZZZZ-ZZZZZ"}).status_code == 404


# -- the website, served by the same process -------------------------------
def test_the_site_is_served_from_the_same_origin(service):
    """One thing to deploy, one domain, no CORS, no second hosting account."""
    client, _, _, _ = service
    r = client.get("/")
    assert r.status_code == 200
    assert "FIRE" in r.text
    assert "text/html" in r.headers["content-type"]


def test_clean_urls_resolve(service):
    client, _, _, _ = service
    for path in ("/welcome", "/account", "/legal/risk", "/legal/terms"):
        assert client.get(path).status_code == 200, path


def test_static_assets_are_served(service):
    client, _, _, _ = service
    assert client.get("/style.css").status_code == 200
    assert client.get("/img/terminal.png").status_code == 200


def test_the_api_routes_win_over_the_site(service):
    """A file called health.html must never shadow the health endpoint."""
    client, _, _, _ = service
    body = client.get("/health").json()
    assert body["ok"] is True


def test_a_path_cannot_escape_the_site_directory(service):
    client, _, _, _ = service
    for attack in ("/../server/app.py", "/..%2f..%2fserver/licences.py",
                   "/../../CREDENTIALS.md"):
        r = client.get(attack)
        assert r.status_code == 404 or "STRIPE" not in r.text, attack


def test_the_support_page_and_404_are_served(service):
    client, _, _, _ = service
    assert client.get("/support").status_code == 200
    missing = client.get("/no-such-page")
    assert missing.status_code == 404
    assert "not here" in missing.text


# -- the purchase webhook, signed the way Stripe signs it ------------------
def _signed(payload: dict) -> tuple[bytes, dict]:
    import json as _json

    import stripe
    body = _json.dumps(payload, separators=(",", ":")).encode()
    ts = int(time.time())
    sig = stripe.WebhookSignature._compute_signature(
        f"{ts}.{body.decode()}", WEBHOOK_SECRET)
    return body, {"stripe-signature": f"t={ts},v1={sig}"}


def test_a_real_signed_purchase_issues_a_licence(service):
    """The whole reason this service exists. Signed exactly as Stripe signs."""
    pytest.importorskip("stripe")
    client, store_mod, _, public = service
    body, headers = _signed({
        "id": "evt_unit_purchase",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_unit_purchase", "customer": "cus_unit",
                            "subscription": "sub_unit",
                            "customer_details": {"email": "buyer@example.com"}}},
    })
    r = client.post("/stripe/webhook", content=body, headers=headers)
    assert r.status_code == 200, r.text

    issued = client.get("/licence", params={"session_id": "cs_unit_purchase"})
    assert issued.status_code == 200
    key = issued.json()["key"]
    assert key.startswith("FIRE-")

    activated = client.post("/activate", json={"key": key, "install": "unit-buy"})
    assert activated.status_code == 200
    assert _payload(activated.json()["token"], public, "unit-buy").status == "active"


def test_a_repeated_purchase_event_issues_only_one_licence(service):
    pytest.importorskip("stripe")
    client, store_mod, _, _ = service
    event = {
        "id": "evt_unit_dupe",
        "type": "checkout.session.completed",
        "data": {"object": {"id": "cs_unit_dupe", "customer": "cus_d",
                            "subscription": "sub_d",
                            "customer_details": {"email": "d@example.com"}}},
    }
    body, headers = _signed(event)
    assert client.post("/stripe/webhook", content=body, headers=headers).status_code == 200
    first = client.get("/licence", params={"session_id": "cs_unit_dupe"}).json()["key"]

    body, headers = _signed(event)
    second = client.post("/stripe/webhook", content=body, headers=headers)
    assert second.json().get("duplicate") is True
    assert client.get("/licence",
                      params={"session_id": "cs_unit_dupe"}).json()["key"] == first


def test_a_cancellation_webhook_expires_the_licence(service):
    pytest.importorskip("stripe")
    client, store_mod, _, public = service
    body, headers = _signed({
        "id": "evt_unit_cancel",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_unit", "status": "canceled"}},
    })
    assert client.post("/stripe/webhook", content=body, headers=headers).status_code == 200
    after = client.post("/entitlement", json={"install": "unit-buy"})
    assert _payload(after.json()["token"], public, "unit-buy").status == "expired"


def test_a_failed_payment_does_not_cut_anybody_off(service):
    """Stripe retries a failed card for days. Only give up when Stripe does."""
    pytest.importorskip("stripe")
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() + 86400,
                             stripe_sub="sub_failing")
    client.post("/activate", json={"key": key, "install": "unit-fail"})

    body, headers = _signed({
        "id": "evt_unit_failed_payment",
        "type": "invoice.payment_failed",
        "data": {"object": {"subscription": "sub_failing"}},
    })
    assert client.post("/stripe/webhook", content=body, headers=headers).status_code == 200
    after = client.post("/entitlement", json={"install": "unit-fail"})
    assert _payload(after.json()["token"], public, "unit-fail").status == "active"


def test_a_past_due_subscription_stays_active(service):
    pytest.importorskip("stripe")
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE Monthly", time.time() + 86400,
                             stripe_sub="sub_pastdue")
    client.post("/activate", json={"key": key, "install": "unit-pastdue"})

    body, headers = _signed({
        "id": "evt_unit_pastdue",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_pastdue", "status": "past_due",
                            "current_period_end": int(time.time()) + 86400}},
    })
    assert client.post("/stripe/webhook", content=body, headers=headers).status_code == 200
    after = client.post("/entitlement", json={"install": "unit-pastdue"})
    assert _payload(after.json()["token"], public, "unit-pastdue").status == "active"


# -- the shapes Stripe actually sends --------------------------------------
def test_the_renewal_date_is_read_from_the_subscription_item(service):
    """Stripe moved current_period_end onto the item.

    Reading only the old top level location returns None, and every licence is
    then created with no expiry at all. That is what happened on the first real
    purchase, and nothing in the suite noticed because the hand written payload
    put the field where the old API had it.
    """
    import sys
    sys.path.insert(0, str(SERVER))
    import app as service_app

    end = int(time.time()) + 30 * 86400
    modern = {"id": "sub_modern", "status": "active",
              "items": {"data": [{"current_period_end": end}]}}
    assert service_app._period_end(modern) == float(end)

    legacy = {"id": "sub_legacy", "status": "active", "current_period_end": end}
    assert service_app._period_end(legacy) == float(end)

    assert service_app._period_end({"id": "sub_none", "status": "active"}) is None

    # Several items: the subscription is paid up until the last one ends.
    multi = {"items": {"data": [{"current_period_end": end},
                                {"current_period_end": end + 86400}]}}
    assert service_app._period_end(multi) == float(end + 86400)


def test_a_subscription_event_in_the_modern_shape_sets_an_expiry(service):
    pytest.importorskip("stripe")
    client, store_mod, licence_mod, public = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE", None, stripe_sub="sub_shape")
    client.post("/activate", json={"key": key, "install": "unit-shape"})

    end = int(time.time()) + 30 * 86400
    body, headers = _signed({
        "id": "evt_unit_shape",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": "sub_shape", "status": "active",
                            "items": {"data": [{"current_period_end": end}]}}},
    })
    assert client.post("/stripe/webhook", content=body, headers=headers).status_code == 200

    state = client.get("/licence/state", params={"key": key}).json()
    assert state["expires"] == float(end), "a licence with no expiry never lapses"


def test_the_plan_name_corrects_itself_on_a_later_event(service):
    """The enrichment after checkout can fail. It must not stay wrong."""
    pytest.importorskip("stripe")
    client, store_mod, licence_mod, _ = service
    key = licence_mod.new_key()
    store_mod.create_licence(key, "", "FIRE", None, stripe_sub="sub_plan")
    assert client.get("/licence/state", params={"key": key}).json()["plan"] == "FIRE"

    end = int(time.time()) + 365 * 86400
    body, headers = _signed({
        "id": "evt_unit_plan",
        "type": "customer.subscription.updated",
        "data": {"object": {
            "id": "sub_plan", "status": "active",
            "items": {"data": [{"current_period_end": end,
                                "price": {"recurring": {"interval": "year"}}}]}}},
    })
    assert client.post("/stripe/webhook", content=body, headers=headers).status_code == 200
    assert client.get("/licence/state", params={"key": key}).json()["plan"] == "FIRE Annual"
