"""A subscription that lapses mid-session.

The failure this prevents: the customer learns their subscription ended at the
instant they click BUY, because that is the first code path that consults
entitlement. That is both a bad experience and a support ticket, so the state
has to reach the interface before the click.
"""
from __future__ import annotations

import time

import pytest

from fire.entitlement.policy import (
    short_suspension_reason, suspension_reason, trading_allowed,
)
from fire.entitlement.watch import EntitlementWatch
from fire.interfaces.entitlement import (
    Entitlement, EntitlementProvider, EntitlementStatus,
)
from fire.interfaces.venue import VenueMode

ACTIVE = Entitlement(EntitlementStatus.ACTIVE, None, "FIRE")
TRIAL = Entitlement(EntitlementStatus.TRIAL, None, "Trial")
EXPIRED = Entitlement(EntitlementStatus.EXPIRED, None, "FIRE")
REVOKED = Entitlement(EntitlementStatus.REVOKED, None, "FIRE")
UNLICENSED = Entitlement(EntitlementStatus.UNLICENSED, None, "")


class StubProvider(EntitlementProvider):
    def __init__(self, ent: Entitlement) -> None:
        self.ent = ent
        self.raise_on_refresh = False
        self.refreshes = 0

    def current(self) -> Entitlement:
        return self.ent

    def refresh(self, timeout_s: float = 5.0) -> Entitlement:
        self.refreshes += 1
        if self.raise_on_refresh:
            raise RuntimeError("network")
        return self.ent

    def redeem(self, licence_key: str) -> Entitlement:
        return self.ent


# -- policy ----------------------------------------------------------------
@pytest.mark.parametrize("ent,live,demo", [
    (ACTIVE, True, True),
    (TRIAL, True, True),
    (EXPIRED, False, True),      # lapsed billing must not kill the free mode
    (UNLICENSED, False, True),
    (REVOKED, False, False),     # revoked has to mean revoked, demo included
])
def test_what_each_state_permits(ent, live, demo):
    assert trading_allowed(VenueMode.LIVE, ent) is live
    assert trading_allowed(VenueMode.DEMO, ent) is demo


def test_no_provider_means_nothing_to_enforce():
    assert trading_allowed(VenueMode.LIVE, None) is True
    assert suspension_reason(VenueMode.LIVE, None) == ""


def test_the_reason_is_plain_and_reassures_about_open_positions():
    text = suspension_reason(VenueMode.LIVE, EXPIRED)
    assert "subscription has ended" in text
    assert "still open at the exchange" in text
    for jargon in ("entitlement", "EXPIRED", "status"):
        assert jargon not in text


def test_the_short_reason_fits_a_card():
    """One line inside a 268px panel. A second line is clipped away."""
    for ent in (EXPIRED, REVOKED, UNLICENSED):
        brief = short_suspension_reason(VenueMode.LIVE, ent)
        assert brief and len(brief) <= 28, brief
        assert len(brief) < len(suspension_reason(VenueMode.LIVE, ent))


def test_a_permitted_state_has_no_reason_to_show():
    assert suspension_reason(VenueMode.LIVE, ACTIVE) == ""
    assert short_suspension_reason(VenueMode.LIVE, ACTIVE) == ""


# -- watch -----------------------------------------------------------------
def test_a_lapse_is_reported_once_not_every_poll():
    p = StubProvider(ACTIVE)
    w = EntitlementWatch(p, interval_s=5.0)
    assert w.poll_once() is None

    p.ent = EXPIRED
    t = w.poll_once()
    assert t is not None and t.live_trading_lost
    assert w.poll_once() is None, "a settled state must not keep firing"


def test_the_ui_drains_a_transition_exactly_once():
    p = StubProvider(ACTIVE)
    w = EntitlementWatch(p, interval_s=5.0)
    p.ent = EXPIRED
    w.poll_once()
    assert w.take_transition() is not None
    assert w.take_transition() is None


def test_a_failed_check_never_downgrades_the_customer():
    """Losing access because the wifi dropped is worse than stale state."""
    p = StubProvider(ACTIVE)
    w = EntitlementWatch(p, interval_s=5.0)
    p.raise_on_refresh = True
    assert w.poll_once() is None
    assert w.latest().allows_live_trading


def test_renewing_restores_trading_without_a_restart():
    p = StubProvider(EXPIRED)
    w = EntitlementWatch(p, interval_s=5.0)
    assert not w.latest().allows_live_trading
    p.ent = ACTIVE
    t = w.poll_once()
    assert t is not None and t.live_trading_regained


def test_the_watch_thread_starts_stops_and_never_blocks():
    p = StubProvider(ACTIVE)
    w = EntitlementWatch(p, interval_s=5.0)
    began = time.time()
    w.start()
    w.stop()
    assert time.time() - began < 2.0
    assert p.refreshes == 0, "stopping promptly must not require a poll first"


def test_the_interval_has_a_floor():
    """A zero interval would spin a thread against a billing backend."""
    assert EntitlementWatch(StubProvider(ACTIVE), interval_s=0.0)._interval >= 5.0


# -- defence in depth ------------------------------------------------------
class _Part:
    def __init__(self, mode): self.mode = mode


class FakeLiveVenue:
    """Just enough shape for Session. Reports live, touches nothing."""
    display_name = "Fake"
    mode = VenueMode.LIVE

    def __init__(self):
        self.market_data = _Part(VenueMode.LIVE)
        self.execution = _Part(VenueMode.LIVE)
        self.account = _Part(VenueMode.LIVE)

    def connect(self): pass
    def disconnect(self): pass


def test_the_session_still_refuses_even_if_the_ui_missed_it():
    """The UI switching buttons off is convenience. This is the actual gate."""
    from fire.core.errors import EntitlementRequired
    from fire.core.session import Session

    session = Session(FakeLiveVenue(), VenueMode.LIVE, StubProvider(EXPIRED))
    with pytest.raises(EntitlementRequired):
        _ = session.execution
    # Market data and balance stay readable, so a lapsed customer can still
    # see what they hold.
    assert session.market_data is not None
    assert session.account is not None


def test_an_active_subscription_passes_the_session_gate():
    from fire.core.session import Session
    session = Session(FakeLiveVenue(), VenueMode.LIVE, StubProvider(ACTIVE))
    assert session.execution is not None
