"""Storage for licences and the installs bound to them.

Deliberately not an ORM. There are three tables and about a dozen queries, and
a dependency that has to be upgraded in lockstep with a payments integration is
not worth the typing it saves.

Runs on SQLite by default so the service can be developed and tested with no
infrastructure at all, and on Postgres when DATABASE_URL is set, which is what
it should run on in production. The only difference between them that matters
here is the placeholder character.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterable, Optional

DATABASE_URL = os.environ.get("DATABASE_URL", "")
SQLITE_PATH = os.environ.get("FIRE_DB", "fire_licences.db")

_lock = threading.RLock()


def _is_postgres() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))


def _placeholder() -> str:
    return "%s" if _is_postgres() else "?"


@contextmanager
def connect():
    """One connection per call. Cheap, and it avoids every pooling question."""
    if _is_postgres():
        import psycopg
        conn = psycopg.connect(DATABASE_URL)
    else:
        conn = sqlite3.connect(SQLITE_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
    CREATE TABLE IF NOT EXISTS events (
        id      TEXT PRIMARY KEY,
        kind    TEXT NOT NULL,
        seen    DOUBLE PRECISION NOT NULL
    )
    """,
)


def init() -> None:
    with _lock, connect() as conn:
        cur = conn.cursor()
        for statement in SCHEMA:
            cur.execute(statement)


def _rows(cur) -> list[tuple]:
    return list(cur.fetchall())


def execute(sql: str, params: Iterable[Any] = ()) -> None:
    with _lock, connect() as conn:
        conn.cursor().execute(q(sql), tuple(params))


def fetchone(sql: str, params: Iterable[Any] = ()) -> Optional[tuple]:
    with _lock, connect() as conn:
        cur = conn.cursor()
        cur.execute(q(sql), tuple(params))
        row = cur.fetchone()
        return tuple(row) if row else None


# -- licences --------------------------------------------------------------
LICENCE_COLUMNS = ("key", "email", "plan", "status", "expires", "seats",
                   "stripe_customer", "stripe_sub", "checkout_session", "created")


def create_licence(key: str, email: str, plan: str, expires: Optional[float],
                   stripe_customer: str = "", stripe_sub: str = "",
                   checkout_session: str = "", seats: int = 3) -> None:
    execute(
        "INSERT INTO licences (key, email, plan, status, expires, seats,"
        " stripe_customer, stripe_sub, checkout_session, created)"
        " VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)",
        (key, email, plan, expires, seats, stripe_customer, stripe_sub,
         checkout_session, time.time()))


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


def set_status(key: str, status: str, expires: Optional[float] = None) -> None:
    if expires is None:
        execute("UPDATE licences SET status = ? WHERE key = ?", (status, key))
    else:
        execute("UPDATE licences SET status = ?, expires = ? WHERE key = ?",
                (status, expires, key))


# -- installs --------------------------------------------------------------
def bind_install(install: str, key: str) -> None:
    now = time.time()
    if fetchone("SELECT 1 FROM installs WHERE install = ? AND key = ?",
                (install, key)):
        execute("UPDATE installs SET last_seen = ? WHERE install = ? AND key = ?",
                (now, install, key))
        return
    execute("INSERT INTO installs (install, key, first_seen, last_seen)"
            " VALUES (?, ?, ?, ?)", (install, key, now, now))


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
    """True if this Stripe event was already handled.

    Stripe retries, and it can deliver the same event more than once. Creating
    two licences for one purchase is the kind of mistake a customer notices.
    """
    if fetchone("SELECT 1 FROM events WHERE id = ?", (event_id,)):
        return True
    execute("INSERT INTO events (id, kind, seen) VALUES (?, ?, ?)",
            (event_id, kind, time.time()))
    return False
