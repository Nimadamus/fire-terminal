"""Live venue adapter. NOT YET IMPLEMENTED.

Deliberately a stub. The build order is demo first, then migrate the safe
market data and execution behaviour across from the audited internal panels.
Everything that lands here must satisfy these rules:

  * credentials arrive as an argument, from `CredentialStore`. This package
    never reads a file path, an environment variable or a bundled key.
  * no module in this package imports anything from the private bot.
  * the wire format stops here. Callers above receive `fire.core.models` types
    only, never a raw exchange payload.
  * every order is immediate or cancel. FIRE never rests an order on the book.
  * `mode` is the constant VenueMode.LIVE, never computed, so `Session` can
    detect a wiring mistake before an order is sent.

Only execution mechanics may be migrated here: order ladder walking, best ask
selection, fee arithmetic and immediate or cancel planning. Anything that
decides WHETHER to trade, or what a contract is worth, is out of scope for
this repository in whole and in part.
"""
from __future__ import annotations

from fire.config.credentials import CredentialStore
from fire.interfaces.venue import Venue


def build_live_venue(store: CredentialStore) -> Venue:
    raise NotImplementedError(
        "The live exchange adapter is not part of this build yet. "
        "FIRE is running in demo mode."
    )
