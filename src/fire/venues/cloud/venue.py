"""The viewer venue: public prices direct, account through the cloud bridge.

Market data needs no credential, so it is fetched straight from the exchange
and stays fast. Balance, positions and fills come from the machine that holds
the key, over the bridge.

There is no execution venue here at all. Not a disabled one, not a guarded one:
the object that could place an order is never constructed, so the only thing
this venue can do with the exchange is read.
"""
from __future__ import annotations

import time
from typing import Optional, Sequence

from fire.core.errors import TradingDisabled
from fire.core.models import (
    AccountSnapshot, Fill, Position, Side,
)
from fire.interfaces.venue import (
    AccountAdapter, ExecutionVenue, MarketDataSource, Venue, VenueMode,
)
from fire.core.models import IndexQuote
from fire.venues.cloud.bridge import CloudBridge
from fire.venues.cloud.spot import SpotFeed


def _cents(value) -> float:
    try:
        return float(value) / 100.0
    except Exception:
        return 0.0


class CloudAccount(AccountAdapter):
    def __init__(self, bridge: CloudBridge) -> None:
        self._b = bridge

    @property
    def mode(self) -> str:
        return VenueMode.LIVE

    def refresh(self) -> None:
        pass                    # the bridge refreshes itself on its own thread

    def snapshot(self) -> AccountSnapshot:
        balance = self._b.section("balance")
        positions_raw = self._b.section("positions")

        positions: list[Position] = []
        for entry in positions_raw.get("market_positions", []):
            count = int(entry.get("position") or 0)
            if not count:
                continue
            # Kalshi signs the side into the position count: negative is NO.
            side = Side.YES if count > 0 else Side.NO
            exposure = abs(_cents(entry.get("market_exposure") or 0))
            size = abs(count)
            positions.append(Position(
                ticker=str(entry.get("ticker") or ""),
                side=side,
                count=size,
                average_price=(exposure / size) if size else 0.0,
            ))

        return AccountSnapshot(
            balance_dollars=_cents(balance.get("balance")),
            positions=positions,
            resting_orders=0,
            updated_epoch=time.time(),
            stale=self._b.stale,
        )


class CloudFills(ExecutionVenue):
    """Fill history only. plan and submit exist to refuse, loudly and early."""

    def __init__(self, bridge: CloudBridge) -> None:
        self._b = bridge

    @property
    def mode(self) -> str:
        return VenueMode.LIVE

    def plan(self, ticker: str, side, budget_dollars: float):
        raise TradingDisabled("This installation cannot place orders.")

    def submit(self, request):
        raise TradingDisabled("This installation cannot place orders.")

    def recent_fills(self, limit: int = 50) -> Sequence[Fill]:
        raw = self._b.section("fills").get("fills", [])
        out: list[Fill] = []
        for entry in raw[:limit]:
            try:
                # This API reports the outcome as `outcome_side` and prices in
                # dollars as strings, with the size in `count_fp`. Reading the
                # names from an older shape silently produced zero everywhere.
                side = (Side.NO if str(entry.get("outcome_side", "")).lower() == "no"
                        else Side.YES)
                price = float(entry.get("yes_price_dollars") if side is Side.YES
                              else entry.get("no_price_dollars") or 0)
                out.append(Fill(
                    ticker=str(entry.get("market_ticker") or entry.get("ticker") or ""),
                    side=side,
                    count=int(round(float(entry.get("count_fp") or 0))),
                    price=price,
                    fee_dollars=float(entry.get("fee_cost") or 0),
                    epoch=_parse_time(str(entry.get("created_time") or "")),
                    order_id=str(entry.get("fill_id") or entry.get("order_id") or ""),
                ))
            except Exception:
                continue
        return out


def _parse_time(stamp: str) -> float:
    if not stamp:
        return time.time()
    try:
        from datetime import datetime
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    except Exception:
        return time.time()


class SpotMarketData(MarketDataSource):
    """The exchange's markets and books, with the underlying price added.

    Kalshi publishes the contract; the INDEX line is the thing it settles
    against, which comes from the spot feed.
    """

    def __init__(self, inner: MarketDataSource, spot: SpotFeed) -> None:
        self._inner = inner
        self._spot = spot

    @property
    def mode(self) -> str:
        return self._inner.mode

    def connection_state(self):
        return self._inner.connection_state()

    def instruments(self):
        return self._inner.instruments()

    def book(self, ticker: str):
        return self._inner.book(ticker)

    def index_quote(self, index_id: str):
        price = self._spot.price(index_id)
        if price is None:
            return None
        return IndexQuote(index_id=index_id, value=price,
                          received_epoch=time.time(), source="coinbase")

    def start(self) -> None:
        self._spot.start()
        self._inner.start()

    def stop(self) -> None:
        self._spot.stop()
        if hasattr(self._inner, "stop"):
            self._inner.stop()


class ViewVenue(Venue):
    """Live prices, live account, no order path."""

    display_name = "Kalshi (view only)"
    read_only = True

    def __init__(self, market_data: MarketDataSource, bridge: CloudBridge) -> None:
        self._md = market_data
        self._bridge = bridge
        self._account = CloudAccount(bridge)
        self._fills = CloudFills(bridge)

    @property
    def mode(self) -> str:
        return VenueMode.LIVE

    @property
    def market_data(self) -> MarketDataSource:
        return self._md

    @property
    def execution(self) -> ExecutionVenue:
        return self._fills

    @property
    def account(self) -> AccountAdapter:
        return self._account

    def connect(self) -> None:
        self._bridge.start()
        self._md.start()

    def disconnect(self) -> None:
        self._bridge.stop()
        if hasattr(self._md, "stop"):
            self._md.stop()


def build_view_venue() -> Venue:
    """Public market data plus the cloud bridge. No credential on this machine."""
    from fire.venues.kalshi import endpoints
    from fire.venues.kalshi.transport import Transport
    from fire.venues.kalshi.venue import LiveMarketData

    if not endpoints.is_configured():
        from fire.core.errors import ExchangeNotConfigured
        raise ExchangeNotConfigured("Live view is not enabled in this build.")

    # No signer: markets and order books are public, and this machine holds no
    # key to sign with, which is the entire point.
    transport = Transport(endpoints.ACTIVE, signer=None)
    market_data = SpotMarketData(LiveMarketData(transport, endpoints.ACTIVE),
                                 SpotFeed())
    return ViewVenue(market_data, CloudBridge())
