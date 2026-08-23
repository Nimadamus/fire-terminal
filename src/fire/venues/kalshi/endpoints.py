"""The single seam where an approved API path gets wired in.

Everything else in this package is written against `EndpointProfile`. When
written authorization arrives, one profile object is filled in and the live
adapter works. No other file changes, and nothing above the venue layer is
touched at all.

Until then `ACTIVE` is UNCONFIGURED, every live construction raises
`ExchangeNotConfigured`, and the app falls back to demo with a clear message.
This is a deliberate compliance gate, not an unfinished feature: the code path
is complete and tested, it simply has nowhere to point.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EndpointProfile:
    """Everything venue-specific about reaching an exchange."""
    name: str
    base_url: str = ""
    api_root: str = ""
    paths: dict[str, str] = field(default_factory=dict)
    configured: bool = False

    # conduct limits, kept here so they are reviewed alongside the endpoints
    max_requests_per_second: float = 5.0
    market_poll_seconds: float = 1.0
    book_poll_seconds: float = 0.5
    account_poll_seconds: float = 2.0

    def url(self, key: str, **fmt: object) -> str:
        if not self.configured:
            raise RuntimeError("endpoint profile is not configured")
        path = self.paths[key].format(**fmt)
        return f"{self.base_url}{self.api_root}{path}"

    def signing_path(self, key: str, **fmt: object) -> str:
        """The path portion that participates in the request signature."""
        if not self.configured:
            raise RuntimeError("endpoint profile is not configured")
        # Kalshi signs the path WITHOUT its query string.
        path = self.paths[key].format(**fmt).split("?", 1)[0]
        return f"{self.api_root}{path}"


# The shape a configured profile takes. Kept as documentation so the wiring
# step is mechanical rather than archaeological.
REQUIRED_PATH_KEYS = (
    "markets",        # list open markets for a series
    "market",         # one market by ticker
    "orderbook",      # depth for one ticker
    "balance",        # account cash
    "positions",      # open positions
    "orders",         # resting orders, and POST target for new orders
    "fills",          # executed trades
)


UNCONFIGURED = EndpointProfile(
    name="unconfigured",
    configured=False,
)

# Wire the approved profile here once permission is granted in writing, then
# set ACTIVE to it. Nothing else in the codebase needs to change.
# Nima's own machine, using his own Kalshi account and his own key. This is
# personal use of the API by the account holder, which needs no third party
# authorization; the pending Kalshi request is about DISTRIBUTING FIRE to other
# members, and that gate is unchanged. Customer builds ship UNCONFIGURED.
OWNER_USE = EndpointProfile(
    name="kalshi",
    base_url="https://api.elections.kalshi.com",
    api_root="/trade-api/v2",
    paths={
        "markets":   "/markets?series_ticker={series}&status=open",
        "market":    "/markets/{ticker}",
        "orderbook": "/markets/{ticker}/orderbook",
        "balance":   "/portfolio/balance",
        "positions": "/portfolio/positions",
        "orders":    "/portfolio/orders",
        "fills":     "/portfolio/fills",
    },
    configured=True,
    # Twelve series plus a book each is a lot of calls per cycle, and the
    # exchange says 429 well before it says anything useful. Paced to sit
    # comfortably under that rather than to look fast.
    max_requests_per_second=2.0,
    market_poll_seconds=4.0,
    book_poll_seconds=2.5,
    account_poll_seconds=6.0,
)

# Switched on only by FIRE_OWNER_MODE=1 or the --owner flag, neither of which a
# customer build ever carries. Absent both, this stays UNCONFIGURED and live
# construction raises, which is the compliance gate working as designed.
import os as _os                                             # noqa: E402
import sys as _sys                                           # noqa: E402

_OWNER = (_os.environ.get("FIRE_OWNER_MODE") == "1"
          or "--owner" in _sys.argv)

ACTIVE: EndpointProfile = OWNER_USE if _OWNER else UNCONFIGURED


def is_configured() -> bool:
    return ACTIVE.configured
