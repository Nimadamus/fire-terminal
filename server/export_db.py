"""Copy every FIRE table out of the database into one dated JSON file.

    DATABASE_URL=... python server/export_db.py <output directory>

So the licences never exist only at one provider. Read only: it runs SELECTs
and nothing else. The URL comes from the environment and is never printed.
Keep the output out of git (it holds customer emails).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

TABLES = ("licences", "installs", "waitlist", "events")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url.startswith(("postgres://", "postgresql://")):
        print("DATABASE_URL is not set to a Postgres URL.")
        return 2
    import psycopg

    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    dump: dict = {"exported_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "tables": {}}
    with psycopg.connect(url, connect_timeout=20) as conn:
        conn.read_only = True
        for table in TABLES:
            exists = conn.execute("SELECT to_regclass(%s) IS NOT NULL",
                                  (f"public.{table}",)).fetchone()[0]
            if not exists:
                # Before the service's first start there are no tables yet.
                dump["tables"][table] = []
                dump.setdefault("absent", []).append(table)
                continue
            cur = conn.execute(f"SELECT * FROM {table} ORDER BY 1")
            cols = [c.name for c in cur.description]
            dump["tables"][table] = [dict(zip(cols, row)) for row in cur.fetchall()]

    path = out_dir / f"fire_db_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dump, indent=1, default=str), encoding="utf-8")
    tmp.replace(path)
    print(path.name, {t: len(r) for t, r in dump["tables"].items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
