"""The venue boundary.

Everything above this line (UI, preferences, entitlement, diagnostics) talks
only to these abstract types. Everything below it (demo simulator, Kalshi
adapter) implements them and is otherwise invisible.

This is the seam that keeps the commercial client free of proprietary logic:
the interfaces describe *executing what the customer asked for*. There is no
method here for "should I trade", "what is this worth" or "which candidate is
best", so no implementation of this interface can smuggle strategy upward.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Sequence

from fire.core.models import (
    AccountSnapshot, Book, ConnectionState, IndexQuote,
    Instrument, OrderRequest, OrderResult, Fill,
)


class VenueMode:
    """Hard, checkable identity for a venue implementation."""
    DEMO = "demo"
    LIVE = "live"


class MarketDataSource(ABC):
    """Read only market state."""

    @property
    @abstractmethod
    def mode(self) -> str:
        """VenueMode.DEMO or VenueMode.LIVE. Never computed, always a constant."""

    @abstractmethod
    def connection_state(self) -> ConnectionState: ...

    @abstractmethod
    def instruments(self) -> Sequence[Instrument]:
        """Currently tradeable contracts, one per supported coin."""

    @abstractmethod
    def book(self, ticker: str) -> Optional[Book]: ...

    @abstractmethod
    def index_quote(self, index_id: str) -> Optional[IndexQuote]: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...


class ExecutionVenue(ABC):
    """Order entry. The only place an order can be created."""

    @property
    @abstractmethod
    def mode(self) -> str: ...

    @abstractmethod
    def plan(self, ticker: str, side, budget_dollars: float) -> OrderRequest:
        """Turn 'spend this much on this side' into a concrete, checkable order.

        Walks the visible book only. Must never plan a count whose cost at the
        limit exceeds `budget_dollars`.
        """

    @abstractmethod
    def submit(self, request: OrderRequest) -> OrderResult:
        """Immediate or cancel. An order from FIRE never rests on the book."""

    @abstractmethod
    def recent_fills(self, limit: int = 50) -> Sequence[Fill]: ...


class AccountAdapter(ABC):
    """Balance, positions and resting order count."""

    @property
    @abstractmethod
    def mode(self) -> str: ...

    @abstractmethod
    def snapshot(self) -> AccountSnapshot: ...

    @abstractmethod
    def refresh(self) -> None: ...


class Venue(ABC):
    """One coherent trading environment. A session holds exactly one."""

    @property
    @abstractmethod
    def mode(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @property
    @abstractmethod
    def market_data(self) -> MarketDataSource: ...

    @property
    @abstractmethod
    def execution(self) -> ExecutionVenue: ...

    @property
    @abstractmethod
    def account(self) -> AccountAdapter: ...

    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...
