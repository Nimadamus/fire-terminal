"""The whole licence lifecycle against a real database, with timings.

    FIRE_TEST_DATABASE_URL=postgresql://.../fire_dev python tests/qa_full.py

Real server processes, configured as a deployed host (RENDER=true), talking to
the database named in FIRE_TEST_DATABASE_URL. Covers schema creation, waitlist,
subscription and one time purchases, duplicate and out of order webhooks,
activation on two machines, entitlement, release, renewal, cancellation and
expiry, concurrent webhooks spread over TWO server processes, kill and restart,
and that nothing leaks the database credentials. Prints measured latencies.

Destructive: drops every FIRE table first. target_guard refuses production.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import os
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))
from fire.entitlement.token import verify            # noqa: E402
from qa_persistence import free_port, start, stop, wait_up   # noqa: E402
from target_guard import assert_safe, describe        # noqa: E402

DB = os.environ.get("FIRE_TEST_DATABASE_URL", "").strip()
SECRET = "ls_qa_full"
FAILURES: list[str] = []
TIMES: dict[str, list[float]] = {}
_ids = itertools.count(int(time.time()) % 100000 * 1000)
_evt = itertools.count(1)


def check(ok: bool, what: str) -> None:
    print(("PASS  " if ok else "FAIL  ") + what, flush=True)
    if not ok:
        FAILURES.append(what)


def timed(label: str, fn, *a, **kw):
    t = time.perf_counter()
    r = fn(*a, **kw)
    TIMES.setdefault(label, []).append((time.perf_counter() - t) * 1000)
    return r


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000000Z")


class Purchase:
    def __init__(self, product="FIRE Monthly", email="qa@example.com"):
        self.order, self.sub, self.customer = next(_ids), next(_ids), next(_ids)
        self.product, self.email = product, email
        self.renews = time.time() + 30 * 86400

    def order_created(self):
        return "order_created", {"data": {"type": "orders", "id": str(self.order),
            "attributes": {"customer_id": self.customer, "user_email": self.email,
                           "status": "paid", "first_order_item": {
                               "order_id": self.order, "product_name": self.product,
                               "variant_name": "Default"}}}}

    def subscription(self, event="subscription_created", status="active",
                     renews=None, ends=None):
        return event, {"data": {"type": "subscriptions", "id": str(self.sub),
            "attributes": {"customer_id": self.customer, "order_id": self.order,
                           "product_name": self.product, "variant_name": "Default",
                           "user_email": self.email, "status": status,
                           "renews_at": iso(renews or self.renews),
                           "ends_at": iso(ends) if ends else None}}}

    def invoice(self):
        return "subscription_payment_success", {"data": {
            "type": "subscription-invoices", "id": str(next(_ids)),
            "attributes": {"subscription_id": self.sub, "status": "paid"}}}


def send(base, ev, event_id=""):
    event, payload = ev
    payload = dict(payload, meta={"event_name": event,
                                  "webhook_id": event_id or f"qa_{next(_evt)}"})
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return timed("webhook", requests.post, base + "/ls/webhook", data=body,
                 headers={"X-Signature": sig}, timeout=30)


def rows(sql, params=()):
    with psycopg.connect(DB) as conn:
        return conn.execute(sql, params).fetchall()


def licences_for(p: Purchase):
    return rows("SELECT key, stripe_sub, status, expires FROM licences"
                " WHERE checkout_session = %s OR stripe_sub = %s",
                (str(p.order), str(p.sub)))


def main() -> int:
    if not DB:
        print("Set FIRE_TEST_DATABASE_URL.")
        return 2
    assert_safe(DB)
    print("target:", describe(DB), flush=True)
    with psycopg.connect(DB) as conn:
        for table in ("installs", "events", "waitlist", "licences"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")

    private = Ed25519PrivateKey.generate()
    pem = private.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    public = base64.urlsafe_b64encode(private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode().rstrip("=").encode()
    env = {k: v for k, v in os.environ.items()
           if k not in ("FIRE_DB", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
                        "FIRE_TEST_DATABASE_URL")}
    env.update({"RENDER": "true", "DATABASE_URL": DB, "FIRE_SIGNING_KEY": pem,
                "LEMONSQUEEZY_SIGNING_SECRET": SECRET,
                "PYTHONPATH": str(ROOT / "src"), "FIRE_SITE_DIR": str(ROOT / "site"),
                # A SQLite path that must never be created: proves no fallback.
                "FIRE_DB": str(Path(os.environ.get("TEMP", ".")) / "fire_must_not_exist.db")})
    Path(env["FIRE_DB"]).unlink(missing_ok=True)
    log = Path(os.environ.get("TEMP", ".")) / "fire_qa_full.log"
    log.write_bytes(b"")

    pa, pb = free_port(), free_port()
    a, b = f"http://127.0.0.1:{pa}", f"http://127.0.0.1:{pb}"
    proc_a, proc_b = start(env, pa, log), start(env, pb, log)
    check(wait_up(a, proc_a, 60) and wait_up(b, proc_b, 60), "two server processes up on Postgres")
    tables = {r[0] for r in rows("SELECT table_name FROM information_schema.tables"
                                 " WHERE table_schema = 'public'")}
    check({"licences", "installs", "waitlist", "events"} <= tables, "schema created on start")
    idx = {r[0] for r in rows("SELECT indexname FROM pg_indexes WHERE tablename = 'licences'")}
    check({"licences_one_per_subscription", "licences_one_per_checkout"} <= idx,
          "unique purchase indexes present")

    # waitlist
    r = timed("waitlist", requests.post, a + "/waitlist",
              json={"email": "qa.wait@example.com", "source": "qa"}, timeout=30)
    check(r.ok and r.json()["new"] is True, "waitlist signup")
    r = requests.post(b + "/waitlist", json={"email": "QA.wait@example.com"}, timeout=30)
    check(r.ok and r.json()["new"] is False, "waitlist duplicate (other process) is one row")

    # subscription purchase, order first, duplicates
    sub = Purchase()
    check(send(a, sub.order_created()).json().get("issued") is True, "order_created issues")
    check(send(b, sub.subscription()).json().get("status") == "active",
          "subscription_created attaches to that licence")
    send(a, sub.order_created()); send(b, sub.subscription(), "dup_x"); send(a, sub.subscription(), "dup_x")
    lic = licences_for(sub)
    check(len(lic) == 1 and lic[0][1] == str(sub.sub), "one licence for the subscription purchase")
    key = lic[0][0]
    r = timed("success_page", requests.get, a + "/licence",
              params={"session_id": str(sub.order)}, timeout=30)
    check(r.ok and r.json()["key"] == key, "success page returns the key by order id")

    # out of order
    ooo = Purchase()
    send(b, ooo.subscription("subscription_updated"))
    send(a, ooo.order_created())
    send(b, ooo.subscription())
    check(len(licences_for(ooo)) == 1, "out of order delivery: one licence")

    # one time purchase
    once = Purchase(product="FIRE Lifetime")
    send(a, once.order_created()); send(b, once.order_created()); send(a, once.order_created(), "o1"); send(a, once.order_created(), "o1")
    lic1 = licences_for(once)
    check(len(lic1) == 1 and lic1[0][3] is None and lic1[0][1] == "",
          "one time purchase: one licence, no expiry")

    # activation, two machines, entitlement, release
    r = timed("activate", requests.post, a + "/activate", json={"key": key, "install": "qa-pc-1"}, timeout=30)
    check(r.ok and verify(r.json()["token"], public, "qa-pc-1") is not None, "activation, token verifies")
    r = timed("activate", requests.post, b + "/activate", json={"key": key, "install": "qa-pc-2"}, timeout=30)
    check(r.ok, "second machine activates")
    r = timed("entitlement", requests.post, a + "/entitlement", json={"install": "qa-pc-2"}, timeout=30)
    check(r.ok and verify(r.json()["token"], public, "qa-pc-2").status == "active", "entitlement by install")
    r = requests.get(b + "/licence/state", params={"key": key}, timeout=30)
    check(r.ok and r.json()["seats_used"] == 2, "two seats in use")
    r = timed("release", requests.post, a + "/licence/release", json={"key": key, "install": "qa-pc-2"}, timeout=30)
    check(r.ok and r.json()["seats_used"] == 1, "release frees a seat")

    # renewal keeps the key
    for month in (1, 2):
        end = sub.renews + month * 30 * 86400
        send(a, sub.invoice()); send(b, sub.subscription("subscription_updated", renews=end))
        lic = licences_for(sub)
        check(len(lic) == 1 and lic[0][0] == key and abs(lic[0][3] - end) < 2,
              f"renewal {month}: same key, expiry moved")

    # cancellation then expiry
    canc = Purchase()
    send(a, canc.subscription())
    ckey = licences_for(canc)[0][0]
    requests.post(a + "/activate", json={"key": ckey, "install": "qa-cancel"}, timeout=30)
    send(b, canc.subscription("subscription_cancelled", "cancelled", ends=time.time() + 7 * 86400))
    check(licences_for(canc)[0][2] == "active", "cancelled: active until ends_at")
    send(a, canc.subscription("subscription_expired", "expired", ends=time.time() - 1))
    r = requests.post(b + "/entitlement", json={"install": "qa-cancel"}, timeout=30)
    check(licences_for(canc)[0][2] == "expired" and
          verify(r.json()["token"], public, "qa-cancel").status == "expired",
          "expired: client entitlement says expired")

    # separate purchases
    s1, s2 = Purchase(email="same@example.com"), Purchase(email="same@example.com")
    for p in (s1, s2):
        send(a, p.order_created()); send(b, p.subscription())
    check(licences_for(s1)[0][0] != licences_for(s2)[0][0] and
          len(licences_for(s1)) == len(licences_for(s2)) == 1,
          "two purchases by one customer: two licences")

    # concurrency across two processes, against this database
    rounds, bad = 15, 0
    for _ in range(rounds):
        p = Purchase()
        deliveries = [(a, p.order_created()), (b, p.subscription()),
                      (b, p.order_created()), (a, p.subscription("subscription_updated")),
                      (a, p.subscription()), (b, p.order_created())]
        barrier = threading.Barrier(len(deliveries))
        codes = []

        def go(base, ev):
            barrier.wait()
            codes.append(send(base, ev).status_code)
        ts = [threading.Thread(target=go, args=d) for d in deliveries]
        for t in ts: t.start()
        for t in ts: t.join()
        lic = licences_for(p)
        if len(lic) != 1 or lic[0][1] != str(p.sub) or any(c != 200 for c in codes):
            bad += 1
    check(bad == 0, f"concurrent webhooks over 2 processes: {rounds} purchases, {bad} bad")

    # kill both, restart one, read everything back
    before = {t: rows(f"SELECT COUNT(*) FROM {t}")[0][0]
              for t in ("licences", "installs", "waitlist", "events")}
    stop(proc_a); stop(proc_b)
    pc = free_port(); c = f"http://127.0.0.1:{pc}"
    proc_c = start(env, pc, log)
    check(wait_up(c, proc_c, 60), "restart on the same database")
    after = {t: rows(f"SELECT COUNT(*) FROM {t}")[0][0] for t in before}
    check(before == after, f"every row survives restart {after}")
    r = requests.get(c + "/licence", params={"session_id": str(sub.order)}, timeout=30)
    check(r.ok and r.json()["key"] == key, "licence survives restart")
    r = requests.post(c + "/entitlement", json={"install": "qa-pc-1"}, timeout=30)
    check(r.ok and verify(r.json()["token"], public, "qa-pc-1").status == "active",
          "activated machine still entitled after restart")
    check(send(c, sub.subscription(), "dup_x").json().get("duplicate") is True,
          "webhook replay after restart is a duplicate")
    stop(proc_c)

    out = log.read_text(errors="replace")
    secret = DB.split("://", 1)[1].split("@", 1)[0]
    password = secret.split(":", 1)[-1]
    check(DB not in out and (len(password) < 12 or password not in out)
          and secret not in out,
          "no database URL, user:password or password in server output")
    check(not Path(env["FIRE_DB"]).exists(), "no SQLite file created (no fallback)")
    check("database ready: postgres" in out and "database ready: sqlite" not in out,
          "server logged postgres backend only")

    print("\nlatency (ms, client measured, laptop to database via local server):")
    for label, xs in TIMES.items():
        xs = sorted(xs)
        print(f"  {label:13s} n={len(xs):3d}  median {statistics.median(xs):7.0f}"
              f"  p90 {xs[int(len(xs) * 0.9) - 1 if len(xs) > 1 else 0]:7.0f}  max {xs[-1]:7.0f}")
    print(f"\n{len(FAILURES)} failure(s)")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
