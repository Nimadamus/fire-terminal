"""Generate the update feed document for a release.

The feed is the only thing customers poll. It is a small static JSON file that
can sit on any static host, which is deliberate: the update path must not
depend on an application server we have to keep alive.

    python packaging/make_feed.py --url https://<host>/FIRE-1.0.0-setup.exe \
        --notes "What changed in one short line" > dist/updates.json

Publishing order matters. Upload the installer FIRST, confirm the URL
downloads, and only then replace updates.json. Doing it the other way round
points every customer at a file that does not exist yet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fire.version import BUILD_CHANNEL, VERSION      # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="public URL of the installer")
    ap.add_argument("--notes", default="", help="one short line, customer facing")
    ap.add_argument("--channel", default=BUILD_CHANNEL or "stable")
    ap.add_argument("--mandatory", action="store_true")
    ap.add_argument("--installer", default="",
                    help="local path to the installer, for the checksum")
    args = ap.parse_args()

    entry = {"version": VERSION, "url": args.url, "notes": args.notes,
             "mandatory": bool(args.mandatory)}

    # A checksum the customer can verify by hand, and that we can check against
    # what actually landed on the host. Cheap insurance against a truncated
    # upload being served to everyone.
    if args.installer:
        path = Path(args.installer)
        if not path.is_file():
            print(f"no installer at {path}", file=sys.stderr)
            return 1
        entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        entry["size_bytes"] = path.stat().st_size

    print(json.dumps({args.channel: entry}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
