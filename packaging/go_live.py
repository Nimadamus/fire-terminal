"""Detect which of the three manual actions are done, then do everything else.

Run it any time. It checks the three things only Nima can do, reports which are
still outstanding, and executes every step whose prerequisites are met. Safe to
run repeatedly: every step is idempotent and nothing is charged.

    python packaging/go_live.py            # check and execute what is ready
    python packaging/go_live.py --check    # report only, change nothing
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

STRIPE_KEY_FILE = Path("C:/Users/BL/fire-terminal-stripe-test.txt")
RENDER_SERVICE = "srv-da5mdu6417fc73fvg68g"
RENDER_OWNER = "tea-d75maendiees73fan6kg"
DOMAIN = "fireterminal.app"
STAGING = "https://fire-terminal.onrender.com"
VAULT = Path("C:/Users/BL/CREDENTIALS.md")


def render_key() -> str:
    for line in VAULT.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("RENDER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def render_api(path: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(
        f"https://api.render.com/v1{path}", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": f"Bearer {render_key()}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read() or "{}")
    except Exception as exc:
        return {"error": str(exc)}


# -- the three checks ------------------------------------------------------
def check_stripe() -> tuple[bool, str]:
    """A dedicated FIRE Stripe account, in test mode."""
    if not STRIPE_KEY_FILE.is_file():
        return False, "no key file"
    key = STRIPE_KEY_FILE.read_text().strip()
    if not key.startswith("sk_test_"):
        return False, "not a test key"
    try:
        from stripe_api import configure
        stripe = configure(key)
        acct = stripe.Account.retrieve()
        acct = acct.to_dict() if hasattr(acct, "to_dict") else dict(acct)
        name = ((acct.get("business_profile") or {}).get("name")
                or ((acct.get("settings") or {}).get("dashboard") or {}).get("display_name")
                or "")
        if "fire" not in name.lower():
            return False, f"still pointing at {name!r}, not FIRE"
        return True, f"{acct.get('id')} ({name})"
    except Exception as exc:
        return False, type(exc).__name__


def check_render_plan() -> tuple[bool, str]:
    data = render_api(f"/services/{RENDER_SERVICE}")
    if data.get("error"):
        return False, data["error"][:60]
    plan = ((data.get("serviceDetails") or {}).get("plan") or "").lower()
    return plan not in ("free", ""), plan or "unknown"


def check_domain() -> tuple[bool, str]:
    """Registered and resolving. Registered alone is not enough to deploy."""
    try:
        with urllib.request.urlopen(f"https://rdap.org/domain/{DOMAIN}", timeout=15) as r:
            registered = r.status == 200
    except Exception as exc:
        registered = getattr(exc, "code", 0) == 200
    if not registered:
        return False, "not registered"
    import socket
    try:
        socket.gethostbyname(DOMAIN)
        return True, "registered, DNS resolving"
    except Exception:
        return False, "registered, DNS not pointed here yet"


# -- the steps that follow -------------------------------------------------
def step_stripe_setup() -> None:
    print("\n-> configuring Stripe (product, prices, founding code, portal)")
    env = dict(os.environ, STRIPE_SECRET_KEY=STRIPE_KEY_FILE.read_text().strip())
    subprocess.run([sys.executable, str(ROOT / "server" / "setup_stripe.py")],
                   env=env, cwd=str(ROOT), check=False)


def step_stripe_journey() -> None:
    print("\n-> full purchase journey against the FIRE account")
    subprocess.run([sys.executable, str(ROOT / "tests" / "qa_stripe_journey.py"),
                    "--key-file", str(STRIPE_KEY_FILE)], cwd=str(ROOT), check=False)


def step_domain_attach() -> None:
    print(f"\n-> attaching {DOMAIN} to Render")
    for host in (DOMAIN, f"www.{DOMAIN}"):
        out = render_api(f"/services/{RENDER_SERVICE}/custom-domains",
                         "POST", {"name": host})
        if out.get("error"):
            print(f"   {host}: {out['error'][:80]}")
        else:
            print(f"   {host}: added")
    existing = render_api(f"/services/{RENDER_SERVICE}/custom-domains")
    if isinstance(existing, list):
        for item in existing:
            cd = item.get("customDomain", {})
            print(f"   {cd.get('name')}: {cd.get('verificationStatus')}")
    print("   DNS records to create are shown in the Render dashboard;"
          " HTTPS is issued automatically once they resolve.")


def step_verify_live(base: str) -> None:
    print(f"\n-> verifying {base}")
    paths = ["/health", "/", "/support", "/account", "/welcome",
             "/legal/risk", "/legal/terms", "/legal/licence",
             "/legal/privacy", "/legal/refunds", "/style.css", "/config.js"]
    bad = []
    for p in paths:
        try:
            with urllib.request.urlopen(base + p, timeout=30) as r:
                code = r.status
        except Exception as exc:
            code = getattr(exc, "code", 0)
        if code != 200:
            bad.append(f"{p} -> {code}")
    print("   all pages 200" if not bad else "   FAILING: " + ", ".join(bad))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    checks = [
        ("FIRE Stripe account", check_stripe,
         "create it at dashboard.stripe.com (account switcher, Create account),"
         f" then save the TEST secret key to {STRIPE_KEY_FILE}"),
        ("Render always on", check_render_plan,
         "set the fire-terminal service to Starter at dashboard.render.com"),
        (f"{DOMAIN}", check_domain,
         "buy it at porkbun.com or namecheap.com"),
    ]

    print("FIRE go live")
    print("=" * 62)
    state = {}
    for label, fn, todo in checks:
        ok, detail = fn()
        state[label] = ok
        print(f"  [{'x' if ok else ' '}] {label:22} {detail}")
        if not ok:
            print(f"      you: {todo}")

    if args.check:
        return 0

    if state["FIRE Stripe account"]:
        step_stripe_setup()
        step_stripe_journey()

    if state[DOMAIN]:
        step_domain_attach()
        step_verify_live(f"https://{DOMAIN}")
    else:
        step_verify_live(STAGING)

    done = sum(state.values())
    print(f"\n{done} of 3 manual actions complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
