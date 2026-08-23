"""One place that configures the Stripe SDK.

Pinning the API version is the point. Stripe moves its default forward and the
shapes change underneath you: this integration was written against an API where
a promotion code took a `coupon` parameter, and by the time it ran the default
had become a nested `promotion` object, so the call failed with "unknown
parameter" against code that had been correct when written.

Pinned, upgrades become something we choose and test. Unpinned, they arrive on
Stripe's schedule and are discovered by a customer.
"""
from __future__ import annotations

import os

# Verified against this version. Change it deliberately, then re run
# tests/qa_presale.py and server/setup_stripe.py before shipping.
API_VERSION = "2026-07-29.dahlia"

# Seconds. Bounded on the HTTP client, NOT passed to the call: `timeout=` given
# to a resource method is sent to Stripe as a query parameter and comes back as
# 400 parameter_unknown, which is how the subscription lookup silently failed
# on the first real purchase.
TIMEOUT_S = float(os.environ.get("FIRE_STRIPE_TIMEOUT", "8"))


def configure(api_key: str = ""):
    """Return the stripe module, configured. Never logs or returns the key."""
    import stripe
    stripe.api_key = api_key or os.environ.get("STRIPE_SECRET_KEY", "")
    stripe.api_version = API_VERSION
    stripe.max_network_retries = 1
    try:
        stripe.default_http_client = stripe.RequestsClient(timeout=TIMEOUT_S)
    except Exception:
        pass          # an unbounded default is worse than ideal, not fatal
    return stripe
