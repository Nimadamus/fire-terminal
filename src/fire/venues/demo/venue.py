"""Demo venue: a complete, self-contained trading environment with no network.

Hard separation from live is structural, not a flag:
  * this package imports no HTTP or socket library at all
  * every object here reports mode == VenueMode.DEMO
  * `Session` refuses to hold a venue whose mode disagrees with the mode it
    was asked for, so a demo order has no reachable path to a live endpoint
"""
from __future__ import annotations

import itertools
import threading
import time
from typing import Optional, Sequence

from fire.core.errors import MarketUnavailable
from fire.core.planning import plan_from_book
from fire.core.models import (
    AccountSnapshot, Book, ConnectionState, Fill, IndexQuote, Instrument,
    OrderRequest, OrderResult, OrderState, Position, Side,
)
from fire.interfaces.venue import (
    AccountAdapter, ExecutionVenue, MarketDataSource, Venue, VenueMode,
)
from fire.venues.demo.simulator import MarketSimulator

DEMO_STARTING_BALANCE = 1_000.00
DEMO_FEE_PER_CONTRACT = 0.0035   # a plausible, rounded stand-in


class _DemoState:
    """Shared mutable state for one demo session."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.sim = MarketSimulator()
        self.balance = DEMO_STARTING_BALANCE
        self.positions: dict[tuple[str, Side], Position] = {}
        self.fills: list[Fill] = []
        self._ids = itertools.count(1)

    def next_id(self) -> str:
        return f"demo-{next(self._ids):06d}"


class DemoMarketData(MarketDataSource):
    def __init__(self, state: _DemoState) -> None:
        self._s = state
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def mode(self) -> str:
        return VenueMode.DEMO

    def connection_state(self) -> ConnectionState:
        return ConnectionState.READY if self._running else ConnectionState.OFFLINE

    def instruments(self) -> Sequence[Instrument]:
        now = time.time()
        with self._s.lock:
            return [self._s.sim.state(c).instrument(now) for c in self._s.sim.codes()]

    def book(self, ticker: str) -> Optional[Book]:
        now = time.time()
        with self._s.lock:
            st = self._s.sim.by_ticker(ticker, now)
            return st.book(now) if st else None

    def index_quote(self, index_id: str) -> Optional[IndexQuote]:
        code = index_id.split(".")[-1]
        now = time.time()
        with self._s.lock:
            if code not in self._s.sim.codes():
                return None
            return self._s.sim.state(code).index_quote(now)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="demo-sim")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        while self._running:
            with self._s.lock:
                self._s.sim.tick()
            time.sleep(0.25)


class DemoExecution(ExecutionVenue):
    def __init__(self, state: _DemoState, data: DemoMarketData) -> None:
        self._s = state
        self._data = data

    @property
    def mode(self) -> str:
        return VenueMode.DEMO

    def plan(self, ticker: str, side: Side, budget_dollars: float) -> OrderRequest:
        book = self._data.book(ticker)
        if book is None:
            raise MarketUnavailable("That demo market is between windows.")
        return plan_from_book(ticker, side, budget_dollars, book)

    def submit(self, request: OrderRequest) -> OrderResult:
        with self._s.lock:
            cost = request.count * request.limit_price
            fee = round(request.count * DEMO_FEE_PER_CONTRACT, 4)
            if cost + fee > self._s.balance:
                return OrderResult(state=OrderState.REJECTED,
                                   message="Demo balance is too low for that order.")
            self._s.balance -= (cost + fee)
            key = (request.ticker, request.side)
            prev = self._s.positions.get(key)
            if prev:
                total = prev.count + request.count
                avg = (prev.cost_dollars + cost) / total
                self._s.positions[key] = Position(request.ticker, request.side,
                                                  total, avg)
            else:
                self._s.positions[key] = Position(request.ticker, request.side,
                                                  request.count, request.limit_price)
            oid = self._s.next_id()
            self._s.fills.append(Fill(
                ticker=request.ticker, side=request.side, count=request.count,
                price=request.limit_price, fee_dollars=fee, epoch=time.time(),
                order_id=oid,
            ))
            return OrderResult(state=OrderState.FILLED, order_id=oid,
                               filled_count=request.count,
                               average_price=request.limit_price,
                               fee_dollars=fee,
                               message="Demo order filled.")

    def recent_fills(self, limit: int = 50) -> Sequence[Fill]:
        with self._s.lock:
            return list(reversed(self._s.fills[-limit:]))


class DemoAccount(AccountAdapter):
    def __init__(self, state: _DemoState) -> None:
        self._s = state

    @property
    def mode(self) -> str:
        return VenueMode.DEMO

    def snapshot(self) -> AccountSnapshot:
        with self._s.lock:
            return AccountSnapshot(
                balance_dollars=round(self._s.balance, 2),
                positions=list(self._s.positions.values()),
                resting_orders=0,
                updated_epoch=time.time(),
                stale=False,
            )

    def refresh(self) -> None:
        return None


class DemoVenue(Venue):
    """The whole demo environment."""

    def __init__(self) -> None:
        self._s = _DemoState()
        self._data = DemoMarketData(self._s)
        self._exec = DemoExecution(self._s, self._data)
        self._acct = DemoAccount(self._s)

    @property
    def mode(self) -> str:
        return VenueMode.DEMO

    @property
    def display_name(self) -> str:
        return "Demo"

    @property
    def market_data(self) -> MarketDataSource:
        return self._data

    @property
    def execution(self) -> ExecutionVenue:
        return self._exec

    @property
    def account(self) -> AccountAdapter:
        return self._acct

    def connect(self) -> None:
        self._data.start()

    def disconnect(self) -> None:
        self._data.stop()

    def reset(self) -> None:
        """Give the customer a clean demo account back."""
        with self._s.lock:
            self._s.balance = DEMO_STARTING_BALANCE
            self._s.positions.clear()
            self._s.fills.clear()
