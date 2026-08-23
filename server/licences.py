"""Licence keys and the signed tokens FIRE actually trusts.

The key is what a customer sees and pastes. The token is what the application
verifies. Keeping them separate means a key can be short and readable while the
thing that grants access is unforgeable.
"""
from __future__ import annotations

import os
import secrets
import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fire.entitlement.token import TokenPayload, sign        # noqa: E402

# Ambiguous characters removed. A customer reading a key off a receipt should
# never have to guess between O and 0, or between I, l and 1.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
GROUPS, GROUP_LEN = 4, 5

GRACE_DAYS = int(os.environ.get("FIRE_GRACE_DAYS", "7"))


def new_key() -> str:
    """FIRE-XXXXX-XXXXX-XXXXX-XXXXX, roughly 98 bits of entropy."""
    body = "-".join(
        "".join(secrets.choice(ALPHABET) for _ in range(GROUP_LEN))
        for _ in range(GROUPS))
    return f"FIRE-{body}"


def normalise(key: str) -> str:
    """Accept what a human types: any case, any spacing, missing prefix."""
    cleaned = "".join(ch for ch in (key or "").upper()
                      if ch.isalnum())
    if cleaned.startswith("FIRE"):
        cleaned = cleaned[4:]
    if len(cleaned) != GROUPS * GROUP_LEN:
        return ""
    parts = [cleaned[i:i + GROUP_LEN]
             for i in range(0, len(cleaned), GROUP_LEN)]
    return "FIRE-" + "-".join(parts)


def private_key_pem() -> bytes:
    """The signing key, from the environment. Never from a file in the repo."""
    material = os.environ.get("FIRE_SIGNING_KEY", "")
    if not material:
        raise RuntimeError(
            "FIRE_SIGNING_KEY is not set. Generate a pair with "
            "python server/make_keys.py and put the private key in the "
            "service environment.")
    return material.replace("\\n", "\n").encode("utf-8")


def token_for(record: dict, install: str) -> str:
    """Mint a signed token describing this licence, for this install."""
    key = str(record.get("key", ""))
    payload = TokenPayload(
        status=str(record.get("status") or "active"),
        expires=record.get("expires"),
        plan=str(record.get("plan") or "FIRE"),
        install=install,
        key_tail=key[-4:] if key else "",
        issued=time.time(),
        grace_days=GRACE_DAYS,
    )
    return sign(payload, private_key_pem())


def trial_token(install: str, days: int = 14) -> str:
    """A trial is granted by the service, not assumed by the client."""
    payload = TokenPayload(
        status="trial", expires=time.time() + days * 86400, plan="Trial",
        install=install, issued=time.time(), grace_days=GRACE_DAYS)
    return sign(payload, private_key_pem())


def is_usable(record: Optional[dict]) -> bool:
    if not record:
        return False
    if record.get("status") != "active":
        return False
    expires = record.get("expires")
    return not (expires and time.time() > float(expires))
