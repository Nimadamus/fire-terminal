"""Single source of version truth for the app, the packager and update checks."""
from __future__ import annotations

# Release naming, so every artefact lines up:
#   VERSION        1.0.0            semantic, no suffix on a shipping build
#   git tag        v1.0.0
#   installer      FIRE-1.0.0-setup.exe
#   feed channel   BUILD_CHANNEL below
# Bump patch for fixes, minor for features, major for anything that changes
# how a customer works. The installer upgrades in place at every level.
VERSION = "1.0.0"
BUILD_CHANNEL = "dev"          # dev | beta | stable
UPDATE_FEED_URL = ""           # set when a release feed exists; empty disables checks

# Where a customer reaches a human. Empty is allowed on a dev build and is
# blocked at release, because a support bundle the customer cannot send
# anywhere is not support.
SUPPORT_EMAIL = ""
SUPPORT_URL = ""

# The licence service. Both must be set on a release build, otherwise FIRE
# falls back to a local trial and there is nothing to charge for.
# LICENCE_PUBLIC_KEY is the base64 raw Ed25519 public key printed by
# server/make_keys.py. The matching private key never leaves the server.
LICENCE_API_URL = ""
LICENCE_PUBLIC_KEY = ""


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
