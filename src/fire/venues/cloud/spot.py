"""Spot prices for the INDEX line.

The exchange publishes the contract, not the underlying it settles against, so
the index has to come from somewhere else. Coinbase is the reference most of
these markets quote, and it answers without a credential.

It refuses a request with no User-Agent, which is why one is set: the first
attempt returned 403 and looked like a blocked endpoint rather than a missing
header.

Failure is silent and the card simply shows no index rather than an error. A
missing spot price is a cosmetic gap; a dialog about it is not.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Optional

PRODUCT = "https://api.exchange.coinbase.com/products/{pair}/ticker"
HEADERS = {"User-Agent": "FIRE-terminal"}
REFRESH = 2.0

# Card name to Coinbase product.
PAIRS = {
    "BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD", "XRP": "XRP-USD",
    "DOGE": "DOGE-USD", "BNB": "BNB-USD", "HYPE": "HYPE-USD",
    "NEAR": "NEAR-USD", "ADA": "ADA-USD", "BCH": "BCH-USD",
    "LTC": "LTC-USD", "AVAX": "AVAX-USD",
}


class SpotFeed:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._prices: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="fire-spot",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=3.0)

    def _loop(self) -> None:
        while not self._stop.is_set():
            for coin, pair in PAIRS.items():
                if self._stop.is_set():
                    return
                try:
                    req = urllib.request.Request(PRODUCT.format(pair=pair),
                                                 headers=HEADERS)
                    with urllib.request.urlopen(req, timeout=6) as r:
                        price = float(json.load(r)["price"])
                    with self._lock:
                        self._prices[coin] = price
                except Exception:
                    continue
            self._stop.wait(REFRESH)

    def price(self, coin: str) -> Optional[float]:
        with self._lock:
            return self._prices.get(coin)
