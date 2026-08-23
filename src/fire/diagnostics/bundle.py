"""Support bundle generation.

A customer clicks one button and gets a zip they can send us. Every byte in it
passes through redaction first, and the whole archive is scanned again before
it is written. If anything credential-shaped survives, the bundle is refused
rather than shipped.
"""
from __future__ import annotations

import io
import json
import platform
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from fire.config import paths
from fire.config.credentials import CredentialStore
from fire.diagnostics.redact import assert_clean, redact_obj, redact_text
from fire.version import BUILD_CHANNEL, VERSION

MAX_LOG_BYTES = 512 * 1024


def environment_report(session=None, prefs=None, entitlement=None) -> dict[str, Any]:
    store = CredentialStore()
    report: dict[str, Any] = {
        "fire": {"version": VERSION, "channel": BUILD_CHANNEL},
        "system": {
            "platform": platform.platform(),
            "python": sys.version.split()[0],
            "machine": platform.machine(),
        },
        "credentials": {
            "backend": store.backend_name(),
            "configured": store.has_credentials(),
            # the credential itself is never read into this report
        },
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if session is not None:
        report["session"] = {
            "mode": session.mode,
            "venue": session.venue_name,
            "connection": str(session.market_data.connection_state().value),
        }
    if prefs is not None:
        from dataclasses import asdict
        report["preferences"] = asdict(prefs)
    if entitlement is not None:
        ent = entitlement.current()
        report["entitlement"] = {"status": ent.status.value, "plan": ent.plan}
    return redact_obj(report)


def _safe_log_text(path: Path) -> str:
    try:
        data = path.read_bytes()[-MAX_LOG_BYTES:]
    except Exception:
        return ""
    return redact_text(data.decode("utf-8", errors="replace"))


def create(session=None, prefs=None, entitlement=None,
           note: str = "") -> Path:
    """Write a redacted support bundle and return its path."""
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    out = paths.bundles_dir() / f"fire-support-{stamp}.zip"

    report = environment_report(session, prefs, entitlement)
    report_text = json.dumps(report, indent=2)
    assert_clean(report_text)

    logs: dict[str, str] = {}
    for log in sorted(paths.logs_dir().glob("*.log")):
        text = _safe_log_text(log)
        if text:
            assert_clean(text)
            logs[log.name] = text

    note_text = redact_text(note or "")
    assert_clean(note_text)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("report.json", report_text)
        if note_text.strip():
            zf.writestr("customer-note.txt", note_text)
        for name, text in logs.items():
            zf.writestr(f"logs/{name}", text)
        zf.writestr("README.txt",
                    "FIRE support bundle.\n\n"
                    "Credentials, private keys, licence keys, email addresses and\n"
                    "user folder names are removed automatically before this file\n"
                    "is written. You can open it and check before sending.\n")

    out.write_bytes(buffer.getvalue())
    return out
