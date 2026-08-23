"""Create the FIRE product, prices, coupon and webhook in a Stripe account.

Run this once against the new FIRE Stripe account, in test mode first. It is
idempotent: run it twice and it finds what it made the first time rather than
creating duplicates, which is the usual way a Stripe account ends up with three
products called FIRE.

    set STRIPE_SECRET_KEY=sk_test_...
    python server/setup_stripe.py --webhook https://<service>/stripe/webhook

It prints the four values that go in the service environment. Nothing is
written to disk, because two of those values are secrets.

Safety: the script refuses to touch an account whose business name is not FIRE
unless you pass --force. That guard exists because the obvious mistake is
running it with a key from an unrelated business's account and quietly adding a
trading product to it.
"""
from __future__ import annotations

import argparse
import os
import sys

PRODUCT_NAME = "FIRE"
PRODUCT_DESC = ("Execution terminal for short duration event contracts. "
                "Windows desktop application.")

PRICES = (
    ("monthly", 5900, "month", "FIRE Monthly"),
    ("annual", 59000, "year", "FIRE Annual"),
)

COUPON_ID = "fire-founding"
COUPON_PERCENT = 34.0
COUPON_REDEMPTIONS = 50

WEBHOOK_EVENTS = [
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.payment_failed",
]


def _find_product(stripe):
    for product in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        if product.name == PRODUCT_NAME:
            return product
    return None


def _find_price(stripe, product_id: str, amount: int, interval: str):
    for price in stripe.Price.list(product=product_id, limit=100,
                                   active=True).auto_paging_iter():
        recurring = price.get("recurring") or {}
        if price.unit_amount == amount and recurring.get("interval") == interval:
            return price
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--webhook", default="",
                    help="full URL of the service webhook endpoint")
    ap.add_argument("--force", action="store_true",
                    help="proceed even if this does not look like the FIRE account")
    args = ap.parse_args()

    key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not key:
        print("STRIPE_SECRET_KEY is not set.", file=sys.stderr)
        return 1

    import stripe
    stripe.api_key = key

    account = stripe.Account.retrieve()
    name = ((account.get("business_profile") or {}).get("name") or "").strip()
    live = not key.startswith("sk_test_")
    print(f"account : {account.get('id')}  ({name or 'unnamed'})")
    print(f"mode    : {'LIVE' if live else 'test'}")

    # The mistake this catches is real: running with a key from an unrelated
    # business and adding a financial product to their account.
    if PRODUCT_NAME.lower() not in name.lower() and not args.force:
        print(f"\nRefusing: this account is called {name!r}, not FIRE.\n"
              f"If that is genuinely the FIRE account, rerun with --force.",
              file=sys.stderr)
        return 2

    product = _find_product(stripe)
    if product is None:
        product = stripe.Product.create(name=PRODUCT_NAME,
                                        description=PRODUCT_DESC)
        print(f"created product {product.id}")
    else:
        print(f"found product   {product.id}")

    env: dict[str, str] = {}
    for slug, amount, interval, nickname in PRICES:
        price = _find_price(stripe, product.id, amount, interval)
        if price is None:
            price = stripe.Price.create(
                product=product.id, unit_amount=amount, currency="usd",
                recurring={"interval": interval}, nickname=nickname)
            print(f"created price   {price.id}  ${amount / 100:.0f}/{interval}")
        else:
            print(f"found price     {price.id}  ${amount / 100:.0f}/{interval}")
        env[f"STRIPE_PRICE_{slug.upper()}"] = price.id

    try:
        coupon = stripe.Coupon.retrieve(COUPON_ID)
        print(f"found coupon    {coupon.id}")
    except Exception:
        coupon = stripe.Coupon.create(
            id=COUPON_ID, percent_off=COUPON_PERCENT, duration="forever",
            name="Founding member")
        print(f"created coupon  {coupon.id}  {COUPON_PERCENT}% off, forever")

    existing_codes = [c for c in stripe.PromotionCode.list(limit=100).auto_paging_iter()
                      if c.code == "FOUNDING50"]
    if existing_codes:
        print(f"found promo     {existing_codes[0].code}")
    else:
        promo = stripe.PromotionCode.create(
            coupon=coupon.id, code="FOUNDING50",
            max_redemptions=COUPON_REDEMPTIONS)
        print(f"created promo   {promo.code}  {COUPON_REDEMPTIONS} redemptions")

    if args.webhook:
        endpoints = [e for e in stripe.WebhookEndpoint.list(limit=100).auto_paging_iter()
                     if e.url == args.webhook]
        if endpoints:
            stripe.WebhookEndpoint.modify(endpoints[0].id,
                                          enabled_events=WEBHOOK_EVENTS)
            print(f"updated webhook {endpoints[0].id}")
            print("  (its signing secret is only shown at creation; if you do "
                  "not have it, delete the endpoint and rerun)")
        else:
            hook = stripe.WebhookEndpoint.create(url=args.webhook,
                                                 enabled_events=WEBHOOK_EVENTS)
            env["STRIPE_WEBHOOK_SECRET"] = hook.secret
            print(f"created webhook {hook.id}")

    print("\n" + "=" * 66)
    print("Put these in the licence service environment:")
    print("=" * 66)
    for name_, value in env.items():
        print(f"{name_}={value}")
    if "STRIPE_WEBHOOK_SECRET" not in env and args.webhook:
        print("STRIPE_WEBHOOK_SECRET=<from the Stripe dashboard>")
    print(f"STRIPE_SECRET_KEY=<the {'live' if live else 'test'} key you used>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
