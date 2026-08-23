"""The client half of licensing.

Two failure modes are being guarded here and they pull in opposite directions:

  * believing a licence that was not issued by us, which gives the product away
  * refusing a licence that was, which locks a paying customer out of a live
    position because our server had a bad afternoon

The first is guarded by signature checking, the second by the grace window.
"""
from __future__ import annotations

import base64
import json
import time

import pytest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from fire.entitlement.remote import RemoteEntitlement
from fire.entitlement.token import (
    DEFAULT_GRACE_DAYS, TokenInvalid, TokenPayload, is_within_grace, sign, verify,
)
from fire.interfaces.entitlement import EntitlementStatus


@pytest.fixture
def keys():
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    public = base64.urlsafe_b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)).decode("ascii").rstrip("=")
    return pem, public.encode("ascii")


@pytest.fixture
def provider(tmp_path, monkeypatch, keys):
    _, public = keys
    from fire.config import paths
    from fire.entitlement import remote as remote_mod
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "entitlement_file", lambda: tmp_path / "ent.json")
    monkeypatch.setattr(remote_mod, "entitlement_file", lambda: tmp_path / "ent.json")
    monkeypatch.setattr(remote_mod, "data_dir", lambda: tmp_path)
    return RemoteEntitlement("https://licence.invalid", public, install="unit-1")


def _cache(provider, tmp_path, token: str, key: str = "") -> None:
    body = {"token": token}
    if key:
        body["key"] = key
    (tmp_path / "ent.json").write_text(json.dumps(body), encoding="utf-8")
    provider._cached = None


def _token(pem: bytes, **kw) -> str:
    fields = {"status": "active", "expires": time.time() + 30 * 86400,
              "plan": "FIRE Monthly", "install": "unit-1",
              "issued": time.time(), "grace_days": DEFAULT_GRACE_DAYS}
    fields.update(kw)
    return sign(TokenPayload(**fields), pem)


# -- the install id --------------------------------------------------------
def test_the_install_id_is_random_and_stable(tmp_path, monkeypatch):
    """Random, not a hardware fingerprint. It must survive a restart and say
    nothing about the machine or the person."""
    from fire.config import paths
    from fire.entitlement import remote as remote_mod
    monkeypatch.setattr(remote_mod, "data_dir", lambda: tmp_path)
    monkeypatch.setattr(paths, "data_dir", lambda: tmp_path)

    first = remote_mod.install_id()
    assert len(first) == 32 and first.isalnum()
    assert remote_mod.install_id() == first

    import platform
    for leak in (platform.node(), platform.machine()):
        if leak:
            assert leak.lower() not in first.lower()


# -- believing only what we signed ----------------------------------------
def test_a_forged_token_is_refused(provider, tmp_path):
    """The whole point: a customer cannot mint their own subscription."""
    other = Ed25519PrivateKey.generate()
    pem = other.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    _cache(provider, tmp_path, _token(pem))
    assert provider.current().status is EntitlementStatus.UNLICENSED


def test_an_edited_token_is_refused(provider, tmp_path, keys):
    pem, _ = keys
    good = _token(pem, status="expired")
    body, sig = good.split(".", 1)
    tampered = base64.urlsafe_b64encode(
        json.dumps({"v": 1, "status": "active", "expires": time.time() + 99999,
                    "install": "unit-1", "issued": time.time(),
                    "grace_days": 7}).encode()).decode().rstrip("=")
    _cache(provider, tmp_path, f"{tampered}.{sig}")
    assert provider.current().status is EntitlementStatus.UNLICENSED
    assert not provider.current().allows_live_trading


def test_a_token_for_another_install_is_refused(provider, tmp_path, keys):
    """Copying the licence file to a second machine must not work."""
    pem, _ = keys
    _cache(provider, tmp_path, _token(pem, install="someone-else"))
    assert provider.current().status is EntitlementStatus.UNLICENSED


def test_a_valid_token_is_believed(provider, tmp_path, keys):
    pem, _ = keys
    _cache(provider, tmp_path, _token(pem))
    ent = provider.current()
    assert ent.status is EntitlementStatus.ACTIVE
    assert ent.plan == "FIRE Monthly"
    assert ent.allows_live_trading


# -- expiry ----------------------------------------------------------------
def test_a_token_past_its_own_expiry_does_not_allow_trading(provider, tmp_path, keys):
    """Even a perfectly signed token stops working when the period ends."""
    pem, _ = keys
    _cache(provider, tmp_path, _token(pem, expires=time.time() - 60))
    ent = provider.current()
    assert ent.status is EntitlementStatus.EXPIRED
    assert not ent.allows_live_trading
    assert ent.allows_demo, "demo must survive a lapsed subscription"


def test_a_revoked_token_stops_demo_too(provider, tmp_path, keys):
    pem, _ = keys
    _cache(provider, tmp_path, _token(pem, status="revoked"))
    ent = provider.current()
    assert ent.status is EntitlementStatus.REVOKED
    assert not ent.allows_live_trading and not ent.allows_demo


# -- being offline ---------------------------------------------------------
def test_a_recent_token_survives_the_service_being_unreachable(provider, tmp_path, keys):
    """The base url is unroutable, so refresh genuinely fails."""
    pem, _ = keys
    _cache(provider, tmp_path, _token(pem))
    ent = provider.refresh(timeout_s=0.01)
    assert ent.status is EntitlementStatus.ACTIVE, "an outage is not an expiry"


def test_a_token_beyond_its_grace_window_stops_trusting_itself(provider, tmp_path, keys):
    pem, _ = keys
    stale = time.time() - (DEFAULT_GRACE_DAYS + 1) * 86400
    _cache(provider, tmp_path, _token(pem, issued=stale,
                                      expires=time.time() + 99999))
    ent = provider.current()
    assert not ent.allows_live_trading
    # And it must not accuse the customer of anything.
    assert "Refresh" in ent.message
    assert "revoked" not in ent.message.lower()


def test_the_grace_window_is_measured_from_issue(keys):
    payload = TokenPayload(status="active", expires=None,
                           issued=time.time() - 86400, grace_days=7)
    assert is_within_grace(payload)
    old = TokenPayload(status="active", expires=None,
                       issued=time.time() - 8 * 86400, grace_days=7)
    assert not is_within_grace(old)


# -- redeeming -------------------------------------------------------------
def test_an_obviously_wrong_key_never_reaches_the_network(provider):
    ent = provider.redeem("short")
    assert ent.status is EntitlementStatus.UNLICENSED
    assert "does not look right" in ent.message


def test_a_failed_activation_says_what_to_do(provider):
    ent = provider.redeem("FIRE-ABCDE-ABCDE-ABCDE-ABCDE")
    assert not ent.allows_live_trading
    assert "support bundle" in ent.message or "connection" in ent.message


# -- what lands on disk ----------------------------------------------------
def test_nothing_personal_is_written_to_the_cache(provider, tmp_path, keys):
    pem, _ = keys
    _cache(provider, tmp_path, _token(pem, key_tail="9F2C"), key="FIRE-AAAAA")
    raw = (tmp_path / "ent.json").read_text(encoding="utf-8")
    payload = verify(json.loads(raw)["token"], provider._pub, "unit-1")
    assert payload.key_tail == "9F2C"
    for field in ("email", "name", "address", "card"):
        assert field not in raw.lower()


def test_a_missing_cache_is_unlicensed_not_a_crash(provider):
    assert provider.current().status is EntitlementStatus.UNLICENSED


def test_a_corrupt_cache_is_unlicensed_not_a_crash(provider, tmp_path):
    (tmp_path / "ent.json").write_text("{not json", encoding="utf-8")
    provider._cached = None
    assert provider.current().status is EntitlementStatus.UNLICENSED
