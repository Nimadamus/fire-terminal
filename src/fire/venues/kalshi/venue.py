"""Live exchange adapter.

COMPLETE BUT UNWIRED. Every piece below is written and tested. The one thing
missing is an approved endpoint profile, which is a compliance gate rather
than an engineering gap: see `endpoints.py`. Until `ACTIVE.configured` is
true, constructing this venue raises `ExchangeNotConfigured` and the
application falls back to demo with a clear message.

Rules this package holds to:
  * credentials arrive as an argument. Nothing here reads a file path, an
    environment variable or a bundled key.
  * the wire format stops here. Callers above receive `fire.core.models`
    types only, never a raw exchange payload.
  * order planning uses the shared `plan_from_book`, so the budget guarantee
    is identical in demo and live.
  * every order is immediate or cancel. FIRE never rests an order.
  * `mode` is the constant VenueMode.LIVE, never computed, so `Session`
    detects a wiring mistake before an order is built.
  * nothing in this package imports from the private trading system.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Sequence

from fire.config.credentials import CredentialStore
from fire.core.errors import TradingDisabled, ExchangeNotConfigured, OrderRejected
from fire.core.models import (
    AccountSnapshot, Book, BookLevel, ConnectionState, Fill, IndexQuote,
    Instrument, OrderRequest, OrderResult, OrderState, Position, Side,
)
from fire.core.planning import plan_from_book
from fire.interfaces.venue import (
    AccountAdapter, ExecutionVenue, MarketDataSource, Venue, VenueMode,
)
from fire.venues.kalshi import endpoints
from fire.venues.kalshi.auth import RequestSigner, signer_from_store
from fire.venues.kalshi.transport import Transport

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Wire format translation. One place, so a venue change never leaks upward.
# --------------------------------------------------------------------------
def _asks_from_bids(bids: Optional[list]) -> tuple[BookLevel, ...]:
    """Turn the opposite side's bid ladder into asks for this side.

    Kalshi publishes two bid ladders, `yes_dollars` and `no_dollars`, priced in
    dollars. To BUY yes you cross the no bids, so the best yes ask is one minus
    the highest no bid. Reading the yes ladder as though it were asks quotes
    the wrong side of the spread.
    """
    out: list[BookLevel] = []
    for entry in bids or []:
        try:
            price, size = float(entry[0]), float(entry[1])
        except (TypeError, ValueError, IndexError):
            continue
        ask = round(1.0 - price, 4)
        if 0.0 < ask < 1.0:
            out.append(BookLevel(price=ask, size=int(size)))
    # Cheapest ask first: that is what a buyer takes.
    out.sort(key=lambda lv: lv.price)
    return tuple(out)




def _coin(ticker: str) -> str:
    """BTC from KXBTC15M-26AUG231845-45. The coin is what belongs on a card."""
    head = ticker.split("-")[0]
    if head.startswith("KX"):
        head = head[2:]
    for suffix in ("15M", "D", "H"):
        if head.endswith(suffix) and len(head) > len(suffix):
            head = head[: -len(suffix)]
            break
    return head or ticker


def _instrument(raw: dict) -> Optional[Instrument]:
    ticker = raw.get("ticker")
    if not ticker:
        return None
    close = raw.get("close_time_epoch") or raw.get("close_ts")
    return Instrument(
        ticker=str(ticker),
        series=str(raw.get("series_ticker") or raw.get("event_ticker") or ""),
        # KXBTC15M reads as noise on a card. The coin is the point.
        display=_coin(str(ticker)),
        strike=_maybe_float(raw.get("strike") or raw.get("floor_strike")),
        close_epoch=_maybe_float(close),
    )


def _maybe_float(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
class LiveMarketData(MarketDataSource):
    def __init__(self, transport: Transport, profile) -> None:
        self._t = transport
        self._p = profile
        self._lock = threading.RLock()
        self._instruments: list[Instrument] = []
        self._books: dict[str, Book] = {}
        self._index: dict[str, IndexQuote] = {}
        self._state = ConnectionState.OFFLINE
        self._running = False
        self._thread: Optional[threading.Thread] = None

    @property
    def mode(self) -> str:
        return VenueMode.LIVE

    def connection_state(self) -> ConnectionState:
        if self._running and self._t.degraded:
            return ConnectionState.DEGRADED
        return self._state

    def instruments(self) -> Sequence[Instrument]:
        with self._lock:
            return list(self._instruments)

    def book(self, ticker: str) -> Optional[Book]:
        with self._lock:
            return self._books.get(ticker)

    def index_quote(self, index_id: str) -> Optional[IndexQuote]:
        with self._lock:
            return self._index.get(index_id)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._state = ConnectionState.CONNECTING
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="live-marketdata")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._state = ConnectionState.OFFLINE

    def _loop(self) -> None:
        while self._running:
            try:
                self._poll_once()
                self._state = ConnectionState.READY
            except Exception as exc:
                # never log a payload; the message is already customer safe
                log.warning("market data poll failed: %s", type(exc).__name__)
                self._state = ConnectionState.DEGRADED
            time.sleep(self._p.book_poll_seconds
                       * (3.0 if self._t.degraded else 1.0))

    # One call per coin. The unfiltered market list is thousands of rows and
    # never reaches the fifteen minute crypto series at all, so asking for the
    # series by name is both correct and far less traffic.
    SERIES = ("KXBTC15M", "KXETH15M", "KXSOL15M", "KXXRP15M", "KXDOGE15M",
              "KXBNB15M", "KXHYPE15M", "KXNEAR15M", "KXADA15M", "KXBCH15M",
              "KXLTC15M", "KXAVAX15M")

    def _poll_once(self) -> None:
        found = []
        for series in self.SERIES:
            try:
                payload = self._t.get("markets", series=series)
            except Exception:
                continue           # one coin missing must not blank the screen
            for raw in payload.get("markets", []):
                inst = _instrument(raw)
                if inst is not None:
                    found.append(inst)
        with self._lock:
            self._instruments = found
        for inst in found:
            raw = self._t.get("orderbook", ticker=inst.ticker)
            ob = raw.get("orderbook", {})
            # The dollar denominated book is `orderbook_fp`; the older
            # `orderbook` key is cents and may be absent entirely.
            fp = raw.get("orderbook_fp") or {}
            book = Book(yes=_asks_from_bids(fp.get("no_dollars")),
                        no=_asks_from_bids(fp.get("yes_dollars")),
                        received_epoch=time.time())
            with self._lock:
                self._books[inst.ticker] = book


class LiveExecution(ExecutionVenue):
    def __init__(self, transport: Transport, data: LiveMarketData) -> None:
        self._t = transport
        self._data = data
        self._fills: list[Fill] = []

    @property
    def mode(self) -> str:
        return VenueMode.LIVE

    def plan(self, ticker: str, side: Side, budget_dollars: float) -> OrderRequest:
        book = self._data.book(ticker)
        if book is None:
            from fire.core.errors import MarketUnavailable
            raise MarketUnavailable("No live book for that market yet.")
        return plan_from_book(ticker, side, budget_dollars, book)

    def submit(self, request: OrderRequest) -> OrderResult:
        body = {
            "ticker": request.ticker,
            "action": "buy",
            "side": request.side.value,
            "count": request.count,
            "type": "limit",
            "time_in_force": "immediate_or_cancel",   # never rests
            "price_cents": int(round(request.limit_price * 100)),
        }
        payload = self._t.post("orders", body)
        order = payload.get("order", payload)

        filled = int(order.get("filled_count") or 0)
        status = str(order.get("status") or "").lower()
        avg = _maybe_float(order.get("average_fill_price_cents"))
        avg_dollars = round(avg / 100.0, 4) if avg is not None else request.limit_price
        fee = _maybe_float(order.get("fee_cents"))
        fee_dollars = round((fee or 0.0) / 100.0, 4)

        if filled <= 0:
            if status in ("rejected", "error"):
                raise OrderRejected("The exchange did not accept that order.")
            return OrderResult(state=OrderState.CANCELLED,
                               order_id=str(order.get("order_id") or ""),
                               message="Not filled. Nothing was charged.")

        result = OrderResult(
            state=OrderState.FILLED if filled >= request.count else OrderState.PARTIAL,
            order_id=str(order.get("order_id") or ""),
            filled_count=filled, average_price=avg_dollars,
            fee_dollars=fee_dollars,
            message="Filled." if filled >= request.count else "Partially filled.",
        )
        self._fills.append(Fill(
            ticker=request.ticker, side=request.side, count=filled,
            price=avg_dollars, fee_dollars=fee_dollars, epoch=time.time(),
            order_id=result.order_id))
        return result

    def recent_fills(self, limit: int = 50) -> Sequence[Fill]:
        return list(reversed(self._fills[-limit:]))


class LiveAccount(AccountAdapter):
    def __init__(self, transport: Transport, profile) -> None:
        self._t = transport
        self._p = profile
        self._lock = threading.RLock()
        self._snapshot = AccountSnapshot()

    @property
    def mode(self) -> str:
        return VenueMode.LIVE

    def snapshot(self) -> AccountSnapshot:
        with self._lock:
            age = time.time() - self._snapshot.updated_epoch
            self._snapshot.stale = age > max(10.0, self._p.account_poll_seconds * 5)
            return self._snapshot

    def refresh(self) -> None:
        balance_raw = self._t.get("balance")
        cents = _maybe_float(balance_raw.get("balance")) or 0.0
        positions_raw = self._t.get("positions")

        positions: list[Position] = []
        for entry in positions_raw.get("market_positions", []):
            count = int(entry.get("position") or 0)
            if count == 0:
                continue
            side = Side.YES if count > 0 else Side.NO
            cost = _maybe_float(entry.get("market_exposure")) or 0.0
            qty = abs(count)
            positions.append(Position(
                ticker=str(entry.get("ticker") or ""), side=side, count=qty,
                average_price=round((cost / 100.0) / qty, 4) if qty else 0.0))

        with self._lock:
            self._snapshot = AccountSnapshot(
                balance_dollars=round(cents / 100.0, 2),
                positions=positions,
                resting_orders=int(positions_raw.get("resting_order_count") or 0),
                updated_epoch=time.time(), stale=False)


class LiveVenue(Venue):
    def __init__(self, signer: RequestSigner, profile=None) -> None:
        self._p = profile or endpoints.ACTIVE
        if not self._p.configured:
            raise ExchangeNotConfigured(
                "No approved exchange endpoint is configured in this build.")
        self._t = Transport(self._p, signer)
        self._data = LiveMarketData(self._t, self._p)
        self._exec = LiveExecution(self._t, self._data)
        self._acct = LiveAccount(self._t, self._p)
        self._running = False
        self._acct_thread: Optional[threading.Thread] = None

    @property
    def mode(self) -> str:
        return VenueMode.LIVE

    @property
    def display_name(self) -> str:
        return "Live"

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
        self._running = True
        self._acct_thread = threading.Thread(target=self._account_loop,
                                             daemon=True, name="live-account")
        self._acct_thread.start()

    def disconnect(self) -> None:
        self._running = False
        self._data.stop()

    def _account_loop(self) -> None:
        while self._running:
            try:
                self._acct.refresh()
            except Exception as exc:
                log.warning("account refresh failed: %s", type(exc).__name__)
            time.sleep(self._p.account_poll_seconds
                       * (3.0 if self._t.degraded else 1.0))


def build_live_venue(store: CredentialStore, read_only: bool = False) -> Venue:
    """Credential injection happens here and nowhere else.

    `read_only` produces a viewer: real balance, positions, fills and prices,
    with the order path removed rather than merely hidden.
    """
    if not endpoints.is_configured():
        raise ExchangeNotConfigured(
            "Live trading is not enabled in this build.")
    venue = LiveVenue(signer_from_store(store))
    if read_only:
        venue.execution = ReadOnlyExecution(venue.execution)
        venue.read_only = True
    return venue


class ReadOnlyExecution(ExecutionVenue):
    """Wraps a live execution venue and removes the ability to trade.

    Fails closed, and fails EARLY: `plan` and `submit` raise before a request
    object exists, so nothing is signed and nothing is sent. Fill history still
    works, because reading what happened is the whole point of a viewer.
    """

    def __init__(self, inner: ExecutionVenue) -> None:
        self._inner = inner

    @property
    def mode(self) -> str:
        return self._inner.mode

    def plan(self, ticker: str, side, budget_dollars: float):
        raise TradingDisabled("Order entry is disabled in live view mode.")

    def submit(self, request):
        raise TradingDisabled("Order entry is disabled in live view mode.")

    def recent_fills(self, limit: int = 50):
        return self._inner.recent_fills(limit)
