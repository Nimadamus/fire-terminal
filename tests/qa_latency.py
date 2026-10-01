"""Database latency, measured the way the service connects (new connection per call).

    FIRE_TEST_DATABASE_URL=... python tests/qa_latency.py [idle_seconds]

Read only. Prints warm connect+query times, then waits idle_seconds (default
360, longer than Neon's 5 minute scale to zero) and times the first query.
"""
from __future__ import annotations

import os
import statistics
import sys
import time
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from target_guard import describe              # noqa: E402

DB = os.environ.get("FIRE_TEST_DATABASE_URL", "").strip()


def one() -> tuple[float, float]:
    t0 = time.perf_counter()
    with psycopg.connect(DB, connect_timeout=30) as conn:
        t1 = time.perf_counter()
        conn.execute("SELECT 1").fetchone()
        t2 = time.perf_counter()
    return (t1 - t0) * 1000, (t2 - t1) * 1000


def main() -> int:
    idle = int(sys.argv[1]) if len(sys.argv) > 1 else 360
    print("target:", describe(DB))
    samples = [one() for _ in range(20)]
    conn_ms = sorted(s[0] for s in samples)
    q_ms = sorted(s[1] for s in samples)
    print(f"warm connect   median {statistics.median(conn_ms):6.0f} ms  max {conn_ms[-1]:6.0f}")
    print(f"warm query     median {statistics.median(q_ms):6.1f} ms  max {q_ms[-1]:6.1f}")
    print(f"idle {idle}s ...", flush=True)
    time.sleep(idle)
    c, q = one()
    print(f"after idle     connect {c:6.0f} ms  first query {q:6.1f} ms  total {c + q:6.0f} ms")
    c, q = one()
    print(f"next call      connect {c:6.0f} ms  query {q:6.1f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
