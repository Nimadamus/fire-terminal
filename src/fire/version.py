"""Single source of version truth for the app, the packager and update checks."""
from __future__ import annotations

VERSION = "1.0.0-dev"
BUILD_CHANNEL = "dev"          # dev | beta | stable
UPDATE_FEED_URL = ""           # set when a release feed exists; empty disables checks


def as_tuple(v: str = VERSION) -> tuple[int, ...]:
    core = v.split("-", 1)[0]
    return tuple(int(x) for x in core.split(".") if x.isdigit())


def is_newer(candidate: str, current: str = VERSION) -> bool:
    return as_tuple(candidate) > as_tuple(current)
