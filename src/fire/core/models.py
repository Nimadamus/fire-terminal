"""Domain types for the FIRE terminal.

These are the ONLY shapes that cross a venue boundary. A venue adapter
translates its own wire format into these; nothing above the adapter layer
ever sees a raw exchange payload.

Deliberately free of any valuation concept. A market here knows its identity,
its clock and its book. It does not know what it is worth, and nothing in the
customer application ever computes that.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    YES = "yes"
    NO = "no"


class OrderState(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ConnectionState(str, Enum):
    OFFLINE = "offline"
    CONNECTING = "connecting"
    READY = "ready"
    DEGRADED = "degraded"
    AUTH_FAILED = "auth_failed"


@dataclass(frozen=True)
class Instrument:
    """A tradeable contract. `series` groups them, `ticker` identifies one."""
    ticker: str
    series: str
    display: str
    strike: Optional[float] = None
    close_epoch: Optional[float] = None

    def seconds_left(self, now: float) -> Optional[float]:
        if self.close_epoch is None:
            return None
        return max(0.0, self.close_epoch - now)


@dataclass(frozen=True)
class BookLevel:
    price: float      # dollars per contract, 0.0 .. 1.0
    size: int         # contracts available


@dataclass(frozen=True)
class Book:
    """One side's resting liquidity, best price first."""
    yes: tuple[BookLevel, ...] = ()
    no: tuple[BookLevel, ...] = ()
    received_epoch: float = 0.0

    def best(self, side: Side) -> Optional[BookLevel]:
        levels = self.yes if side is Side.YES else self.no
        return levels[0] if levels else None

    def depth(self, side: Side) -> int:
        levels = self.yes if side is Side.YES else self.no
        return sum(lv.size for lv in levels)


@dataclass(frozen=True)
class IndexQuote:
    """Underlying reference price, for display."""
    index_id: str
    value: float
    received_epoch: float
    source: str = ""


@dataclass(frozen=True)
class OrderRequest:
    """What the customer asked for. Immutable once submitted."""
    ticker: str
    side: Side
    limit_price: float        # dollars per contract
    count: int
    budget_dollars: float     # the amount the customer typed


@dataclass(frozen=True)
class OrderResult:
    state: OrderState
    order_id: str = ""
    filled_count: int = 0
    average_price: float = 0.0
    fee_dollars: float = 0.0
    message: str = ""

    @property
    def cost_dollars(self) -> float:
        return self.filled_count * self.average_price + self.fee_dollars


@dataclass(frozen=True)
class Fill:
    ticker: str
    side: Side
    count: int
    price: float
    fee_dollars: float
    epoch: float
    order_id: str = ""


@dataclass(frozen=True)
class Position:
    ticker: str
    side: Side
    count: int
    average_price: float

    @property
    def cost_dollars(self) -> float:
        return self.count * self.average_price

    @property
    def payout_if_correct(self) -> float:
        return float(self.count)


@dataclass
class AccountSnapshot:
    balance_dollars: float = 0.0
    positions: list[Position] = field(default_factory=list)
    resting_orders: int = 0
    updated_epoch: float = 0.0
    stale: bool = False
