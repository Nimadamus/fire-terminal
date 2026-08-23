"""HTTP transport: pacing, backoff and error translation.

Conduct rules this file exists to satisfy, all of which appear on the launch
checklist as requirements the exchange expects of a well behaved application:

  * a hard client side request rate ceiling, so a customer cannot become a
    problem for the venue no matter what they click
  * exponential backoff with jitter on retryable failures, never an immediate
    retry and never a retry storm
  * a bounded retry count, because a persistent error means a bug, not a
    reason to keep hammering
  * degrade rather than fail: when limited, slow down and keep the last good
    value on screen

Nothing here knows about strategy, valuation or order selection. It moves
bytes and translates failures into `FireError` types the UI can render.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Any, Optional

from fire.core.errors import (
    ConnectionLost, CredentialsInvalid, ExchangeNotConfigured,
    MarketUnavailable, RateLimited,
)
from fire.venues.kalshi.auth import RequestSigner
from fire.venues.kalshi.endpoints import EndpointProfile

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BASE_BACKOFF_S = 0.5
MAX_BACKOFF_S = 8.0
REQUEST_TIMEOUT_S = 8.0


class RateGate:
    """Token bucket. Blocks the caller rather than dropping the request."""

    def __init__(self, per_second: float) -> None:
        self._min_interval = 1.0 / max(0.1, per_second)
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            if now < self._next_allowed:
                time.sleep(self._next_allowed - now)
                now = time.monotonic()
            self._next_allowed = now + self._min_interval


class Transport:
    """One authenticated HTTP client against one endpoint profile."""

    def __init__(self, profile: EndpointProfile,
                 signer: Optional[RequestSigner] = None) -> None:
        if not profile.configured:
            raise ExchangeNotConfigured(
                "No approved exchange endpoint is configured in this build."
            )
        self._profile = profile
        self._signer = signer
        self._gate = RateGate(profile.max_requests_per_second)
        self._degraded = False
        self._session = self._new_session()

    @staticmethod
    def _new_session():
        import requests
        s = requests.Session()
        s.headers.update({"User-Agent": "FIRE-terminal"})
        return s

    @property
    def degraded(self) -> bool:
        """True while the venue is pushing back. Callers should poll slower."""
        return self._degraded

    def get(self, key: str, **fmt: Any) -> dict:
        return self._request("GET", key, None, **fmt)

    def post(self, key: str, body: dict, **fmt: Any) -> dict:
        return self._request("POST", key, body, **fmt)

    # -- internals ---------------------------------------------------------
    def _request(self, method: str, key: str, body: Optional[dict],
                 **fmt: Any) -> dict:
        url = self._profile.url(key, **fmt)
        signing_path = self._profile.signing_path(key, **fmt)
        last_error: Optional[Exception] = None

        for attempt in range(MAX_ATTEMPTS):
            self._gate.wait()
            try:
                # No signer means public endpoints only, which is what a
                # viewer install has: markets and order books need no
                # credential, and this machine deliberately holds none.
                headers = (self._signer.headers(method, signing_path)
                           if self._signer is not None
                           else {"Content-Type": "application/json"})
                response = self._session.request(
                    method, url, headers=headers, json=body,
                    timeout=REQUEST_TIMEOUT_S)
            except Exception as exc:
                last_error = exc
                self._sleep_backoff(attempt)
                continue

            status = response.status_code

            if 200 <= status < 300:
                self._degraded = False
                try:
                    return response.json()
                except ValueError:
                    return {}

            if status in (401, 403):
                raise CredentialsInvalid(
                    "The exchange rejected this key for that request.")
            if status == 404:
                raise MarketUnavailable("That market is not available.")
            if status == 429 or 500 <= status < 600:
                self._degraded = True
                # never log a response body: it can echo request headers
                log.warning("venue returned %s, backing off (attempt %d)",
                            status, attempt + 1)
                self._sleep_backoff(attempt)
                last_error = RuntimeError(f"status {status}")
                continue

            raise ConnectionLost(f"Unexpected response from the exchange ({status}).")

        if self._degraded:
            raise RateLimited("The exchange is limiting requests.")
        raise ConnectionLost("Could not reach the exchange.") from last_error

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        delay = min(MAX_BACKOFF_S, BASE_BACKOFF_S * (2 ** attempt))
        time.sleep(delay * (0.5 + random.random() * 0.5))   # jitter
