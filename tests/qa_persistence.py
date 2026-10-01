"""End to end: a real server process on Postgres, killed and restarted.

    FIRE_TEST_DATABASE_URL=postgresql://... python tests/qa_persistence.py

Runs the service exactly as a deployed host would (RENDER=true, so SQLite is
refused), walks a purchase through the Lemon Squeezy webhook, the success page,
activation, entitlement, seat state and release, then kills the process,
starts a new one and checks every record is still there. Also checks that a
deployed service with no Postgres refuses to start, and that the database URL
never appears in the server's output.

Use a throwaway database. Every FIRE table in it is dropped first.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import psycopg
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"
sys.path.insert(0, str(ROOT / "src"))
from fire.entitlement.token import verify            # noqa: E402

DB = os.environ.get("FIRE_TEST_DATABASE_URL", "").strip()
SECRET = "ls_qa_persistence"
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
FAILURES: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + what)
    if not ok:
        FAILURES.append(what)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(env: dict, port: int, log: Path) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)], cwd=SERVER, env=env, creationflags=NO_WINDOW,
        stdout=log.open("ab"), stderr=subprocess.STDOUT)


def wait_up(base: str, proc: subprocess.Popen, seconds: float = 30) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            return False
        try:
            if requests.get(base + "/health", timeout=2).ok:
                return True
        except requests.RequestException:
            pass
        time.sleep(0.3)
    return False


def stop(proc: subprocess.Popen) -> None:
    proc.kill()
    proc.wait(timeout=15)


def signed(event: str, data_id: str, attributes: dict, event_id: str):
    body = json.dumps({"meta": {"event_name": event, "webhook_id": event_id},
                       "data": {"id": data_id, "attributes": attributes}},
                      separators=(",", ":")).encode()
    return body, {"X-Signature": hmac.new(SECRET.encode(), body,
                                          hashlib.sha256).hexdigest()}


def main() -> int:
    if not DB.startswith(("postgres://", "postgresql://")):
        print("Set FIRE_TEST_DATABASE_URL to a throwaway Postgres.")
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from target_guard import assert_safe
    assert_safe(DB)                     # never production, before any DROP
    with psycopg.connect(DB) as conn:
        for table in ("installs", "events", "waitlist", "licences"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")

    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode().rstrip("=").encode()

    env = {k: v for k, v in os.environ.items()
           if k not in ("DATABASE_URL", "FIRE_DB", "STRIPE_SECRET_KEY",
                        "STRIPE_WEBHOOK_SECRET")}
    env.update({"RENDER": "true", "FIRE_SIGNING_KEY": pem,
                "LEMONSQUEEZY_SIGNING_SECRET": SECRET,
                "PYTHONPATH": str(ROOT / "src"),
                "FIRE_SITE_DIR": str(ROOT / "site")})
    log = Path(os.environ.get("TEMP", ".")) / "fire_qa_persistence.log"
    log.write_bytes(b"")

    # 1. Deployed with no Postgres: must refuse to start.
    port = free_port()
    proc = start(env, port, log)
    up = wait_up(f"http://127.0.0.1:{port}", proc, 15)
    check(not up, "deployed service with no DATABASE_URL refuses to start")
    if proc.poll() is None:
        stop(proc)

    # 2. The real thing.
    env["DATABASE_URL"] = DB
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start(env, port, log)
    check(wait_up(base, proc), "service starts on Postgres")

    r = requests.post(base + "/waitlist", json={"email": "qa.wait@example.com",
                                                "source": "qa"}, timeout=10)
    check(r.ok and r.json().get("new") is True, "waitlist signup stored")

    order_id = "880001"
    body, headers = signed("subscription_created", "sub_qa_1", {
        "user_email": "qa.buyer@example.com", "status": "active",
        "order_id": int(order_id), "product_name": "FIRE Monthly",
        "renews_at": "2026-11-30T00:00:00Z"}, "evt_qa_1")
    r = requests.post(base + "/ls/webhook", data=body, headers=headers, timeout=10)
    check(r.ok and r.json().get("issued"), "Lemon Squeezy purchase issues a licence")
    r = requests.post(base + "/ls/webhook", data=body, headers=headers, timeout=10)
    check(r.ok and r.json().get("duplicate"), "same webhook again is a duplicate")

    r = requests.get(base + "/licence", params={"session_id": order_id}, timeout=10)
    key = r.json().get("key", "") if r.ok else ""
    check(bool(key), "success page gets the key for the order")

    r = requests.post(base + "/activate", json={"key": key, "install": "qa-pc-1"},
                      timeout=10)
    tok = r.json().get("token", "") if r.ok else ""
    claims = verify(tok, public, "qa-pc-1") if tok else None
    check(claims is not None, "activation returns a token the app verifies")

    r = requests.post(base + "/activate", json={"key": key, "install": "qa-pc-2"},
                      timeout=10)
    check(r.ok, "second machine activates")
    r = requests.post(base + "/entitlement", json={"install": "qa-pc-1"}, timeout=10)
    check(r.ok and verify(r.json()["token"], public, "qa-pc-1") is not None,
          "entitlement re-check by install id alone")
    r = requests.get(base + "/licence/state", params={"key": key}, timeout=10)
    check(r.ok and r.json().get("seats_used") == 2, "seat state shows 2 machines")
    r = requests.post(base + "/licence/release", json={"key": key,
                      "install": "qa-pc-2"}, timeout=10)
    check(r.ok and r.json().get("seats_used") == 1, "release frees a seat")

    # 3. Kill it the way a host does, start a fresh process, read it all back.
    stop(proc)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    proc = start(env, port, log)
    check(wait_up(base, proc), "service restarts on the same database")
    r = requests.get(base + "/licence", params={"session_id": order_id}, timeout=10)
    check(r.ok and r.json().get("key") == key, "licence survives the restart")
    r = requests.post(base + "/entitlement", json={"install": "qa-pc-1"}, timeout=10)
    check(r.ok, "activated machine still entitled after restart")
    r = requests.get(base + "/licence/state", params={"key": key}, timeout=10)
    check(r.ok and r.json().get("seats_used") == 1, "seat state survives restart")
    r = requests.post(base + "/waitlist", json={"email": "qa.wait@example.com"},
                      timeout=10)
    check(r.ok and r.json().get("new") is False, "waitlist signup survives restart")
    r = requests.post(base + "/ls/webhook", data=body, headers=headers, timeout=10)
    check(r.ok and r.json().get("duplicate"),
          "webhook replay after restart is still a duplicate")
    stop(proc)

    with psycopg.connect(DB) as conn:
        n = conn.execute("SELECT COUNT(*) FROM licences").fetchone()[0]
    check(n == 1, f"exactly one licence row in Postgres (found {n})")

    out = log.read_text(errors="replace")
    password = DB.split("://", 1)[1].split("@", 1)[0].split(":", 1)[-1]
    check(DB not in out and (len(password) < 4 or password not in out),
          "server output never contains the database URL or password")

    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
