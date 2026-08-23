"""Watches subscription state so the customer learns from the interface.

A subscription can lapse while the terminal is sitting open. Without this, the
first sign is a rejected order at the moment someone clicks BUY, which is the
worst possible time to find out and reads as a broken product rather than an
expired card.

Three rules shape the design:

  * The check runs off the UI thread. A remote provider will do network I/O,
    and a frozen window during a routine licence check is unacceptable.
  * A failed check never downgrades anyone. If the provider raises, we keep the
    last known good answer. Losing access because the wifi dropped is worse
    than a few minutes of stale state.
  * Transitions are reported once, not once per poll, so the UI is not fighting
    a banner that reappears every fifteen minutes.

Nothing here touches tkinter. The thread only records what it found; the UI
drains it on its own tick, which keeps every widget call on the main thread.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Optional

from fire.interfaces.entitlement import Entitlement, EntitlementProvider

DEFAULT_INTERVAL_S = 900.0          # fifteen minutes


@dataclass(frozen=True)
class Transition:
    previous: Entitlement
    current: Entitlement

    @property
    def live_trading_lost(self) -> bool:
        return self.previous.allows_live_trading and not self.current.allows_live_trading

    @property
    def live_trading_regained(self) -> bool:
        return not self.previous.allows_live_trading and self.current.allows_live_trading


class EntitlementWatch:
    def __init__(self, provider: EntitlementProvider,
                 interval_s: float = DEFAULT_INTERVAL_S) -> None:
        self._provider = provider
        self._interval = max(5.0, float(interval_s))
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._latest: Entitlement = provider.current()
        self._pending: Optional[Transition] = None

    # -- reading -----------------------------------------------------------
    def latest(self) -> Entitlement:
        with self._lock:
            return self._latest

    def take_transition(self) -> Optional[Transition]:
        """Called from the UI thread. Returns a change at most once."""
        with self._lock:
            t, self._pending = self._pending, None
            return t

    # -- checking ----------------------------------------------------------
    def poll_once(self) -> Optional[Transition]:
        """One check. Safe to call from any thread; never raises."""
        try:
            fresh = self._provider.refresh()
        except Exception:
            return None                  # keep the last good answer
        if fresh is None:
            return None
        with self._lock:
            previous = self._latest
            if fresh.status is previous.status:
                self._latest = fresh     # same state, keep dates fresh, no event
                return None
            self._latest = fresh
            transition = Transition(previous, fresh)
            self._pending = transition
            return transition

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="fire-entitlement",
                                        daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        # Wait first: current() was already read in __init__, so an immediate
        # poll would only duplicate it.
        while not self._stop.wait(self._interval):
            self.poll_once()

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
