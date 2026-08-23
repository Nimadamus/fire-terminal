"""Licensing boundary.

All subscription logic lives behind `EntitlementProvider`. The rest of the
application asks one question, `current()`, and reads the returned state. No
billing vocabulary (Stripe, invoice, price ID, webhook) appears anywhere above
this interface, so the billing backend can be swapped without touching the app.

Design note: entitlement gates LIVE trading only. Demo mode is always
available, including with no licence at all, because a customer who cannot
evaluate the product will not buy it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class EntitlementStatus(str, Enum):
    TRIAL = "trial"
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"
    UNLICENSED = "unlicensed"


@dataclass(frozen=True)
class Entitlement:
    status: EntitlementStatus
    expires_epoch: Optional[float] = None
    plan: str = ""
    seat_label: str = ""
    message: str = ""
    max_version: Optional[str] = None   # version entitlement, None = no ceiling

    @property
    def allows_live_trading(self) -> bool:
        return self.status in (EntitlementStatus.TRIAL, EntitlementStatus.ACTIVE)

    @property
    def allows_demo(self) -> bool:
        return self.status is not EntitlementStatus.REVOKED

    @property
    def is_warning(self) -> bool:
        return self.status in (EntitlementStatus.EXPIRED, EntitlementStatus.REVOKED)


class EntitlementProvider(ABC):
    """One question, one answer. Implementations may cache and must not block
    the UI thread for longer than `timeout_s`."""

    @abstractmethod
    def current(self) -> Entitlement: ...

    @abstractmethod
    def refresh(self, timeout_s: float = 5.0) -> Entitlement:
        """Re-check with the backend if there is one. Must degrade to the last
        known good answer rather than locking the customer out on a network
        blip."""

    @abstractmethod
    def redeem(self, licence_key: str) -> Entitlement:
        """Attach a licence to this installation."""
