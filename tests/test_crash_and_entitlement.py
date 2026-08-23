"""Crash sanitisation and entitlement state machine."""
from __future__ import annotations

import time

import pytest

from fire.diagnostics import crash
from fire.interfaces.entitlement import Entitlement, EntitlementStatus


# -- crash sanitisation ----------------------------------------------------
def _capture(fn):
    """Run fn, return the formatted crash text."""
    try:
        fn()
    except Exception as exc:
        return crash._format(type(exc), exc, exc.__traceback__)
    raise AssertionError("expected an exception")


def test_crash_text_carries_no_local_variables():
    def boom():
        secret_key = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQ"  # noqa: F841
        raise ValueError("kaboom")

    text = _capture(boom)
    assert "MIIEvQIBADANBgkqhkiG9w0" not in text
    assert "kaboom" in text


def test_crash_text_redacts_a_key_id_in_the_message():
    def boom():
        raise ValueError("failed for key f6e2c2f5-2712-4fc8-9225-fb5d4884d9c5")

    text = _capture(boom)
    assert "f6e2c2f5" not in text
    assert "[redacted]" in text


def test_crash_text_redacts_the_user_path():
    def boom():
        raise ValueError(r"could not open C:\Users\SomeCustomer\thing.json")

    assert "SomeCustomer" not in _capture(boom)


def test_crash_text_withholds_source_from_credential_frames():
    """A frame in an auth or credential module must not render its source."""
    from fire.config.credentials import Credentials
    from fire.venues.kalshi.auth import RequestSigner

    def boom():
        RequestSigner(Credentials(key_id="k", private_key_pem="bogus"))

    try:
        boom()
    except Exception as exc:
        text = crash._format(type(exc), exc, exc.__traceback__)
    assert "<source withheld>" in text


def test_crash_report_is_suppressed_if_it_cannot_be_verified_clean(monkeypatch):
    """Losing a report beats leaking a credential."""
    monkeypatch.setattr(crash, "_format", lambda *a: "-----BEGIN PRIVATE KEY-----")
    try:
        raise ValueError("x")
    except ValueError as exc:
        assert crash.write_report(type(exc), exc, exc.__traceback__) is None


def test_crash_report_writes_when_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(crash, "logs_dir", lambda: tmp_path)
    try:
        raise ValueError("ordinary failure")
    except ValueError as exc:
        path = crash.write_report(type(exc), exc, exc.__traceback__)
    assert path is not None and path.exists()
    assert "ordinary failure" in path.read_text(encoding="utf-8")


# -- entitlement state machine --------------------------------------------
@pytest.mark.parametrize("status,live,demo", [
    (EntitlementStatus.TRIAL, True, True),
    (EntitlementStatus.ACTIVE, True, True),
    (EntitlementStatus.EXPIRED, False, True),
    (EntitlementStatus.REVOKED, False, False),
    (EntitlementStatus.UNLICENSED, False, True),
])
def test_entitlement_permissions(status, live, demo):
    ent = Entitlement(status)
    assert ent.allows_live_trading is live
    assert ent.allows_demo is demo


def test_expired_and_revoked_are_warnings():
    assert Entitlement(EntitlementStatus.EXPIRED).is_warning
    assert Entitlement(EntitlementStatus.REVOKED).is_warning
    assert not Entitlement(EntitlementStatus.ACTIVE).is_warning


def test_local_provider_grants_a_trial_on_first_run(tmp_path, monkeypatch):
    from fire.entitlement import local
    monkeypatch.setattr(local, "entitlement_file", lambda: tmp_path / "e.json")
    ent = local.LocalEntitlement().current()
    assert ent.status is EntitlementStatus.TRIAL
    assert ent.allows_live_trading


def test_local_provider_expires_a_finished_trial(tmp_path, monkeypatch):
    import json
    from fire.entitlement import local
    path = tmp_path / "e.json"
    path.write_text(json.dumps({"status": "trial", "expires": time.time() - 10}))
    monkeypatch.setattr(local, "entitlement_file", lambda: path)
    ent = local.LocalEntitlement().current()
    assert ent.status is EntitlementStatus.EXPIRED
    assert not ent.allows_live_trading
    assert ent.allows_demo          # demo survives expiry, by design


def test_revoked_blocks_demo_too(tmp_path, monkeypatch):
    import json
    from fire.entitlement import local
    path = tmp_path / "e.json"
    path.write_text(json.dumps({"status": "revoked"}))
    monkeypatch.setattr(local, "entitlement_file", lambda: path)
    assert not local.LocalEntitlement().current().allows_demo


def test_redeem_rejects_a_short_key(tmp_path, monkeypatch):
    from fire.entitlement import local
    monkeypatch.setattr(local, "entitlement_file", lambda: tmp_path / "e.json")
    assert not local.LocalEntitlement().redeem("abc").allows_live_trading


def test_redeem_activates_a_plausible_key(tmp_path, monkeypatch):
    from fire.entitlement import local
    monkeypatch.setattr(local, "entitlement_file", lambda: tmp_path / "e.json")
    ent = local.LocalEntitlement().redeem("FIRE-XXXX-YYYY-ZZZZ")
    assert ent.status is EntitlementStatus.ACTIVE


def test_stored_licence_key_is_never_kept_in_full(tmp_path, monkeypatch):
    import json
    from fire.entitlement import local
    path = tmp_path / "e.json"
    monkeypatch.setattr(local, "entitlement_file", lambda: path)
    local.LocalEntitlement().redeem("FIRE-SECRET-KEY-1234")
    stored = json.loads(path.read_text())
    assert "FIRE-SECRET-KEY-1234" not in json.dumps(stored)


# -- session gating --------------------------------------------------------
def test_live_session_refuses_execution_without_entitlement():
    from fire.core.errors import EntitlementRequired
    from fire.core.session import Session
    from fire.interfaces.venue import VenueMode

    class Expired:
        def current(self):
            return Entitlement(EntitlementStatus.EXPIRED, message="ended")
        def refresh(self, timeout_s=5.0):
            return self.current()
        def redeem(self, k):
            return self.current()

    class PretendLive:
        mode = VenueMode.LIVE
        display_name = "Live"
        market_data = account = None
        execution = type("E", (), {"mode": VenueMode.LIVE})()

        def connect(self): ...
        def disconnect(self): ...

    session = Session(PretendLive(), VenueMode.LIVE, Expired())
    with pytest.raises(EntitlementRequired):
        _ = session.execution
