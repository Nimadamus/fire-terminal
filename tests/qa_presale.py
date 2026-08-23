"""Pre sale audit: the five things that must hold before we take money.

    A. a customer can purchase
    B. the purchase produces a valid entitlement
    C. the customer can install
    D. FIRE recognises the entitlement
    E. expiry and cancellation disable live trading without destroying data
       and without silently switching modes

Everything here runs against the real service over a real socket, with a real
Stripe signed webhook, and drives the real desktop client code rather than a
stand in. The only part not exercised is Stripe's own hosted checkout page,
which we cannot reach without a Stripe account; the event it sends afterwards
is reproduced exactly, signature and all.

    python tests/qa_presale.py [--installer dist/installer/FIRE-1.0.0-setup.exe]
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests                                                   # noqa: E402
import stripe                                                     # noqa: E402
from cryptography.hazmat.primitives import serialization           # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (    # noqa: E402
    Ed25519PrivateKey,
)

WEBHOOK_SECRET = "whsec_" + "presale_audit_secret_do_not_use_live"

results: list[tuple[bool, str, str]] = []


def check(ok: bool, what: str, detail: str = "") -> bool:
    ok = bool(ok)
    results.append((ok, what, detail))
    mark = "PASS" if ok else "FAIL"
    print(f"  {mark}  {what}" + (f"   [{detail}]" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n{title}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def stripe_signed(payload: dict) -> tuple[bytes, str]:
    """A webhook body and header Stripe's own verifier will accept.

    Built with stripe's signing helper rather than by hand, so if their scheme
    changes this test fails rather than quietly proving nothing.
    """
    body = json.dumps(payload, separators=(",", ":")).encode()
    timestamp = int(time.time())
    signature = stripe.WebhookSignature._compute_signature(
        f"{timestamp}.{body.decode()}", WEBHOOK_SECRET)
    return body, f"t={timestamp},v1={signature}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--installer", default="")
    args = ap.parse_args()

    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode("ascii")
    public = base64.urlsafe_b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)).decode("ascii").rstrip("=")

    port = free_port()
    db = Path(tempfile.gettempdir()) / "fire_presale.db"
    if db.exists():
        db.unlink()

    os.environ["FIRE_DB"] = str(db)
    os.environ.pop("DATABASE_URL", None)

    env = dict(os.environ)
    env.update({
        "FIRE_SIGNING_KEY": pem,
        "FIRE_DB": str(db),
        "FIRE_SITE_DIR": str(ROOT / "site"),
        "PYTHONPATH": str(ROOT / "src"),
        "STRIPE_WEBHOOK_SECRET": WEBHOOK_SECRET,
        # No API key on purpose: this proves the webhook still issues a licence
        # when Stripe's API is unreachable, which is the failure that would
        # otherwise take a paying customer's money and give them nothing.
        "STRIPE_SECRET_KEY": "",
    })

    print("FIRE pre sale audit")
    print("=" * 68)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=str(ROOT / "server"), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                if requests.get(f"{base}/health", timeout=1).status_code == 200:
                    break
            except Exception:
                time.sleep(0.4)
        else:
            proc.kill()
            print("service never started:\n" + (proc.stdout.read() if proc.stdout else ""))
            return 1

        audit(base, public.encode("ascii"), args.installer)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        if db.exists():
            db.unlink()

    print("\n" + "=" * 68)
    failed = [r for r in results if not r[0]]
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        print("\nBLOCKING:")
        for _, what, _ in failed:
            print(f"  - {what}")
    return 1 if failed else 0


def audit(base: str, public: bytes, installer: str) -> None:
    from fire.entitlement.token import TokenInvalid, verify

    session_id = "cs_test_presale_0001"
    sub_id = "sub_test_presale_0001"
    email = "first.customer@example.com"

    # -- A. the customer purchases -----------------------------------------
    section("A. Customer can purchase")

    body, header = stripe_signed({
        "id": "evt_presale_0001",
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": session_id,
            "customer": "cus_test_presale",
            "subscription": sub_id,
            "customer_details": {"email": email},
        }},
    })
    r = requests.post(f"{base}/stripe/webhook", data=body,
                      headers={"stripe-signature": header}, timeout=10)
    check(r.status_code == 200, "Stripe webhook accepted with a valid signature")

    forged, _ = stripe_signed({"id": "evt_x", "type": "checkout.session.completed",
                               "data": {"object": {}}})
    r = requests.post(f"{base}/stripe/webhook", data=forged,
                      headers={"stripe-signature": "t=1,v1=deadbeef"}, timeout=10)
    check(r.status_code == 400, "a forged signature is refused")

    r = requests.post(f"{base}/stripe/webhook", data=body,
                      headers={"stripe-signature": header}, timeout=10)
    check(r.status_code == 200 and r.json().get("duplicate") is True,
          "a repeated event does not issue a second licence")

    # -- B. the purchase produces an entitlement ---------------------------
    section("B. Customer gets a valid entitlement")

    r = requests.get(f"{base}/licence", params={"session_id": session_id}, timeout=10)
    check(r.status_code == 200, "success page returns the licence")
    licence_key = r.json().get("key", "")
    check(licence_key.startswith("FIRE-") and len(licence_key) == 28,
          "licence key is well formed", licence_key)
    check(r.json().get("email") == email, "licence is tied to the buyer's email")

    body_paid = json.loads(body)
    check("first.customer" not in licence_key, "the key reveals nothing about the buyer")

    # -- C. install --------------------------------------------------------
    section("C. Customer can install")

    if installer:
        path = Path(installer)
        check(path.is_file(), f"installer exists", path.name)
        if path.is_file():
            size_mb = path.stat().st_size / (1024 * 1024)
            check(2 < size_mb < 200, "installer is a plausible size",
                  f"{size_mb:.1f} MB")
    else:
        bundle = ROOT / "dist" / "FIRE" / "FIRE.exe"
        check(bundle.is_file(), "built application present", str(bundle.name))

    for shipped in ("CREDENTIALS.md", "TROUBLESHOOTING.md", "LICENSE.txt"):
        found = list((ROOT / "dist" / "FIRE").glob(f"**/docs/{shipped}"))
        check(bool(found), f"{shipped} ships with the build")

    # -- D. FIRE recognises the entitlement --------------------------------
    section("D. FIRE recognises the entitlement")

    from fire.entitlement.remote import RemoteEntitlement
    from fire.interfaces.entitlement import EntitlementStatus

    workdir = Path(tempfile.mkdtemp(prefix="fire-presale-"))
    try:
        _redirect_client_paths(workdir)

        provider = RemoteEntitlement(base, public, install="presale-install-01")
        before = provider.current()
        check(not before.allows_live_trading,
              "a fresh install cannot trade live before activating")

        activated = provider.redeem(licence_key)
        check(activated.status is EntitlementStatus.ACTIVE,
              "the real client activates with the key from the purchase")
        check(activated.allows_live_trading, "and live trading is enabled")
        check(activated.plan.startswith("FIRE"), "plan is shown", activated.plan)

        cached = (workdir / "ent.json").read_text(encoding="utf-8")
        check(email not in cached, "nothing personal is written to the customer's disk")
        payload = verify(json.loads(cached)["token"], public, "presale-install-01")
        check(payload.status == "active", "the cached token verifies against our key")

        other = RemoteEntitlement(base, public, install="a-different-machine")
        try:
            verify(json.loads(cached)["token"], public, "a-different-machine")
            check(False, "a copied licence file does not unlock another machine")
        except TokenInvalid:
            check(True, "a copied licence file does not unlock another machine")

        # The whole gate, through the real session object the UI uses.
        _check_session_gate(provider, activated)

        # -- E. cancellation ------------------------------------------------
        section("E. Cancellation disables live trading safely")

        _cancel(base, sub_id)

        after = provider.refresh(timeout_s=5)
        check(after.status is EntitlementStatus.EXPIRED,
              "after cancellation the client reads expired")
        check(not after.allows_live_trading, "live trading is disabled")
        check(after.allows_demo, "demo mode still works")

        from fire.entitlement.policy import (
            short_suspension_reason, suspension_reason, trading_allowed,
        )
        from fire.interfaces.venue import VenueMode
        check(not trading_allowed(VenueMode.LIVE, after),
              "the policy refuses live order entry")
        check(trading_allowed(VenueMode.DEMO, after),
              "the policy still allows demo")
        reason = suspension_reason(VenueMode.LIVE, after)
        check("still open at the exchange" in reason,
              "the customer is told their positions are untouched")
        check(len(short_suspension_reason(VenueMode.LIVE, after)) <= 28,
              "the card message fits on one line")

        check((workdir / "ent.json").is_file(),
              "customer data is not destroyed by expiry")
        prefs = workdir / "prefs.json"
        prefs.write_text('{"theme":"dark"}', encoding="utf-8")
        provider.refresh(timeout_s=5)
        check(prefs.is_file() and "dark" in prefs.read_text(encoding="utf-8"),
              "preferences survive an entitlement change")

        _check_no_silent_mode_switch()

        # renewal puts it back
        _reactivate(base, sub_id)
        renewed = provider.refresh(timeout_s=5)
        check(renewed.allows_live_trading,
              "renewing restores live trading without a reinstall")

        # -- outage --------------------------------------------------------
        section("F. An outage is not an expiry")
        offline = RemoteEntitlement("http://127.0.0.1:1", public,
                                    install="presale-install-01")
        stale = offline.refresh(timeout_s=0.3)
        check(stale.allows_live_trading,
              "a paying customer keeps trading when our service is unreachable")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _redirect_client_paths(workdir: Path) -> None:
    """Point the client's storage at a scratch directory, not the real profile."""
    from fire.config import paths
    from fire.entitlement import remote as remote_mod
    paths.data_dir = lambda: workdir                      # type: ignore[assignment]
    paths.entitlement_file = lambda: workdir / "ent.json"  # type: ignore[assignment]
    paths.prefs_file = lambda: workdir / "prefs.json"      # type: ignore[assignment]
    remote_mod.entitlement_file = lambda: workdir / "ent.json"
    remote_mod.data_dir = lambda: workdir


def _check_session_gate(provider, entitlement) -> None:
    """The Session is the actual gate. The UI is only convenience."""
    from fire.core.errors import EntitlementRequired
    from fire.core.session import Session
    from fire.interfaces.venue import VenueMode

    class _Part:
        def __init__(self, mode):
            self.mode = mode

        def recent_fills(self, limit=50):
            return []

    class _Venue:
        display_name = "Audit"
        mode = VenueMode.LIVE

        def __init__(self):
            self.market_data = _Part(VenueMode.LIVE)
            self.execution = _Part(VenueMode.LIVE)
            self.account = _Part(VenueMode.LIVE)

        def connect(self):
            pass

        def disconnect(self):
            pass

    session = Session(_Venue(), VenueMode.LIVE, provider)
    try:
        check(session.execution is not None,
              "an active subscription passes the live execution gate")
    except EntitlementRequired:
        check(False, "an active subscription passes the live execution gate")


def _check_no_silent_mode_switch() -> None:
    """Expiry must never move a customer from live to demo on its own."""
    import inspect

    from fire.ui import main_window
    source = inspect.getsource(main_window.MainWindow._apply_trading_state)
    check("restart_mode" not in source,
          "expiry does not switch modes by itself")
    switch = inspect.getsource(main_window.MainWindow._switch_to_demo)
    check("askokcancel" in switch,
          "switching to demo requires an explicit confirmation")
    check("stay open at the exchange" in switch,
          "and warns that real positions remain open")


def _cancel(base: str, sub_id: str) -> None:
    body, header = stripe_signed({
        "id": "evt_presale_cancel",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": sub_id, "status": "canceled"}},
    })
    requests.post(f"{base}/stripe/webhook", data=body,
                  headers={"stripe-signature": header}, timeout=10)


def _reactivate(base: str, sub_id: str) -> None:
    body, header = stripe_signed({
        "id": "evt_presale_renew",
        "type": "customer.subscription.updated",
        "data": {"object": {"id": sub_id, "status": "active",
                            "current_period_end": int(time.time()) + 30 * 86400}},
    })
    requests.post(f"{base}/stripe/webhook", data=body,
                  headers={"stripe-signature": header}, timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
