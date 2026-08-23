"""Live adapter tests.

The adapter is fully exercised here without touching a network. A fake
transport stands in for HTTP, so translation, planning, order submission and
account parsing are all covered before an approved endpoint ever exists.
"""
from __future__ import annotations

import pytest

from fire.core.errors import (
    CredentialsInvalid, ExchangeNotConfigured, OrderRejected, SetupIncomplete,
)
from fire.core.models import OrderState, Side
from fire.core.session import Session
from fire.interfaces.venue import VenueMode
from fire.venues.kalshi import endpoints
from fire.venues.kalshi.auth import RequestSigner, signer_from_store
from fire.venues.kalshi.endpoints import EndpointProfile, REQUIRED_PATH_KEYS
from fire.venues.kalshi.transport import RateGate
from fire.venues.kalshi.venue import (
    LiveAccount, LiveExecution, LiveMarketData, LiveVenue, _asks_from_bids,
    _instrument,
)


# -- the compliance gate ---------------------------------------------------
def test_ships_unconfigured():
    """The build must not carry a live endpoint until permission is granted."""
    assert endpoints.ACTIVE.configured is False
    assert endpoints.ACTIVE.base_url == ""
    assert endpoints.is_configured() is False


def test_building_live_venue_is_refused_while_unconfigured():
    from fire.config.credentials import CredentialStore
    from fire.venues.kalshi.venue import build_live_venue
    with pytest.raises(ExchangeNotConfigured):
        build_live_venue(CredentialStore())


def test_profile_refuses_to_produce_urls_while_unconfigured():
    with pytest.raises(RuntimeError):
        endpoints.UNCONFIGURED.url("markets")


def test_configured_profile_builds_urls_and_signing_paths():
    """Proves wiring is a one object change, not a restructure."""
    profile = EndpointProfile(
        name="test", base_url="https://example.invalid", api_root="/api/v2",
        paths={k: f"/{k}" for k in REQUIRED_PATH_KEYS}
        | {"orderbook": "/markets/{ticker}/orderbook"},
        configured=True)
    assert profile.url("balance") == "https://example.invalid/api/v2/balance"
    assert profile.signing_path("balance") == "/api/v2/balance"
    assert profile.url("orderbook", ticker="ABC").endswith("/markets/ABC/orderbook")


# -- credential injection --------------------------------------------------
def _test_key_pem() -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()


@pytest.fixture(scope="module")
def signer() -> RequestSigner:
    from fire.config.credentials import Credentials
    return RequestSigner(Credentials(key_id="test-key", private_key_pem=_test_key_pem()))


def test_signer_produces_auth_headers(signer):
    headers = signer.headers("GET", "/api/v2/balance", timestamp_ms=1700000000000)
    assert headers["KALSHI-ACCESS-KEY"] == "test-key"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1700000000000"
    assert len(headers["KALSHI-ACCESS-SIGNATURE"]) > 40


def test_signature_changes_with_path(signer):
    a = signer.headers("GET", "/a", timestamp_ms=1)["KALSHI-ACCESS-SIGNATURE"]
    b = signer.headers("GET", "/b", timestamp_ms=1)["KALSHI-ACCESS-SIGNATURE"]
    assert a != b


def test_signer_never_exposes_the_key_material(signer):
    """A traceback or a diagnostic dump must not be able to reach the PEM."""
    assert "BEGIN" not in repr(signer)
    assert not any("PEM" in str(v) or "-----" in str(v)
                   for v in vars(signer).values())


def test_signer_rejects_a_bad_key():
    from fire.config.credentials import Credentials
    with pytest.raises(CredentialsInvalid):
        RequestSigner(Credentials(key_id="x", private_key_pem="not a key"))


def test_signer_from_store_requires_setup():
    class EmptyStore:
        def load(self):
            return None
    with pytest.raises(SetupIncomplete):
        signer_from_store(EmptyStore())


# -- wire translation ------------------------------------------------------
def test_asks_are_derived_from_the_opposite_bid_ladder():
    """To buy YES you cross the NO bids, so a yes ask is one minus a no bid."""
    levels = _asks_from_bids([["0.55", "10"], ["0.01", "3"], ["0.30", "5"]])
    # Cheapest ask first, because that is the one a buyer takes.
    assert [lv.price for lv in levels] == [0.45, 0.70, 0.99]
    assert levels[0].size == 10


def test_levels_survive_malformed_entries():
    assert (_asks_from_bids([["0.50", "1"], None, ["x", "y"], []])
            == _asks_from_bids([["0.50", "1"]]))


def test_a_bid_of_zero_or_one_produces_no_tradeable_ask():
    """1.00 and 0.00 would imply a free or worthless contract."""
    assert _asks_from_bids([["1.00", "5"], ["0.00", "5"]]) == ()


def test_instrument_translation():
    inst = _instrument({"ticker": "AAA-BBB", "series_ticker": "AAA",
                        "strike": "101.5", "close_time_epoch": 1700000000})
    assert inst.ticker == "AAA-BBB" and inst.strike == 101.5
    assert inst.seconds_left(1700000000) == 0.0


def test_instrument_requires_a_ticker():
    assert _instrument({"strike": 1}) is None


# -- execution against a fake transport ------------------------------------
class FakeTransport:
    """Stands in for HTTP. Records what would have been sent."""

    def __init__(self, responses: dict):
        self.responses = responses
        self.posted: list[tuple[str, dict]] = []
        self.degraded = False

    def get(self, key, **fmt):
        return self.responses.get(key, {})

    def post(self, key, body, **fmt):
        self.posted.append((key, body))
        return self.responses.get(key, {})


class FakeData:
    def __init__(self, book):
        self._book = book

    def book(self, ticker):
        return self._book


def _book():
    from fire.core.models import Book
    return Book(yes=_asks_from_bids([["0.50", "100"]]),
                no=_asks_from_bids([["0.60", "100"]]))


def test_live_order_is_always_immediate_or_cancel():
    t = FakeTransport({"orders": {"order": {"order_id": "1", "filled_count": 4,
                                            "average_fill_price_cents": 50}}})
    ex = LiveExecution(t, FakeData(_book()))
    request = ex.plan("T", Side.YES, 2.00)
    ex.submit(request)
    _, body = t.posted[0]
    assert body["time_in_force"] == "immediate_or_cancel"
    assert body["action"] == "buy" and body["side"] == "yes"
    assert body["price_cents"] == 50


def test_live_plan_honours_the_budget_guarantee():
    ex = LiveExecution(FakeTransport({}), FakeData(_book()))
    request = ex.plan("T", Side.YES, 2.00)
    assert request.count * request.limit_price <= 2.00 + 1e-9


def test_live_unfilled_order_is_not_reported_as_a_fill():
    t = FakeTransport({"orders": {"order": {"order_id": "2", "filled_count": 0,
                                            "status": "canceled"}}})
    ex = LiveExecution(t, FakeData(_book()))
    result = ex.submit(ex.plan("T", Side.NO, 2.00))
    assert result.state is OrderState.CANCELLED
    assert result.filled_count == 0


def test_live_rejected_order_raises_a_customer_error():
    t = FakeTransport({"orders": {"order": {"filled_count": 0, "status": "rejected"}}})
    ex = LiveExecution(t, FakeData(_book()))
    with pytest.raises(OrderRejected):
        ex.submit(ex.plan("T", Side.YES, 2.00))


def test_live_partial_fill_is_labelled_partial():
    t = FakeTransport({"orders": {"order": {"order_id": "3", "filled_count": 1,
                                            "average_fill_price_cents": 50}}})
    ex = LiveExecution(t, FakeData(_book()))
    request = ex.plan("T", Side.YES, 2.00)
    assert request.count > 1
    assert ex.submit(request).state is OrderState.PARTIAL


# -- account ---------------------------------------------------------------
def test_account_parses_balance_and_positions():
    profile = EndpointProfile(name="t", configured=True, base_url="x",
                              paths={k: "/" + k for k in REQUIRED_PATH_KEYS})
    t = FakeTransport({
        "balance": {"balance": 12345},
        "positions": {"market_positions": [
            {"ticker": "AAA", "position": 10, "market_exposure": 500},
            {"ticker": "BBB", "position": 0, "market_exposure": 0},
            {"ticker": "CCC", "position": -4, "market_exposure": 200},
        ], "resting_order_count": 2},
    })
    acct = LiveAccount(t, profile)
    acct.refresh()
    snap = acct.snapshot()
    assert snap.balance_dollars == 123.45
    assert snap.resting_orders == 2
    assert len(snap.positions) == 2          # the zero position is dropped
    assert snap.positions[0].side is Side.YES
    assert snap.positions[1].side is Side.NO


# -- mode integrity --------------------------------------------------------
def test_every_live_component_reports_live_mode():
    profile = EndpointProfile(name="t", configured=True, base_url="x",
                              paths={k: "/" + k for k in REQUIRED_PATH_KEYS})
    t = FakeTransport({})
    assert LiveMarketData(t, profile).mode == VenueMode.LIVE
    assert LiveExecution(t, FakeData(_book())).mode == VenueMode.LIVE
    assert LiveAccount(t, profile).mode == VenueMode.LIVE


def test_a_live_venue_cannot_be_held_in_a_demo_session():
    """The mirror of the demo guard: mode mismatch is caught either way."""
    from fire.core.errors import DemoModeOnly

    class PretendLive:
        mode = VenueMode.LIVE
        display_name = "Live"
        market_data = execution = account = None

        def connect(self): ...
        def disconnect(self): ...

    with pytest.raises(DemoModeOnly):
        Session(PretendLive(), VenueMode.DEMO)


# -- conduct ---------------------------------------------------------------
def test_rate_gate_paces_requests():
    import time
    gate = RateGate(per_second=20.0)
    start = time.monotonic()
    for _ in range(5):
        gate.wait()
    assert time.monotonic() - start >= 0.15
