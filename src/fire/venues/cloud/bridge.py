"""Account reads for the laptop, taken from the machine that holds the key.

The trading key lives on the cloud box and stays there. This talks to a script
sitting beside it which accepts one word from a fixed list and returns JSON.
There is no URL parameter and no passthrough, so nothing here can be talked
into signing a request the bridge author did not write, and there is no order
path on either side of the link.

Transport is the management channel that already exists to that machine, so no
new port is opened and nothing new is exposed to the internet. It is slow, a
second or two per call, which is why everything the viewer needs arrives in one
`state` round trip on a lazy timer rather than three calls on a fast one.

Owner tooling. Never part of a customer build: `--view` is the only thing that
constructs it, and a customer build has no cloud box to point at.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

HOST = "3.224.38.193"
REMOTE_PYTHON = "C:/Program Files/Python310/python.exe"
REMOTE_SCRIPT = "C:/stage/firebridge/bridge.py"
VAULT = Path("C:/Users/BL/CREDENTIALS.md")

# Anything not in here is not askable. The bridge enforces the same list on its
# own side; this one exists so a mistake here fails before the network.
ALLOWED = ("state", "balance", "positions", "fills")

REFRESH_SECONDS = 6.0


class CloudBridge:
    """One cached view of the account, refreshed on a background thread."""

    def __init__(self, refresh_seconds: float = REFRESH_SECONDS) -> None:
        self._refresh = max(3.0, refresh_seconds)
        self._lock = threading.RLock()
        self._state: dict[str, Any] = {}
        self._fetched_at = 0.0
        self._reachable = False
        self._session = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    # -- connection --------------------------------------------------------
    def _connect(self):
        if self._session is not None:
            return self._session
        import winrm
        text = VAULT.read_text(encoding="utf-8", errors="ignore")
        block = text[text.index(HOST):]
        password = re.search(r"password: `([^`]+)`", block).group(1)
        self._session = winrm.Session(f"http://{HOST}:5985/wsman",
                                      auth=("Administrator", password),
                                      transport="ntlm")
        return self._session

    def _call(self, what: str) -> dict:
        if what not in ALLOWED:
            raise ValueError(f"{what!r} is not a permitted bridge call")
        session = self._connect()
        result = session.run_ps(
            f"& '{REMOTE_PYTHON}' '{REMOTE_SCRIPT}' {what}")
        if result.status_code != 0:
            return {}
        try:
            return json.loads(result.std_out.decode("utf-8", "replace"))
        except Exception:
            return {}

    # -- lifecycle ---------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="fire-bridge",
                                        daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                fresh = self._call("state")
                if fresh:
                    with self._lock:
                        self._state = fresh
                        self._fetched_at = time.time()
                        self._reachable = True
                else:
                    self._reachable = False
            except Exception as exc:
                self._reachable = False
                log.info("bridge unreachable: %s", type(exc).__name__)
            self._stop.wait(self._refresh)

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=3.0)

    # -- reading -----------------------------------------------------------
    @property
    def reachable(self) -> bool:
        return self._reachable

    @property
    def stale(self) -> bool:
        """True when the last good answer is old enough to be worth flagging."""
        with self._lock:
            if not self._fetched_at:
                return True
            return (time.time() - self._fetched_at) > self._refresh * 3

    def section(self, name: str) -> dict:
        with self._lock:
            value = self._state.get(name) or {}
        return value if isinstance(value, dict) else {}
