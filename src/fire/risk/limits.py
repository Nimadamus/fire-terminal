"""Customer risk limits.

Written from scratch rather than ported. The internal version enforces a fixed
house fraction across multiple concurrent runners sharing one account, which is
a problem a customer does not have and whose implementation reveals how our own
sizing works. This is the simple, honest version: one ceiling, one account,
configurable by the person whose money it is.

Definition used throughout: for a binary contract bought at `price` dollars,
the maximum possible loss is the full purchase cost, because the contract can
settle at zero. So max loss equals cost including fees.
"""
from __future__ import annotations

from dataclasses import dataclass

from fire.core.errors import RiskLimitExceeded
from fire.core.models import OrderRequest


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    max_loss_dollars: float
    ceiling_dollars: float
    reason: str = ""

    @property
    def headroom_dollars(self) -> float:
        return max(0.0, self.ceiling_dollars - self.max_loss_dollars)


class RiskLimiter:
    """Evaluated immediately before submit, on every order, in both modes."""

    def __init__(self, fraction: float = 0.10, enabled: bool = True) -> None:
        self.fraction = min(1.0, max(0.005, float(fraction)))
        self.enabled = bool(enabled)

    def ceiling(self, balance_dollars: float) -> float:
        return round(max(0.0, balance_dollars) * self.fraction, 2)

    def evaluate(self, request: OrderRequest, balance_dollars: float,
                 fee_dollars: float = 0.0) -> RiskDecision:
        max_loss = round(request.count * request.limit_price + fee_dollars, 2)
        ceiling = self.ceiling(balance_dollars)

        if not self.enabled:
            return RiskDecision(True, max_loss, ceiling, "Risk limit is turned off.")
        if max_loss <= ceiling:
            return RiskDecision(True, max_loss, ceiling)
        return RiskDecision(
            False, max_loss, ceiling,
            f"This order risks ${max_loss:,.2f}, above your ${ceiling:,.2f} limit "
            f"({self.fraction:.0%} of a ${balance_dollars:,.2f} balance).",
        )

    def enforce(self, request: OrderRequest, balance_dollars: float,
                fee_dollars: float = 0.0) -> RiskDecision:
        decision = self.evaluate(request, balance_dollars, fee_dollars)
        if not decision.allowed:
            raise RiskLimitExceeded(decision.reason)
        return decision

    def largest_affordable_stake(self, balance_dollars: float) -> float:
        """What the 'Max' button should offer."""
        return self.ceiling(balance_dollars) if self.enabled else max(0.0, balance_dollars)
