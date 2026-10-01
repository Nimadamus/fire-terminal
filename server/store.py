"""Storage for licences and the installs bound to them.

Deliberately not an ORM. There are three tables and about a dozen queries, and
a dependency that has to be upgraded in lockstep with a payments integration is
not worth the typing it saves.

Postgres, from DATABASE_URL, is the only database production may use. SQLite
exists for local development and the test suite and nothing else: a deployed
service with no Postgres refuses to start rather than quietly writing licences
to a file the host will throw away. That is exactly what happened on Render's
free plan, where /tmp is wiped every time the instance sleeps.

The only difference between the two that matters here is the placeholder
character, and every write is written so it is safe on both.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterable, Optional

log = logging.getLogger("fire.licence.store")

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
SQLITE_PATH = os.environ.get("FIRE_DB", "fire_licences.db")

# A managed Postgres that scales to zero (Neon) takes a moment to wake, and a
# network blip should not turn into a lost purchase. Bounded on purpose: a
# webhook that hangs is as bad as one that fails.
CONNECT_TIMEOUT_S = int(os.environ.get("FIRE_DB_CONNECT_TIMEOUT", "10"))

# Postgres connections are pooled and reused. A new TLS connection to Neon costs
# about a quarter of a second; a webhook makes half a dozen queries. Small on
# purpose: one instance never holds more than POOL_MAX, and an idle connection
# is closed after POOL_IDLE_S, well before Neon suspends its compute, so the
# pool never keeps the database awake and never hands out a connection Neon
# has already dropped.
POOL_MAX = int(os.environ.get("FIRE_DB_POOL_MAX", "4"))
POOL_IDLE_S = 60.0
POOL_LIFETIME_S = 900.0
POOL_WAIT_S = float(os.environ.get("FIRE_DB_POOL_WAIT", "15"))

# SQLite allows one writer, so SQLite calls take turns inside the process.
# Postgres needs no lock: the unique indexes and ON CONFLICT writes are what
# make concurrent deliveries safe, across threads and across instances alike.
_lock = threading.RLock()
_pool = None
_pool_guard = threading.Lock()
_opened = 0                      # connections actually created, for measurement


class DatabaseUnavailable(RuntimeError):
    """The database could not be reached. Callers answer 503 so senders retry."""


class ConfigurationError(RuntimeError):
    """The service is deployed without a durable database."""


def _is_postgres() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def _is_deployed() -> bool:
    """True on a real host. Render sets RENDER; anything else sets FIRE_ENV."""
    return bool(os.environ.get("RENDER")) or \
        os.environ.get("FIRE_ENV", "").lower() == "production"


def backend() -> str:
    """Which database this process uses. Never includes the URL or password."""
    return "postgres" if _is_postgres() else "sqlite"


def _check_configuration() -> None:
    if DATABASE_URL and not _is_postgres():
        # Never fall back to SQLite because a URL was mistyped.
        raise ConfigurationError("DATABASE_URL is set but is not a Postgres URL.")
    if _is_deployed() and not _is_postgres():
        raise ConfigurationError(
            "No Postgres DATABASE_URL on a deployed service. Refusing to start: "
            "licences written to local disk here would be lost.")


def _placeholder() -> str:
    return "%s" if _is_postgres() else "?"


def _count_new_connection(_conn) -> None:
    global _opened
    _opened += 1


def connections_opened() -> int:
    """How many database connections this process has created so far."""
    return _opened


def _get_pool():
    global _pool
    if _pool is None:
        with _pool_guard:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                _pool = ConnectionPool(
                    DATABASE_URL, min_size=0, max_size=POOL_MAX,
                    max_idle=POOL_IDLE_S, max_lifetime=POOL_LIFETIME_S,
                    timeout=POOL_WAIT_S, reconnect_timeout=60.0,
                    configure=_count_new_connection, name="fire-licence",
                    kwargs={"connect_timeout": CONNECT_TIMEOUT_S,
                            "application_name": "fire-licence"},
                    open=True)
    return _pool


def close() -> None:
    """Close every pooled connection. Called when the service shuts down."""
    global _pool
    with _pool_guard:
        if _pool is not None:
            _pool.close()
            _pool = None


@contextmanager
def _guard():
    if _is_postgres():
        yield
    else:
        with _lock:
            yield


@contextmanager
def connect():
    """A connection for one unit of work, committed on success and rolled
    back on any error. Postgres connections come from the pool and go back to
    it; one left broken by a failure is discarded by the pool, never reused."""
    if _is_postgres():
        import psycopg
        from psycopg_pool import PoolTimeout
        try:
            ctx = _get_pool().connection()
            conn = ctx.__enter__()
        except (PoolTimeout, psycopg.OperationalError) as exc:
            # The type only. The message can carry the host and user.
            log.warning("database unavailable: %s", type(exc).__name__)
            raise DatabaseUnavailable("database unreachable") from exc
        try:
            yield conn
        except BaseException as exc:
            ctx.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            ctx.__exit__(None, None, None)
        return
    conn = sqlite3.connect(SQLITE_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _run(work):
    """Run one unit of work, retrying once on a dropped connection.

    A pooled connection can be cut by the server between uses (Neon suspends
    its compute; a network blip). The pool discards it on the way back, and the
    retry gets a fresh one. Safe to repeat: every write here is idempotent, and
    a statement that failed on a dead connection was never committed.
    """
    import psycopg
    for attempt in (1, 2):
        try:
            with _guard(), connect() as conn:
                return work(conn)
        except psycopg.OperationalError as exc:
            if attempt == 2 or not _is_postgres():
                log.warning("database error: %s", type(exc).__name__)
                raise DatabaseUnavailable("database error") from exc
            log.info("retrying on a fresh connection after %s", type(exc).__name__)
            # When the server dropped one connection it usually dropped them
            # all (Neon suspending). Test every idle one now and discard the
            # dead, so the retry cannot pick up another casualty.
            if _pool is not None:
                _pool.check()


def q(sql: str) -> str:
    """Translate ? placeholders for whichever database is behind us."""
    return sql.replace("?", "%s") if _is_postgres() else sql


SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS licences (
        key             TEXT PRIMARY KEY,
        email           TEXT NOT NULL DEFAULT '',
        plan            TEXT NOT NULL DEFAULT '',
        status          TEXT NOT NULL DEFAULT 'active',
        expires         DOUBLE PRECISION,
        seats           INTEGER NOT NULL DEFAULT 3,
        stripe_customer TEXT NOT NULL DEFAULT '',
        stripe_sub      TEXT NOT NULL DEFAULT '',
        checkout_session TEXT NOT NULL DEFAULT '',
        created         DOUBLE PRECISION NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS installs (
        install   TEXT NOT NULL,
        key       TEXT NOT NULL,
        first_seen DOUBLE PRECISION NOT NULL,
        last_seen  DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (install, key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS waitlist (
        email   TEXT PRIMARY KEY,
        note    TEXT NOT NULL DEFAULT '',
        source  TEXT NOT NULL DEFAULT '',
        joined  DOUBLE PRECISION NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS events (
        id      TEXT PRIMARY KEY,
        kind    TEXT NOT NULL,
        seen    DOUBLE PRECISION NOT NULL
    )
    """,
    # One licence per subscription, enforced by the database rather than by a
    # read before the write, so two deliveries of the same purchase arriving
    # together cannot both issue a key.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS licences_one_per_subscription
        ON licences (stripe_sub) WHERE stripe_sub <> ''
    """,
    # And one licence per checkout (Stripe session or Lemon Squeezy order).
    """
    CREATE UNIQUE INDEX IF NOT EXISTS licences_one_per_checkout
        ON licences (checkout_session) WHERE checkout_session <> ''
    """,
)


def init() -> None:
    """Create anything missing. Every statement is idempotent, so this runs on
    every start and is the whole migration story for a schema this small."""
    _check_configuration()
    with _guard(), connect() as conn:
        cur = conn.cursor()
        if _is_postgres():
            # CREATE ... IF NOT EXISTS is not safe when two instances start at
            # once (both pass the check, one fails on the catalogue). One
            # transaction level lock makes every starting instance take turns.
            cur.execute("SELECT pg_advisory_xact_lock(724100117)")
        for statement in SCHEMA:
            cur.execute(statement)
    log.info("database ready: %s", backend())


def _rows(cur) -> list[tuple]:
    return list(cur.fetchall())


def execute(sql: str, params: Iterable[Any] = ()) -> int:
    """Run one write. Returns the number of rows it changed."""
    def work(conn):
        cur = conn.cursor()
        cur.execute(q(sql), tuple(params))
        return int(cur.rowcount or 0)
    return _run(work)


def fetchone(sql: str, params: Iterable[Any] = ()) -> Optional[tuple]:
    def work(conn):
        cur = conn.cursor()
        cur.execute(q(sql), tuple(params))
        row = cur.fetchone()
        return tuple(row) if row else None
    return _run(work)


# -- licences --------------------------------------------------------------
LICENCE_COLUMNS = ("key", "email", "plan", "status", "expires", "seats",
                   "stripe_customer", "stripe_sub", "checkout_session", "created")


def create_licence(key: str, email: str, plan: str, expires: Optional[float],
                   stripe_customer: str = "", stripe_sub: str = "",
                   checkout_session: str = "", seats: int = 3) -> bool:
    """False if this subscription already has a licence (nothing written)."""
    return execute(
        "INSERT INTO licences (key, email, plan, status, expires, seats,"
        " stripe_customer, stripe_sub, checkout_session, created)"
        " VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT DO NOTHING",
        (key, email, plan, expires, seats, stripe_customer, stripe_sub,
         checkout_session, time.time())) == 1


def licence(key: str) -> Optional[dict]:
    row = fetchone(
        "SELECT key, email, plan, status, expires, seats, stripe_customer,"
        " stripe_sub, checkout_session, created FROM licences WHERE key = ?",
        (key,))
    return dict(zip(LICENCE_COLUMNS, row)) if row else None


def licence_by_session(session_id: str) -> Optional[dict]:
    row = fetchone(
        "SELECT key, email, plan, status, expires, seats, stripe_customer,"
        " stripe_sub, checkout_session, created FROM licences"
        " WHERE checkout_session = ?", (session_id,))
    return dict(zip(LICENCE_COLUMNS, row)) if row else None


def licence_by_subscription(sub_id: str) -> Optional[dict]:
    row = fetchone(
        "SELECT key, email, plan, status, expires, seats, stripe_customer,"
        " stripe_sub, checkout_session, created FROM licences"
        " WHERE stripe_sub = ?", (sub_id,))
    return dict(zip(LICENCE_COLUMNS, row)) if row else None


def attach_subscription(key: str, sub_id: str) -> bool:
    """Link a subscription to the licence its order already issued.

    True if the licence now carries this subscription. Only ever fills an empty
    link: a licence already tied to a different subscription is left alone and
    False comes back, so one key can never be moved between purchases.
    The order's provisional expiry is cleared: from here the subscription's
    own period end, set by the caller, is the only one that counts.
    """
    execute("UPDATE licences SET stripe_sub = ?, expires = NULL"
            " WHERE key = ? AND stripe_sub = ''", (sub_id, key))
    row = fetchone("SELECT stripe_sub FROM licences WHERE key = ?", (key,))
    return bool(row) and str(row[0]) == sub_id


def set_plan(key: str, plan: str) -> None:
    execute("UPDATE licences SET plan = ? WHERE key = ?", (plan, key))


def set_status(key: str, status: str, expires: Optional[float] = None) -> None:
    if expires is None:
        execute("UPDATE licences SET status = ? WHERE key = ?", (status, key))
    else:
        execute("UPDATE licences SET status = ?, expires = ? WHERE key = ?",
                (status, expires, key))


# -- installs --------------------------------------------------------------
def bind_install(install: str, key: str) -> None:
    now = time.time()
    execute("INSERT INTO installs (install, key, first_seen, last_seen)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT (install, key) DO UPDATE SET last_seen = excluded.last_seen",
            (install, key, now, now))


def install_count(key: str) -> int:
    row = fetchone("SELECT COUNT(*) FROM installs WHERE key = ?", (key,))
    return int(row[0]) if row else 0


def install_is_bound(install: str, key: str) -> bool:
    return fetchone("SELECT 1 FROM installs WHERE install = ? AND key = ?",
                    (install, key)) is not None


def key_for_install(install: str) -> Optional[str]:
    row = fetchone("SELECT key FROM installs WHERE install = ?"
                   " ORDER BY last_seen DESC", (install,))
    return str(row[0]) if row else None


# -- webhook idempotency ---------------------------------------------------
def seen_event(event_id: str, kind: str = "") -> bool:
    """True if this webhook event was already handled successfully.

    Only asks. The event is recorded by mark_event once its work is done, so a
    delivery that fails halfway (the database dropped, the process restarted)
    is retried by the sender and processed then, instead of being remembered as
    handled and lost. Duplicate work is still impossible: every write a
    webhook makes is idempotent on its own.
    """
    return fetchone("SELECT 1 FROM events WHERE id = ?", (event_id,)) is not None


def mark_event(event_id: str, kind: str = "") -> None:
    """Record a webhook event as handled. Safe to call twice."""
    execute("INSERT INTO events (id, kind, seen) VALUES (?, ?, ?)"
            " ON CONFLICT (id) DO NOTHING", (event_id, kind, time.time()))


# -- waitlist --------------------------------------------------------------
def join_waitlist(email: str, note: str = "", source: str = "") -> bool:
    """True if this is a new signup. Signing up twice is not an error."""
    return execute("INSERT INTO waitlist (email, note, source, joined)"
                   " VALUES (?, ?, ?, ?) ON CONFLICT (email) DO NOTHING",
                   (email, note[:500], source[:60], time.time())) == 1


def waitlist_size() -> int:
    row = fetchone("SELECT COUNT(*) FROM waitlist", ())
    return int(row[0]) if row else 0


def installs_for(key: str) -> list[dict]:
    """Every machine bound to a licence, newest activity first."""
    def work(conn):
        cur = conn.cursor()
        cur.execute(q("SELECT install, first_seen, last_seen FROM installs"
                      " WHERE key = ? ORDER BY last_seen DESC"), (key,))
        return [{"install": r[0], "first_seen": r[1], "last_seen": r[2]}
                for r in cur.fetchall()]
    return _run(work)


def release_install(install: str, key: str) -> bool:
    """Unbind one machine. True if there was one to unbind."""
    if not install_is_bound(install, key):
        return False
    execute("DELETE FROM installs WHERE install = ? AND key = ?", (install, key))
    return True
