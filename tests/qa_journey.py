"""Launch QA: the customer journey against a real running service.

Not part of the unit suite. This starts uvicorn for real, over a real socket,
and walks the path a stranger takes on the day they pay us: landing page,
waitlist, purchase, activation, re-check, changing computer, cancellation.

The unit tests use FastAPI's in process client, which is fast and proves the
logic. This proves the thing actually serves, which is a different question and
the one that matters on launch day.

    python tests/qa_journey.py
"""
from __future__ import annotations

import base64
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import requests                                              # noqa: E402
from cryptography.hazmat.primitives import serialization      # noqa: E402
from cryptography.hazmat.primitives.asymmetric.ed25519 import (  # noqa: E402
    Ed25519PrivateKey,
)

from fire.entitlement.token import TokenInvalid, verify       # noqa: E402

PASS, FAIL = "  PASS", "  FAIL"
results: list[tuple[bool, str]] = []


def check(ok: bool, what: str, detail: str = "") -> bool:
    results.append((bool(ok), what))
    print(f"{PASS if ok else FAIL}  {what}" + (f"   [{detail}]" if detail else ""))
    return bool(ok)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> int:
    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode("ascii")
    public = base64.urlsafe_b64encode(
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw)).decode("ascii").rstrip("=").encode()

    port = free_port()
    db = ROOT / "dist" / "qa_journey.db"
    db.parent.mkdir(exist_ok=True)
    if db.exists():
        db.unlink()

    # The seeding helpers below import the service's own store module in this
    # process, so this process has to point at the same database the service
    # is using. Without this they quietly open a different file.
    os.environ["FIRE_DB"] = str(db)
    os.environ.pop("DATABASE_URL", None)

    env = dict(os.environ)
    env.update({"FIRE_SIGNING_KEY": pem, "FIRE_DB": str(db),
                "PYTHONPATH": str(ROOT / "src"), "FIRE_SITE_DIR": str(ROOT / "site")})

    print("\nStarting the service for real, on a real socket.\n")
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
            print("service never came up:")
            proc.kill()
            print(proc.stdout.read() if proc.stdout else "")
            return 1

        run(base, public)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
        if db.exists():
            db.unlink()

    passed = sum(1 for ok, _ in results if ok)
    failed = len(results) - passed
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


def run(base: str, public: bytes) -> None:

    # -- 1. a stranger lands ------------------------------------------------
    print("1. Landing")
    page = requests.get(f"{base}/", timeout=10)
    check(page.status_code == 200, "front page serves")
    check("FIRE" in page.text, "front page mentions the product")
    check("data-plan" not in page.text or "waitlist" in page.text,
          "pre launch state, no live checkout button")
    for path in ("/support", "/account", "/welcome", "/legal/risk",
                 "/legal/terms", "/legal/privacy", "/legal/refunds",
                 "/legal/licence", "/style.css", "/img/terminal.png"):
        check(requests.get(f"{base}{path}", timeout=10).status_code == 200,
              f"serves {path}")
    check(requests.get(f"{base}/nope", timeout=10).status_code == 404,
          "unknown page returns a real 404")

    # -- 2. waitlist --------------------------------------------------------
    print("\n2. Waitlist")
    r = requests.post(f"{base}/waitlist", json={"email": "qa@example.com"}, timeout=10)
    check(r.status_code == 200 and r.json()["new"] is True, "joins the waitlist")
    r = requests.post(f"{base}/waitlist", json={"email": "QA@example.com"}, timeout=10)
    check(r.status_code == 200 and r.json()["new"] is False,
          "joining twice is not an error")
    check(requests.post(f"{base}/waitlist", json={"email": "nope"},
                        timeout=10).status_code == 400, "refuses a bad address")

    # -- 3. before purchase -------------------------------------------------
    print("\n3. A fresh install, no licence")
    r = requests.post(f"{base}/entitlement", json={"install": "qa-machine-1"}, timeout=10)
    check(r.status_code == 200, "fresh install gets an answer")
    trial = verify(r.json()["token"], public, "qa-machine-1")
    check(trial.status == "trial", "and it is a trial, not a refusal")
    check(trial.expires and trial.expires > time.time(), "trial has a future expiry")

    # -- 4. purchase --------------------------------------------------------
    print("\n4. Purchase")
    check(requests.get(f"{base}/licence", params={"session_id": "cs_qa"},
                       timeout=10).status_code == 202,
          "success page waits rather than failing while the webhook lands")

    key = seed_purchase(base)
    r = requests.get(f"{base}/licence", params={"session_id": "cs_qa"}, timeout=10)
    check(r.status_code == 200 and r.json()["key"] == key,
          "success page hands over the key once the webhook lands")

    # -- 5. activation ------------------------------------------------------
    print("\n5. Activation")
    r = requests.post(f"{base}/activate",
                      json={"key": key.lower().replace("-", " "),
                            "install": "qa-machine-1"}, timeout=10)
    check(r.status_code == 200, "activates however the key is typed")
    payload = verify(r.json()["token"], public, "qa-machine-1")
    check(payload.status == "active", "token says active")
    check(payload.plan == "FIRE Monthly", "token carries the plan")
    check("qa@example.com" not in r.json()["token"], "no personal data in the token")

    try:
        verify(r.json()["token"], public, "some-other-machine")
        check(False, "token is bound to one install")
    except TokenInvalid:
        check(True, "token is bound to one install")

    # -- 6. changing computer ----------------------------------------------
    print("\n6. Changing computer")
    for n in (2, 3):
        requests.post(f"{base}/activate",
                      json={"key": key, "install": f"qa-machine-{n}"}, timeout=10)
    r = requests.post(f"{base}/activate",
                      json={"key": key, "install": "qa-machine-4"}, timeout=10)
    check(r.status_code == 409, "fourth computer is refused")

    state = requests.get(f"{base}/licence/state", params={"key": key}, timeout=10).json()
    check(state["seats_used"] == 3, "account page shows three computers")
    check("qa@example.com" not in json.dumps(state), "account state leaks no email")

    check(all(c["handle"] and c["id"] for c in state["computers"]),
          "each computer has a readable id and an exact handle")
    r = requests.post(f"{base}/licence/release",
                      json={"key": key,
                            "install": state["computers"][0]["handle"]}, timeout=10)
    check(r.status_code == 200 and r.json()["seats_used"] == 2,
          "customer frees a seat themselves")
    check(requests.post(f"{base}/activate",
                        json={"key": key, "install": "qa-machine-4"},
                        timeout=10).status_code == 200,
          "the new computer then activates")

    # -- 7. renewal and cancellation ---------------------------------------
    print("\n7. Renewal, failure and cancellation")
    r = requests.post(f"{base}/entitlement", json={"install": "qa-machine-1"}, timeout=10)
    check(verify(r.json()["token"], public, "qa-machine-1").status == "active",
          "re-check without sending the key still works")

    set_status(base, key, "expired")
    r = requests.post(f"{base}/entitlement", json={"install": "qa-machine-1"}, timeout=10)
    after = verify(r.json()["token"], public, "qa-machine-1")
    check(after.status == "expired", "a cancelled subscription reads as expired")

    set_status(base, key, "active")
    r = requests.post(f"{base}/entitlement", json={"install": "qa-machine-1"}, timeout=10)
    check(verify(r.json()["token"], public, "qa-machine-1").status == "active",
          "renewing restores it")

    # -- 8. what a stranger cannot do --------------------------------------
    print("\n8. Abuse")
    check(requests.post(f"{base}/activate",
                        json={"key": "FIRE-AAAAA-AAAAA-AAAAA-AAAAA",
                              "install": "x"}, timeout=10).status_code == 404,
          "an invented key is refused")
    check(requests.post(f"{base}/stripe/webhook", data=b"{}",
                        headers={"stripe-signature": "forged"},
                        timeout=10).status_code in (400, 503),
          "an unsigned webhook is refused")
    for attack in ("/../server/app.py", "/../../CREDENTIALS.md"):
        r = requests.get(f"{base}{attack}", timeout=10)
        check(r.status_code == 404 or "STRIPE" not in r.text,
              f"path traversal blocked: {attack}")

    health = requests.get(f"{base}/health", timeout=10).json()
    check(health["signing_key"] is True, "health reports the signing key")
    check(health["site"] is True, "health reports the site is present")
    check("FIRE_SIGNING_KEY" not in json.dumps(health), "health leaks no secret")


def seed_purchase(base: str) -> str:
    """Stand in for the Stripe webhook, which cannot run without Stripe.

    Uses the service's own modules so the licence is created exactly the way
    the real webhook creates it.
    """
    sys.path.insert(0, str(ROOT / "server"))
    import licences as licence_mod
    import store as store_mod
    key = licence_mod.new_key()
    store_mod.create_licence(key, "qa@example.com", "FIRE Monthly",
                             time.time() + 30 * 86400, "cus_qa", "sub_qa", "cs_qa")
    return key


def set_status(base: str, key: str, status: str) -> None:
    import store as store_mod
    store_mod.set_status(key, status,
                         time.time() + (30 * 86400 if status == "active" else -60))


if __name__ == "__main__":
    raise SystemExit(main())
