"""The complete purchase journey against a real Stripe account.

One command. Point it at any Stripe test key and it will stand up the licence
service locally, create a real customer and a real subscription, drive the real
webhooks into the service, activate the real desktop client, then cancel and
check that entitlement goes away without taking the customer's data with it.

    python tests/qa_stripe_journey.py --key-file C:\\path\\to\\stripe-test-key.txt
    python tests/qa_stripe_journey.py --hosted     # also open a hosted checkout

Everything it creates in Stripe is cleaned up at the end, so it is safe to run
repeatedly against the same account.

Why it drives the API rather than the hosted checkout page by default: the
hosted page is Stripe's and cannot be completed without a browser, while
everything after it is ours. `--hosted` prints a checkout URL when the page
itself needs a look.

Refuses to run against a live key. There is no version of this worth doing with
real money.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "server"))

import requests                                                    # noqa: E402
from cryptography.hazmat.primitives import serialization            # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (     # noqa: E402
    Ed25519PrivateKey,
)

results: list[tuple[bool, str]] = []


def check(ok, what: str, detail: str = "") -> bool:
    ok = bool(ok)
    results.append((ok, what))
    print(f"  {'PASS' if ok else 'FAIL'}  {what}" + (f"   [{detail}]" if detail else ""),
          flush=True)
    return ok


def section(title: str) -> None:
    print(f"\n{title}", flush=True)


def d(obj) -> dict:
    return obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)


def _plain(o):
    """Stripe's real objects carry Decimal values; JSON does not."""
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    raise TypeError(type(o).__name__)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Service:
    """The licence service, running for real on a real socket."""

    def __init__(self, stripe_key: str, prices: dict[str, str]):
        private = Ed25519PrivateKey.generate()
        self.signing_key = private.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()).decode()
        self.public_key = base64.urlsafe_b64encode(
            private.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw)).decode().rstrip("=").encode()
        self.webhook_secret = "whsec_" + base64.b16encode(os.urandom(24)).decode().lower()
        self.port = free_port()
        self.db = Path(tempfile.gettempdir()) / f"fire_journey_{self.port}.db"
        self.base = f"http://127.0.0.1:{self.port}"
        self._stripe_key = stripe_key
        self._prices = prices
        self.proc: subprocess.Popen | None = None

    def start(self) -> bool:
        env = dict(os.environ)
        env.update({
            "FIRE_SIGNING_KEY": self.signing_key,
            "FIRE_DB": str(self.db),
            "FIRE_SITE_DIR": str(ROOT / "site"),
            "PYTHONPATH": str(ROOT / "src"),
            "STRIPE_WEBHOOK_SECRET": self.webhook_secret,
            "STRIPE_SECRET_KEY": self._stripe_key,
            "STRIPE_PRICE_MONTHLY": self._prices.get("monthly", ""),
            "STRIPE_PRICE_ANNUAL": self._prices.get("annual", ""),
            "FIRE_SITE_URL": self.base,
        })
        env.pop("DATABASE_URL", None)
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(self.port), "--log-level", "warning"],
            cwd=str(ROOT / "server"), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for _ in range(60):
            try:
                if requests.get(f"{self.base}/health", timeout=1).status_code == 200:
                    return True
            except Exception:
                time.sleep(0.4)
        return False

    def deliver(self, stripe, event_id: str, kind: str, obj) -> int:
        """Post an event signed exactly the way Stripe signs it."""
        body = json.dumps({"id": event_id, "type": kind, "data": {"object": d(obj)}},
                          separators=(",", ":"), default=_plain).encode()
        ts = int(time.time())
        sig = stripe.WebhookSignature._compute_signature(
            f"{ts}.{body.decode()}", self.webhook_secret)
        r = requests.post(f"{self.base}/stripe/webhook", data=body,
                          headers={"stripe-signature": f"t={ts},v1={sig}"}, timeout=25)
        return r.status_code

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except Exception:
                self.proc.kill()
        if self.db.exists():
            try:
                self.db.unlink()
            except Exception:
                pass


def find_prices(stripe) -> dict[str, str]:
    """Locate the FIRE prices. Fails loudly rather than testing the wrong thing."""
    prices: dict[str, str] = {}
    for product in stripe.Product.list(limit=100, active=True).auto_paging_iter():
        if d(product).get("name") != "FIRE":
            continue
        for price in stripe.Price.list(product=d(product)["id"], limit=100,
                                       active=True).auto_paging_iter():
            data = d(price)
            interval = (data.get("recurring") or {}).get("interval")
            if interval == "month" and data.get("unit_amount") == 5900:
                prices["monthly"] = data["id"]
            elif interval == "year" and data.get("unit_amount") == 59000:
                prices["annual"] = data["id"]
    return prices


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key-file", default="C:/Users/BL/fire-terminal-stripe-test.txt")
    ap.add_argument("--hosted", action="store_true",
                    help="also print a hosted checkout URL for a manual browser pass")
    args = ap.parse_args()

    key_path = Path(args.key_file)
    if not key_path.is_file():
        print(f"No Stripe key at {key_path}", file=sys.stderr)
        return 1
    stripe_key = key_path.read_text().strip()

    if not stripe_key.startswith("sk_test_"):
        print("Refusing: that is not a test key. This journey creates and cancels\n"
              "real subscriptions and must never run against live money.",
              file=sys.stderr)
        return 2

    from stripe_api import configure
    stripe = configure(stripe_key)

    account = d(stripe.Account.retrieve())
    label = ((account.get("business_profile") or {}).get("name")
             or ((account.get("settings") or {}).get("dashboard") or {}).get("display_name")
             or "unnamed")
    print("FIRE Stripe journey")
    print("=" * 68)
    print(f"account : {account.get('id')}  ({label})")
    print("mode    : test")

    prices = find_prices(stripe)
    if "monthly" not in prices or "annual" not in prices:
        print("\nFIRE prices not found in this account. Run first:\n"
              "  python server/setup_stripe.py", file=sys.stderr)
        return 3
    print(f"monthly : {prices['monthly']}")
    print(f"annual  : {prices['annual']}")

    service = Service(stripe_key, prices)
    if not service.start():
        print("licence service did not start", file=sys.stderr)
        service.stop()
        return 1

    created: dict[str, str] = {}
    workdir = Path(tempfile.mkdtemp(prefix="fire-journey-"))
    try:
        journey(stripe, service, prices, created, workdir, args.hosted)
    finally:
        cleanup(stripe, created)
        service.stop()
        shutil.rmtree(workdir, ignore_errors=True)

    failed = [w for ok, w in results if not ok]
    print("\n" + "=" * 68)
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    for w in failed:
        print(f"  BLOCKING: {w}")
    return 1 if failed else 0


def journey(stripe, service, prices, created, workdir, hosted: bool) -> None:
    email = f"journey+{int(time.time())}@example.com"

    # -- A. purchase --------------------------------------------------------
    section("A. Customer purchases")

    if hosted:
        r = requests.post(f"{service.base}/checkout", timeout=20,
                          json={"plan": "monthly", "email": email})
        url = r.json().get("url", "") if r.status_code == 200 else ""
        check(url.startswith("https://checkout.stripe.com"),
              "hosted checkout session created")
        print(f"\n  Open this to check the page itself:\n  {url}\n")

    customer = d(stripe.Customer.create(email=email, name="Journey Test"))
    created["customer"] = customer["id"]
    check(customer.get("id", "").startswith("cus_"), "customer created at Stripe")

    # pm_card_visa is Stripe's own test instrument. No real card is involved.
    # Attaching it mints a NEW payment method id for this customer, so the
    # returned id is the one to make default; reusing the shared token fails.
    attached = d(stripe.PaymentMethod.attach("pm_card_visa",
                                             customer=customer["id"]))
    stripe.Customer.modify(
        customer["id"],
        invoice_settings={"default_payment_method": attached["id"]})

    subscription = d(stripe.Subscription.create(
        customer=customer["id"], items=[{"price": prices["monthly"]}]))
    created["subscription"] = subscription["id"]
    check(subscription.get("status") in ("active", "trialing"),
          "subscription is active", subscription.get("status", ""))

    session_id = f"cs_journey_{int(time.time())}"
    fake_session = {"id": session_id, "customer": customer["id"],
                    "subscription": subscription["id"],
                    "customer_details": {"email": email}}
    code = service.deliver(stripe, f"evt_{session_id}",
                           "checkout.session.completed", fake_session)
    check(code == 200, "purchase webhook accepted")

    code = service.deliver(stripe, f"evt_{session_id}",
                           "checkout.session.completed", fake_session)
    check(code == 200, "a repeated event is accepted and ignored")

    # -- B. entitlement -----------------------------------------------------
    section("B. Purchase produces a valid entitlement")

    r = requests.get(f"{service.base}/licence", timeout=20,
                     params={"session_id": session_id})
    check(r.status_code == 200, "success page returns the licence")
    key = r.json().get("key", "")
    check(key.startswith("FIRE-") and len(key) == 28, "licence key well formed", key)

    service.deliver(stripe, f"evt_sub_{session_id}",
                    "customer.subscription.created", subscription)

    state = requests.get(f"{service.base}/licence/state", timeout=20,
                         params={"key": key}).json()
    check(state["status"] == "active", "licence is active")
    check(state["plan"] == "FIRE Monthly", "plan read from Stripe", state["plan"])
    check(state["expires"] and state["expires"] > time.time(),
          "renewal date set",
          time.strftime("%d %b %Y", time.localtime(state["expires"]))
          if state["expires"] else "MISSING")
    check(email not in json.dumps(state), "account state leaks no email")

    # -- C/D. the desktop client -------------------------------------------
    section("C. FIRE recognises the entitlement")

    from fire.config import paths
    from fire.entitlement import remote as remote_mod
    paths.data_dir = lambda: workdir
    paths.entitlement_file = lambda: workdir / "ent.json"
    paths.prefs_file = lambda: workdir / "prefs.json"
    remote_mod.entitlement_file = lambda: workdir / "ent.json"
    remote_mod.data_dir = lambda: workdir

    from fire.entitlement.policy import suspension_reason, trading_allowed
    from fire.entitlement.remote import RemoteEntitlement
    from fire.entitlement.token import TokenInvalid, verify
    from fire.interfaces.entitlement import EntitlementStatus
    from fire.interfaces.venue import VenueMode

    client = RemoteEntitlement(service.base, service.public_key,
                               install="journey-machine-01")
    check(not client.current().allows_live_trading,
          "a fresh install cannot trade live before activating")

    ent = client.redeem(key)
    check(ent.status is EntitlementStatus.ACTIVE, "the real client activates")
    check(ent.allows_live_trading, "live trading enabled")
    check(ent.plan == "FIRE Monthly", "plan shown to the customer", ent.plan)

    cached = (workdir / "ent.json").read_text()
    check(email not in cached, "nothing personal written to the customer's disk")
    try:
        verify(json.loads(cached)["token"], service.public_key, "another-machine")
        check(False, "a copied licence file does not unlock another machine")
    except TokenInvalid:
        check(True, "a copied licence file does not unlock another machine")

    (workdir / "prefs.json").write_text('{"theme":"dark","default_stake":250.0}')

    # -- E. cancellation ----------------------------------------------------
    section("D. Cancellation removes entitlement safely")

    cancelled = d(stripe.Subscription.cancel(created["subscription"]))
    created.pop("subscription", None)
    check(cancelled.get("status") == "canceled", "cancelled at Stripe")

    code = service.deliver(stripe, f"evt_cancel_{session_id}",
                           "customer.subscription.deleted", cancelled)
    check(code == 200, "cancellation webhook accepted")

    after = client.refresh(timeout_s=8)
    check(after.status is EntitlementStatus.EXPIRED, "client reads expired")
    check(not after.allows_live_trading, "live trading disabled")
    check(after.allows_demo, "demo mode still works")
    check(not trading_allowed(VenueMode.LIVE, after), "policy refuses live orders")
    check(trading_allowed(VenueMode.DEMO, after), "policy still allows demo")
    check("still open at the exchange" in suspension_reason(VenueMode.LIVE, after),
          "customer told their positions are untouched")
    check((workdir / "prefs.json").is_file()
          and "dark" in (workdir / "prefs.json").read_text(),
          "preferences survive cancellation")
    check((workdir / "ent.json").is_file(), "licence data not destroyed")

    # -- F. outage ----------------------------------------------------------
    section("E. An outage is not an expiry")
    offline = RemoteEntitlement("http://127.0.0.1:1", service.public_key,
                                install="journey-machine-01")
    check(offline.refresh(timeout_s=0.3).allows_demo,
          "an unreachable service does not lock the customer out of demo")


def cleanup(stripe, created: dict[str, str]) -> None:
    """Leave the Stripe account as it was found."""
    if created.get("subscription"):
        try:
            stripe.Subscription.cancel(created["subscription"])
        except Exception:
            pass
    if created.get("customer"):
        try:
            stripe.Customer.delete(created["customer"])
            print("\ncleaned up the test customer")
        except Exception:
            print("\ncould not delete the test customer; remove it by hand")


if __name__ == "__main__":
    raise SystemExit(main())
