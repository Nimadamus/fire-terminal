"""Refuse to run destructive tests against anything that could be production.

The Postgres test runs drop every FIRE table first. They may only ever touch a
throwaway database, so before any of them connects this checks, in order:

  1. the URL is not the production URL (if that file exists on this machine)
  2. the database is local (127.0.0.1 / localhost), or its NAME ends in _dev
     or _test. Production's database is named without either suffix.
  3. the database does not carry the production marker table. The live
     migration writes fire_target = 'production' into Neon main, so even a
     copy of main under another name is refused.

Any failure raises before a single statement that changes anything is run.
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

PROD_URL_FILE = Path.home() / ".secrets" / "fire_neon_prod_url.txt"


class UnsafeTarget(RuntimeError):
    pass


def describe(url: str) -> str:
    """host/dbname only, for messages. Never the user or password."""
    parts = urlsplit(url)
    return f"{parts.hostname}/{parts.path.lstrip('/')}"


def assert_safe(url: str) -> None:
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme not in ("postgres", "postgresql"):
        raise UnsafeTarget("not a Postgres URL")
    if PROD_URL_FILE.exists() and PROD_URL_FILE.read_text().strip() == url:
        raise UnsafeTarget("this is the production database URL")
    host = (parts.hostname or "").lower()
    dbname = parts.path.lstrip("/").lower()
    local = host in ("127.0.0.1", "localhost", "::1")
    if not local and not dbname.endswith(("_dev", "_test")):
        raise UnsafeTarget(f"{describe(url)}: remote database name must end in _dev or _test")

    import psycopg
    with psycopg.connect(url, connect_timeout=20) as conn:
        row = conn.execute(
            "SELECT to_regclass('public.fire_target') IS NOT NULL").fetchone()
        if row and row[0]:
            target = conn.execute("SELECT env FROM fire_target LIMIT 1").fetchone()
            if not target or str(target[0]) != "dev":
                raise UnsafeTarget(f"{describe(url)} is marked {target!r}, not dev")
        elif not local:
            # First use of a remote dev database: mark it, so it can be told
            # apart from production forever after.
            conn.execute("CREATE TABLE fire_target (env TEXT NOT NULL)")
            conn.execute("INSERT INTO fire_target (env) VALUES ('dev')")
