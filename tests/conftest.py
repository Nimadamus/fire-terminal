"""Shared test setup.

The licence service tests run on SQLite by default. Set FIRE_TEST_DATABASE_URL
to a throwaway Postgres and the same tests run against Postgres instead, which
is what production uses. Never point it at a database that holds real data:
every table is dropped first.
"""
from __future__ import annotations

import os

TEST_PG = os.environ.get("FIRE_TEST_DATABASE_URL", "").strip()


def use_test_database(sqlite_path: str) -> None:
    """Point the service at a clean database for one test module."""
    os.environ.pop("RENDER", None)
    os.environ.pop("FIRE_ENV", None)
    os.environ["FIRE_DB"] = sqlite_path
    if not TEST_PG:
        os.environ.pop("DATABASE_URL", None)
        return
    from target_guard import assert_safe
    assert_safe(TEST_PG)                # never production, before any DROP
    os.environ["DATABASE_URL"] = TEST_PG
    import psycopg
    with psycopg.connect(TEST_PG) as conn:
        for table in ("installs", "events", "waitlist", "licences"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
