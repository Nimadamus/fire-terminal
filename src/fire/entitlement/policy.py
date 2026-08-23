"""What a given subscription state permits, in one place.

The rule is deliberately not "entitlement gates live trading" alone. Demo has
its own gate, because REVOKED has to mean something: if a revoked installation
could still place simulated orders forever, revocation would be decoration.
Every other state leaves demo open, since a customer who cannot evaluate the
product will not buy it.

This is a pure function on purpose. The UI, the session and the tests all ask
the same question and get the same answer, and none of them re-implement it.
"""
from __future__ import annotations

from typing import Optional

from fire.interfaces.entitlement import Entitlement, EntitlementStatus
from fire.interfaces.venue import VenueMode


def trading_allowed(mode: str, ent: Optional[Entitlement]) -> bool:
    """May the customer send orders right now, in this mode?"""
    if ent is None:
        return True                      # no provider wired: nothing to enforce
    if mode == VenueMode.LIVE:
        return ent.allows_live_trading
    return ent.allows_demo


def suspension_reason(mode: str, ent: Optional[Entitlement]) -> str:
    """Plain words for why order entry is switched off, aimed at the customer.

    Never say "entitlement", never name a status code, and always say what is
    still true: their money and their real positions are untouched.
    """
    if trading_allowed(mode, ent) or ent is None:
        return ""
    if ent.status is EntitlementStatus.REVOKED:
        return ("Access to this installation was withdrawn, so FIRE will not "
                "send orders. Your exchange account is unaffected. Send us a "
                "support bundle from Diagnostics if this looks wrong.")
    if ent.status is EntitlementStatus.EXPIRED:
        return ("Your subscription has ended, so FIRE will not send orders. "
                "Nothing has been closed and nothing has been sold: any "
                "positions you hold are still open at the exchange. Renew to "
                "start trading again, or switch to demo mode.")
    return ("FIRE needs an active subscription to send orders. Demo mode is "
            "available without one.")


def short_suspension_reason(mode: str, ent: Optional[Entitlement]) -> str:
    """The same fact in a few words, for places with no room to explain.

    A card is 268px wide and its height is fixed, so anything that wraps to a
    second line is clipped and the customer reads half a message. That is worse
    than saying little, so these stay on one line and the bar across the top
    carries the explanation.
    """
    if trading_allowed(mode, ent) or ent is None:
        return ""
    if ent.status is EntitlementStatus.REVOKED:
        return "Trading is switched off."
    if ent.status is EntitlementStatus.EXPIRED:
        return "Subscription ended."
    return "Subscription needed."
