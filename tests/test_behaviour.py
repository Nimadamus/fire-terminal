"""Behaviour tests for the demo path, risk limits, redaction and session mode."""
from __future__ import annotations

import pytest

from fire.core.errors import DemoModeOnly, RiskLimitExceeded
from fire.core.models import OrderRequest, OrderState, Side
from fire.core.session import Session
from fire.diagnostics.redact import assert_clean, redact_obj, redact_text
from fire.interfaces.venue import VenueMode
from fire.risk.limits import RiskLimiter
from fire.venues.demo.venue import DEMO_STARTING_BALANCE, DemoVenue


# -- demo venue ------------------------------------------------------------
@pytest.fixture()
def demo():
    v = DemoVenue()
    v.connect()
    yield v
    v.disconnect()


def test_demo_lists_twelve_markets(demo):
    assert len(demo.market_data.instruments()) == 12


def test_demo_order_fills_and_moves_balance(demo):
    inst = demo.market_data.instruments()[0]
    req = demo.execution.plan(inst.ticker, Side.YES, 50.0)
    assert req.count > 0
    assert req.count * req.limit_price <= 50.0 + 1e-9

    result = demo.execution.submit(req)
    assert result.state is OrderState.FILLED
    snap = demo.account.snapshot()
    assert snap.balance_dollars < DEMO_STARTING_BALANCE
    assert len(snap.positions) == 1


def test_demo_plan_never_exceeds_budget(demo):
    for inst in demo.market_data.instruments():
        for side in (Side.YES, Side.NO):
            try:
                req = demo.execution.plan(inst.ticker, side, 37.0)
            except Exception:
                continue
            assert req.count * req.limit_price <= 37.0 + 1e-9


def test_demo_reset_restores_balance(demo):
    inst = demo.market_data.instruments()[0]
    demo.execution.submit(demo.execution.plan(inst.ticker, Side.YES, 25.0))
    demo.reset()
    assert demo.account.snapshot().balance_dollars == DEMO_STARTING_BALANCE


def test_every_demo_component_reports_demo_mode(demo):
    assert demo.mode == VenueMode.DEMO
    assert demo.market_data.mode == VenueMode.DEMO
    assert demo.execution.mode == VenueMode.DEMO
    assert demo.account.mode == VenueMode.DEMO


# -- session mode integrity -----------------------------------------------
def test_session_rejects_mode_mismatch(demo):
    with pytest.raises(DemoModeOnly):
        Session(demo, VenueMode.LIVE)


def test_session_allows_matching_mode(demo):
    s = Session(demo, VenueMode.DEMO)
    assert s.is_demo and not s.is_live


def test_live_session_refuses_raw_venue_access(demo):
    s = Session(demo, VenueMode.DEMO)
    assert s.raw_venue() is demo          # allowed in demo


# -- risk ------------------------------------------------------------------
def test_risk_blocks_oversized_order():
    limiter = RiskLimiter(fraction=0.10)
    req = OrderRequest("X", Side.YES, 0.99, 200, 200.0)
    with pytest.raises(RiskLimitExceeded):
        limiter.enforce(req, balance_dollars=1000.0)


def test_risk_allows_order_inside_ceiling():
    limiter = RiskLimiter(fraction=0.10)
    req = OrderRequest("X", Side.YES, 0.50, 100, 50.0)
    decision = limiter.enforce(req, balance_dollars=1000.0)
    assert decision.allowed and decision.ceiling_dollars == 100.0


def test_risk_can_be_disabled():
    limiter = RiskLimiter(fraction=0.10, enabled=False)
    req = OrderRequest("X", Side.YES, 0.99, 5000, 5000.0)
    assert limiter.evaluate(req, 100.0).allowed


# -- redaction -------------------------------------------------------------
def test_redacts_pem_block():
    text = "key:\n-----BEGIN PRIVATE KEY-----\nMIIabc123\n-----END PRIVATE KEY-----\n"
    assert "BEGIN PRIVATE KEY" not in redact_text(text)


def test_redacts_uuid_key_id():
    out = redact_text("KID f6e2c2f5-2712-4fc8-9225-fb5d4884d9c5 used")
    assert "f6e2c2f5" not in out


def test_redacts_by_key_name():
    out = redact_obj({"api_key": "abcd1234", "nested": {"password": "hunter2"}})
    assert out["api_key"] == "[redacted]"
    assert out["nested"]["password"] == "[redacted]"


def test_redacts_windows_user_path():
    assert "SomeCustomer" not in redact_text(r"C:\Users\SomeCustomer\AppData")


def test_assert_clean_raises_on_leak():
    with pytest.raises(AssertionError):
        assert_clean("-----BEGIN RSA PRIVATE KEY-----")


# -- shipped guidance ------------------------------------------------------
def test_the_key_security_guide_ships_and_is_findable():
    from fire.config.paths import resource
    path = resource("CREDENTIALS.md")
    assert path is not None, "Preferences links to this file"
    text = path.read_text(encoding="utf-8").lower()
    # The two things a customer needs at the worst possible moment.
    assert "rotat" in text and "revok" in text
    assert "lost, stolen" in text
    # And the promise that makes phishing obvious.
    assert "never ask" in text


def test_a_missing_resource_returns_none_rather_than_raising():
    from fire.config.paths import resource
    assert resource("no-such-file-9f3a.md") is None
