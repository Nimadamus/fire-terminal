"""Single source of version truth for the app, the packager and update checks."""
from __future__ import annotations

VERSION = "1.0.0-dev"
BUILD_CHANNEL = "dev"          # dev | beta | stable
UPDATE_FEED_URL = ""           # set when a release feed exists; empty disables checks

# Where a customer reaches a human. Empty is allowed on a dev build and is
# blocked at release, because a support bundle the customer cannot send
# anywhere is not support.
SUPPORT_EMAIL = ""
SUPPORT_URL = ""


def support_contact() -> str:
    """One line telling the customer where to send a support bundle."""
    if SUPPORT_EMAIL and SUPPORT_URL:
        return f"{SUPPORT_EMAIL}  or  {SUPPORT_URL}"
    return SUPPORT_EMAIL or SUPPORT_URL


def is_release_build() -> bool:
    return BUILD_CHANNEL in ("beta", "stable")


def as_tuple(v: str = VERSION) -> tuple[int, ...]:
    core = v.split("-", 1)[0]
    return tuple(int(x) for x in core.split(".") if x.isdigit())


def is_newer(candidate: str, current: str = VERSION) -> bool:
    return as_tuple(candidate) > as_tuple(current)
