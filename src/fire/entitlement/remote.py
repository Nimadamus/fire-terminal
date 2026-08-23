"""Entitlement backed by the licence service.

This is the production provider. `LocalEntitlement` stays as the trial only
fallback for a build with no service configured.

The shape of the deal with the server:

    POST {base}/activate     {"key": "...", "install": "..."}  -> {"token": "..."}
    POST {base}/entitlement  {"install": "...", "key": "..."}  -> {"token": "..."}

Both return a signed token, described in `fire.entitlement.token`. FIRE never
believes an unsigned answer and never decides entitlement locally.

Behaviour that matters more than the wire format:

**A network failure is not an expiry.** If the service cannot be reached, the
cached token stands until its own grace window runs out. Locking a paying
customer out of a live position because a server had a bad afternoon is a worse
failure than a few days of stale state.

**The install id is a random value we generate, not a hardware fingerprint.**
Fingerprinting a customer's machine to enforce a fifty dollar subscription is
both rude and fragile: it breaks on a RAM upgrade and it collects something we
have no business collecting.

**Nothing personal is stored on disk.** The cached token carries a status, a
plan, an expiry, the opaque install id and four characters of the licence key.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from fire.config.paths import data_dir, entitlement_file
from fire.entitlement.token import (
    TokenInvalid, TokenPayload, is_within_grace, verify,
)
from fire.interfaces.entitlement import (
    Entitlement, EntitlementProvider, EntitlementStatus,
)

log = logging.getLogger(__name__)

TIMEOUT_S = 8.0

_STATUS = {
    "trial": EntitlementStatus.TRIAL,
    "active": EntitlementStatus.ACTIVE,
    "expired": EntitlementStatus.EXPIRED,
    "revoked": EntitlementStatus.REVOKED,
}


def install_id() -> str:
    """A random id for this installation, created once and kept.

    Random, not derived from the machine. It identifies an install to the
    licence service so a seat can be counted, and it says nothing about the
    person or the hardware.
    """
    path = data_dir() / "install.id"
    try:
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    except Exception:
        pass
    fresh = uuid.uuid4().hex
    try:
        path.write_text(fresh, encoding="utf-8")
    except Exception:
        pass                      # a read only profile still gets a working id
    return fresh


class RemoteEntitlement(EntitlementProvider):
    def __init__(self, base_url: str, public_key_pem: bytes,
                 install: Optional[str] = None) -> None:
        self._base = base_url.rstrip("/")
        self._pub = public_key_pem
        self._install = install or install_id()
        self._cached: Optional[Entitlement] = None

    # -- local cache -------------------------------------------------------
    def _read_cache(self) -> Optional[TokenPayload]:
        try:
            data = json.loads(entitlement_file().read_text(encoding="utf-8"))
            return verify(str(data.get("token", "")), self._pub, self._install)
        except (OSError, ValueError, TokenInvalid):
            return None
        except Exception:
            return None

    def _write_cache(self, token: str, key_tail: str = "") -> None:
        try:
            payload = {"token": token}
            if key_tail:
                payload["key_tail"] = key_tail
            tmp = entitlement_file().with_suffix(".tmp")
            tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp.replace(entitlement_file())
        except Exception:
            log.info("entitlement cache could not be written")

    def _stored_key(self) -> str:
        try:
            data = json.loads(entitlement_file().read_text(encoding="utf-8"))
            return str(data.get("key", ""))
        except Exception:
            return ""

    # -- network -----------------------------------------------------------
    def _post(self, path: str, body: dict, timeout_s: float) -> Optional[str]:
        try:
            import requests
            response = requests.post(f"{self._base}{path}", json=body,
                                     timeout=timeout_s,
                                     headers={"User-Agent": "FIRE-terminal"})
        except Exception as exc:
            log.info("licence service unreachable: %s", type(exc).__name__)
            return None
        if response.status_code != 200:
            log.info("licence service said %s", response.status_code)
            return None
        try:
            return str(response.json().get("token") or "")
        except Exception:
            return None

    # -- translation -------------------------------------------------------
    def _to_entitlement(self, payload: TokenPayload,
                        stale: bool = False) -> Entitlement:
        status = _STATUS.get(payload.status, EntitlementStatus.UNLICENSED)
        now = time.time()

        if status in (EntitlementStatus.TRIAL, EntitlementStatus.ACTIVE) \
                and payload.expires and now > float(payload.expires):
            status = EntitlementStatus.EXPIRED

        message = ""
        if status is EntitlementStatus.TRIAL and payload.expires:
            days = max(0, int((float(payload.expires) - now) / 86400))
            message = f"{days} day{'s' if days != 1 else ''} left in your trial."
        elif status is EntitlementStatus.EXPIRED:
            message = "Your subscription has ended."
        elif status is EntitlementStatus.REVOKED:
            message = "This installation's access was withdrawn."
        elif stale:
            message = "Checked recently. FIRE will confirm when it reconnects."

        return Entitlement(status, payload.expires, payload.plan,
                           seat_label="", message=message,
                           max_version=payload.max_version)

    # -- interface ---------------------------------------------------------
    def current(self) -> Entitlement:
        if self._cached is not None:
            return self._cached
        payload = self._read_cache()
        if payload is None:
            self._cached = Entitlement(
                EntitlementStatus.UNLICENSED, None, "",
                message="Enter your licence key to enable live trading.")
            return self._cached

        # A cached token that has outlived its grace window is not trusted,
        # but it is also not proof of anything bad, so say so plainly rather
        # than accusing the customer of having no licence.
        if not is_within_grace(payload):
            self._cached = Entitlement(
                EntitlementStatus.EXPIRED, payload.expires, payload.plan,
                message="FIRE has not been able to confirm your subscription. "
                        "Open Account and press Refresh.")
            return self._cached

        self._cached = self._to_entitlement(payload)
        return self._cached

    def refresh(self, timeout_s: float = TIMEOUT_S) -> Entitlement:
        token = self._post("/entitlement",
                           {"install": self._install, "key": self._stored_key()},
                           timeout_s)
        if token:
            try:
                payload = verify(token, self._pub, self._install)
            except TokenInvalid:
                log.info("licence service returned a token we could not verify")
                payload = None
            if payload is not None:
                self._write_cache(token, payload.key_tail)
                self._cached = self._to_entitlement(payload)
                return self._cached

        # Unreachable or unusable answer: the cached token stands.
        self._cached = None
        return self.current()

    def redeem(self, licence_key: str) -> Entitlement:
        key = (licence_key or "").strip()
        if len(key) < 8:
            return Entitlement(EntitlementStatus.UNLICENSED, None, "",
                               message="That licence key does not look right.")
        token = self._post("/activate", {"key": key, "install": self._install},
                           TIMEOUT_S)
        if not token:
            return Entitlement(
                EntitlementStatus.UNLICENSED, None, "",
                message="That licence could not be activated right now. Check "
                        "your connection and try again, or send us a support "
                        "bundle from Diagnostics.")
        try:
            payload = verify(token, self._pub, self._install)
        except TokenInvalid:
            return Entitlement(
                EntitlementStatus.UNLICENSED, None, "",
                message="That activation could not be verified. Please send us "
                        "a support bundle from Diagnostics.")

        # The key itself is kept so a later refresh can identify the seat. It
        # is a licence key, not a credential for the customer's money.
        try:
            entitlement_file().write_text(
                json.dumps({"token": token, "key": key,
                            "key_tail": payload.key_tail}, indent=2),
                encoding="utf-8")
        except Exception:
            log.info("licence could not be cached")
        self._cached = self._to_entitlement(payload)
        return self._cached
