"""The session owns exactly one venue and enforces mode integrity.

This is the enforcement point for the demo/live split. The UI never holds a
venue directly; it holds a Session and asks for `session.execution`. Every
access re-checks that the venue's declared mode still matches the mode the
session was opened in, so a mismatch is caught at the call site rather than
after an order has gone out.

Belt and braces on purpose: the demo package cannot reach the network at all,
and this check means even a wiring mistake cannot cross the streams.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

from fire.core.errors import DemoModeOnly, EntitlementRequired
from fire.interfaces.entitlement import Entitlement, EntitlementProvider
from fire.interfaces.venue import (
    AccountAdapter, ExecutionVenue, MarketDataSource, Venue, VenueMode,
)


class Session:
    def __init__(self, venue: Venue, mode: str,
                 entitlement: Optional[EntitlementProvider] = None) -> None:
        if venue.mode != mode:
            raise DemoModeOnly(
                f"Session opened as {mode!r} but venue reports {venue.mode!r}."
            )
        self._venue = venue
        self._mode = mode
        self._entitlement = entitlement
        self._lock = threading.RLock()
        self._listeners: list[Callable[[], None]] = []

    # -- identity ----------------------------------------------------------
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def is_demo(self) -> bool:
        return self._mode == VenueMode.DEMO

    @property
    def is_live(self) -> bool:
        return self._mode == VenueMode.LIVE

    @property
    def read_only(self) -> bool:
        """A viewer install: real account, no order path."""
        return bool(getattr(self._venue, "read_only", False))

    @property
    def venue_name(self) -> str:
        return self._venue.display_name

    # -- guarded accessors -------------------------------------------------
    def _guard(self, component) -> None:
        if component.mode != self._mode:
            raise DemoModeOnly(
                f"{type(component).__name__} reports mode {component.mode!r} "
                f"inside a {self._mode!r} session."
            )

    @property
    def market_data(self) -> MarketDataSource:
        md = self._venue.market_data
        self._guard(md)
        return md

    @property
    def execution(self) -> ExecutionVenue:
        ex = self._venue.execution
        self._guard(ex)
        if self.is_live:
            self._require_entitlement()
        return ex

    def recent_fills(self, limit: int = 50):
        """Fill history, deliberately NOT gated by entitlement.

        Reading what you already did is not trading. A customer whose
        subscription lapsed must still be able to see their own history, the
        same way `account` stays readable. Mode integrity is still enforced.
        """
        ex = self._venue.execution
        self._guard(ex)
        return ex.recent_fills(limit)

    @property
    def account(self) -> AccountAdapter:
        ac = self._venue.account
        self._guard(ac)
        return ac

    # -- entitlement -------------------------------------------------------
    def _require_entitlement(self) -> None:
        if self._entitlement is None:
            return
        ent: Entitlement = self._entitlement.current()
        if not ent.allows_live_trading:
            raise EntitlementRequired(ent.message or f"Subscription status: {ent.status.value}.")

    def entitlement(self) -> Optional[Entitlement]:
        return self._entitlement.current() if self._entitlement else None

    # -- lifecycle ---------------------------------------------------------
    def connect(self) -> None:
        with self._lock:
            self._venue.connect()
        self._notify()

    def disconnect(self) -> None:
        with self._lock:
            self._venue.disconnect()
        self._notify()

    def raw_venue(self) -> Venue:
        """Escape hatch for demo-only controls such as Reset. Refuses in live."""
        if self.is_live:
            raise DemoModeOnly("Direct venue access is not available in live mode.")
        return self._venue

    # -- change notification ----------------------------------------------
    def on_change(self, fn: Callable[[], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        for fn in list(self._listeners):
            try:
                fn()
            except Exception:
                pass
