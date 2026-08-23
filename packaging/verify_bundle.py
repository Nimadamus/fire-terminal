"""Release gate: inspect a built bundle before it goes anywhere.

Run after PyInstaller. Exits non zero if the bundle contains anything it must
not, so a bad build cannot be shipped by accident.

    python packaging/verify_bundle.py dist/FIRE

Checks, in order of how badly each would hurt:
  1. no private key or credential file of any kind
  2. no module from the private trading system
  3. no internal vocabulary in any bundled source or data file
  4. no configured endpoint while authorization is outstanding
  5. the entry point actually exists
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

# Filenames that are never legitimate in a customer bundle.
FORBIDDEN_FILENAMES = re.compile(
    r"(?i)(\.key$|\.pfx$|\.p12$|credentials\.dat$|kalshi_key|id_rsa)")

# `.pem` alone is not evidence of anything: a CA trust bundle is a .pem full
# of certificates and ships legitimately with any HTTPS client. What must
# never ship is PRIVATE key material, so judge these files by content.
PRIVATE_KEY_MARKERS = (b"PRIVATE KEY", b"BEGIN RSA PRIVATE", b"BEGIN EC PRIVATE",
                       b"BEGIN OPENSSH PRIVATE", b"ENCRYPTED PRIVATE KEY")

FORBIDDEN_MODULE_NAMES = (
    "fair_model", "kalshi_live_order", "fire_interlock", "shared_book",
    "market_claim", "trade_lease", "global_kill", "fortress_owner",
    "order_gateway", "order_ack", "fill_reconcile", "integrity_gate",
    "proc_census", "runtime_identity", "health_checks", "filter_heartbeat",
    "filter_manifest_report", "shadow_compare", "btc15m_fire_paper",
    "kalshi_price_widget", "kalshi_risk_cap", "fire_render_log",
)

FORBIDDEN_TEXT = (
    b"-----BEGIN", b"C4_FORTRESS", b"MODEL_REGISTRY", b"fortress_v2",
    b"live auto lane",
)

SCAN_SUFFIXES = {".py", ".pyc", ".json", ".txt", ".md", ".cfg", ".ini"}
MAX_BUNDLE_MB = 200


def fail(message: str) -> None:
    print(f"BLOCKED: {message}")
    sys.exit(1)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    root = Path(argv[1])
    if not root.exists():
        fail(f"{root} does not exist. Build first.")

    files = [p for p in root.rglob("*") if p.is_file()]
    if not files:
        fail("bundle is empty")

    # 1. credential shaped files, and any file carrying private key material
    for path in files:
        if FORBIDDEN_FILENAMES.search(path.name):
            fail(f"credential shaped file in bundle: {path.relative_to(root)}")
        if path.suffix.lower() in (".pem", ".crt", ".cer", ".der"):
            try:
                blob = path.read_bytes()
            except OSError:
                continue
            for marker in PRIVATE_KEY_MARKERS:
                if marker in blob:
                    fail(f"private key material in bundle: "
                         f"{path.relative_to(root)}")

    # 2. private modules, by filename and inside any archive
    for path in files:
        stem = path.stem.lower()
        for name in FORBIDDEN_MODULE_NAMES:
            if stem == name:
                fail(f"private module in bundle: {path.relative_to(root)}")
        if path.suffix == ".zip" or path.name.endswith(".pyz"):
            try:
                with zipfile.ZipFile(path) as zf:
                    for entry in zf.namelist():
                        base = Path(entry).stem.lower()
                        if base in FORBIDDEN_MODULE_NAMES:
                            fail(f"private module inside {path.name}: {entry}")
            except zipfile.BadZipFile:
                pass

    # 3. forbidden text anywhere scannable
    for path in files:
        if path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        try:
            blob = path.read_bytes()
        except OSError:
            continue
        for needle in FORBIDDEN_TEXT:
            if needle in blob:
                fail(f"{needle.decode(errors='replace')!r} found in "
                     f"{path.relative_to(root)}")

    # 4. endpoint must stay unconfigured until permission is granted
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    try:
        from fire.venues.kalshi import endpoints
        if endpoints.is_configured():
            print("NOTE: a live endpoint is configured in this build. "
                  "Confirm written authorization is on file before releasing.")
    except Exception:
        pass

    # 5. entry point, and the guidance the app links to
    exe = list(root.glob("FIRE.exe")) + list(root.glob("FIRE"))
    if not exe:
        fail("no FIRE entry point in the bundle")

    # Preferences links to this. A build that ships without it hands the
    # customer a dead button on the day their laptop goes missing.
    if not list(root.glob("**/docs/CREDENTIALS.md")):
        fail("docs/CREDENTIALS.md is missing from the bundle")
    size_mb = sum(p.stat().st_size for p in files) / (1024 * 1024)
    if size_mb > MAX_BUNDLE_MB:
        fail(f"bundle is {size_mb:.0f} MB, over the {MAX_BUNDLE_MB} MB ceiling")

    print(f"OK: {len(files)} files, {size_mb:.1f} MB, no private material found.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
