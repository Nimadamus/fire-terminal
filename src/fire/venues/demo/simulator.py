"""Deterministic market simulator for Demo mode.

NO NETWORK. This module must never import requests, urllib3, websocket or
socket. `tests/test_demo_isolation.py` enforces that.

--------------------------------------------------------------------------
A NOTE ON THE PRICING USED HERE, WHICH IS DELIBERATE
--------------------------------------------------------------------------
The book below is generated from a plain terminal price model: the chance the
index finishes past the strike, treated as a single endpoint of a random walk.

That is the naive, textbook form. It is not how these contracts actually
settle, and anyone who reverse engineers this file learns nothing except
first year probability. That is the point. Demo mode has to look and feel
like a real market without carrying a single line of real analysis.
--------------------------------------------------------------------------
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field

from fire.core.models import Book, BookLevel, IndexQuote, Instrument

WINDOW_SECONDS = 15 * 60


@dataclass(frozen=True)
class DemoCoin:
    code: str
    display: str
    start_price: float
    daily_vol: float          # rough annualised-ish wiggle, presentation only
    decimals: int


DEMO_COINS: tuple[DemoCoin, ...] = (
    DemoCoin("BTC",  "Bitcoin",   77_100.00, 0.34, 2),
    DemoCoin("ETH",  "Ethereum",   2_418.00, 0.45, 2),
    DemoCoin("SOL",  "Solana",        94.81, 0.62, 2),
    DemoCoin("XRP",  "XRP",           1.4846, 0.58, 4),
    DemoCoin("DOGE", "Dogecoin",      0.09203, 0.72, 5),
    DemoCoin("BNB",  "BNB",         694.75, 0.40, 2),
    DemoCoin("HYPE", "Hyperliquid",  79.6082, 0.80, 4),
    DemoCoin("NEAR", "NEAR",          1.879, 0.66, 3),
    DemoCoin("ADA",  "Cardano",       0.2238, 0.61, 4),
    DemoCoin("BCH",  "Bitcoin Cash", 512.40, 0.44, 2),
    DemoCoin("LTC",  "Litecoin",      88.15, 0.47, 2),
    DemoCoin("TON",  "Toncoin",        3.412, 0.63, 3),
)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


@dataclass
class _CoinState:
    coin: DemoCoin
    price: float
    strike: float
    window_start: float
    seed: int
    _rng: random.Random = field(init=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    @property
    def window_end(self) -> float:
        return self.window_start + WINDOW_SECONDS

    def step(self, now: float, dt: float) -> None:
        """One diffusion step. Deterministic per seed so demo replays sensibly."""
        sigma_per_s = self.coin.daily_vol / math.sqrt(365 * 24 * 3600)
        shock = self._rng.gauss(0.0, 1.0) * sigma_per_s * math.sqrt(max(dt, 0.001))
        self.price = max(1e-9, self.price * (1.0 + shock))
        if now >= self.window_end:
            self.roll(now)

    def roll(self, now: float) -> None:
        """Open the next 15 minute window, strike near the current price."""
        self.window_start = now - (now % WINDOW_SECONDS)
        drift = self._rng.uniform(-0.0016, 0.0016)
        self.strike = round(self.price * (1.0 + drift), self.coin.decimals)

    # -- presentation-only probability, see module docstring -----------------
    def _p_above_strike(self, now: float) -> float:
        left = max(1.0, self.window_end - now)
        sigma_per_s = self.coin.daily_vol / math.sqrt(365 * 24 * 3600)
        sd = self.price * sigma_per_s * math.sqrt(left)
        if sd <= 0:
            return 1.0 if self.price > self.strike else 0.0
        return _norm_cdf((self.price - self.strike) / sd)

    def instrument(self, now: float) -> Instrument:
        stamp = time.strftime("%d%b%y%H%M", time.gmtime(self.window_end)).upper()
        return Instrument(
            ticker=f"DEMO-{self.coin.code}15M-{stamp}",
            series=f"DEMO{self.coin.code}15M",
            display=self.coin.code,
            strike=self.strike,
            close_epoch=self.window_end,
        )

    def book(self, now: float) -> Book:
        p_yes = min(0.995, max(0.005, self._p_above_strike(now)))
        # a spread that tightens as the window closes, like a real book does
        left_frac = max(0.0, (self.window_end - now) / WINDOW_SECONDS)
        spread = 0.004 + 0.026 * left_frac

        def ladder(mid: float) -> tuple[BookLevel, ...]:
            out = []
            for i in range(4):
                px = min(0.99, max(0.01, round(mid + spread * (0.5 + i * 0.6), 4)))
                size = int(140 / (i + 1)) + self._rng.randint(0, 45)
                out.append(BookLevel(price=px, size=max(1, size)))
            return tuple(out)

        return Book(yes=ladder(p_yes), no=ladder(1.0 - p_yes), received_epoch=now)

    def index_quote(self, now: float) -> IndexQuote:
        return IndexQuote(
            index_id=f"DEMO.{self.coin.code}",
            value=round(self.price, self.coin.decimals),
            received_epoch=now,
            source="Demo simulator",
        )


class MarketSimulator:
    """Drives all demo coins forward. Single threaded, cheap, no I/O."""

    def __init__(self, seed: int = 20260822) -> None:
        base = time.time()
        self._states: dict[str, _CoinState] = {}
        for i, coin in enumerate(DEMO_COINS):
            st = _CoinState(
                coin=coin, price=coin.start_price, strike=coin.start_price,
                window_start=base - (base % WINDOW_SECONDS), seed=seed + i * 7919,
            )
            st.roll(base)
            self._states[coin.code] = st
        self._last = base

    def tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        dt = max(0.0, now - self._last)
        self._last = now
        for st in self._states.values():
            st.step(now, dt)

    def codes(self) -> tuple[str, ...]:
        return tuple(self._states)

    def state(self, code: str) -> _CoinState:
        return self._states[code]

    def by_ticker(self, ticker: str, now: float) -> _CoinState | None:
        for st in self._states.values():
            if st.instrument(now).ticker == ticker:
                return st
        return None
