"""Offline-first entitlement provider.

This is the ONLY implementation today and it deliberately talks to nothing.
It gives a new install a real trial so the product can be evaluated, stores
the result locally, and exposes exactly the interface a billing backend will
later satisfy.

When Stripe (or anything else) is wired up, write a `RemoteEntitlement`
implementing the same interface and change one line in `app.py`. Nothing else
in the application knows what billing is.

Anti-goal: this is not copy protection. A local licence file is trivially
editable and pretending otherwise would be theatre. It exists to answer
"what should the UI show this customer" and to give billing a clean seam.
Real enforcement, if we ever want it, has to be server side.
"""
from __future__ import annotations

import json
import time

from fire.config.paths import entitlement_file
from fire.interfaces.entitlement import (
    Entitlement, EntitlementProvider, EntitlementStatus,
)

TRIAL_DAYS = 14


class LocalEntitlement(EntitlementProvider):
    def __init__(self) -> None:
        self._cached: Entitlement | None = None

    # -- persistence -------------------------------------------------------
    def _read(self) -> dict:
        path = entitlement_file()
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write(self, data: dict) -> None:
        tmp = entitlement_file().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(entitlement_file())

    # -- interface ---------------------------------------------------------
    def current(self) -> Entitlement:
        if self._cached is not None:
            return self._cached
        data = self._read()
        now = time.time()

        if not data:
            data = {"status": "trial", "started": now,
                    "expires": now + TRIAL_DAYS * 86400, "plan": "Trial"}
            self._write(data)

        status = str(data.get("status", "trial"))
        expires = data.get("expires")

        if status == "revoked":
            ent = Entitlement(EntitlementStatus.REVOKED, expires, data.get("plan", ""),
                              message="This installation's access was revoked.")
        elif expires and now > float(expires):
            was_trial = status == "trial"
            ent = Entitlement(
                EntitlementStatus.EXPIRED, expires, data.get("plan", ""),
                message=("Your trial has ended." if was_trial
                         else "Your subscription has lapsed."),
            )
        elif status == "active":
            ent = Entitlement(EntitlementStatus.ACTIVE, expires, data.get("plan", "FIRE"),
                              seat_label=data.get("seat", ""))
        elif status == "trial":
            days = max(0, int((float(expires) - now) / 86400)) if expires else 0
            ent = Entitlement(EntitlementStatus.TRIAL, expires, "Trial",
                              message=f"{days} day{'s' if days != 1 else ''} left in your trial.")
        else:
            ent = Entitlement(EntitlementStatus.UNLICENSED, None, "",
                              message="No licence found on this installation.")

        self._cached = ent
        return ent

    def refresh(self, timeout_s: float = 5.0) -> Entitlement:
        self._cached = None
        return self.current()

    def redeem(self, licence_key: str) -> Entitlement:
        key = (licence_key or "").strip()
        if len(key) < 8:
            return Entitlement(EntitlementStatus.UNLICENSED, None, "",
                               message="That licence key does not look right.")
        # No backend yet: record the key and mark active for a year. Replaced
        # wholesale by the remote provider when billing is connected.
        now = time.time()
        self._write({"status": "active", "started": now, "expires": now + 365 * 86400,
                     "plan": "FIRE", "key_tail": key[-4:]})
        self._cached = None
        return self.current()
