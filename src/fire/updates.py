"""Update checking.

Two rules that matter more than the mechanism:

  * an update check must never block startup or the UI. It runs on a daemon
    thread and a failure is silent, because a customer who cannot reach our
    release feed still has a working terminal.
  * the check sends nothing about the customer. It is a plain GET for a small
    JSON document. No install id, no telemetry, no account identifier.

The feed is unset in this build (`UPDATE_FEED_URL` is empty), so checking is
disabled and `check()` returns None immediately.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from fire.version import BUILD_CHANNEL, UPDATE_FEED_URL, VERSION, is_newer

log = logging.getLogger(__name__)

TIMEOUT_S = 6.0


@dataclass(frozen=True)
class Release:
    version: str
    url: str = ""
    notes: str = ""
    mandatory: bool = False

    @property
    def is_newer(self) -> bool:
        return is_newer(self.version, VERSION)


def check(feed_url: str = UPDATE_FEED_URL) -> Optional[Release]:
    """Synchronous check. Returns None when disabled, unreachable or current."""
    if not feed_url:
        return None
    try:
        import requests
        response = requests.get(feed_url, timeout=TIMEOUT_S,
                                headers={"User-Agent": "FIRE-terminal"})
        if response.status_code != 200:
            return None
        data = response.json()
    except Exception as exc:
        log.info("update check skipped: %s", type(exc).__name__)
        return None

    channel = data.get(BUILD_CHANNEL) or data.get("stable") or {}
    version = str(channel.get("version") or "")
    if not version:
        return None
    release = Release(version=version, url=str(channel.get("url") or ""),
                      notes=str(channel.get("notes") or ""),
                      mandatory=bool(channel.get("mandatory")))
    return release if release.is_newer else None


def check_in_background(on_update: Callable[[Release], None],
                        feed_url: str = UPDATE_FEED_URL) -> None:
    """Fire and forget. `on_update` is only called if something newer exists."""
    if not feed_url:
        return

    def _run() -> None:
        release = check(feed_url)
        if release is not None:
            try:
                on_update(release)
            except Exception:
                pass

    threading.Thread(target=_run, daemon=True, name="update-check").start()


def parse_feed(text: str) -> dict:
    """Exposed for tests and for validating a feed document before publishing."""
    return json.loads(text)
