"""Crash capture, sanitized.

Rules:
  * a customer never sees a traceback. They see a plain apology, what was
    lost, and a way to send us the detail.
  * a traceback is the single most dangerous thing we write to disk, because
    local variables can be rendered into it. So every frame is scrubbed and
    every line passes through redaction before it touches a file.
  * a crash report is never transmitted automatically. It is written locally
    and only leaves the machine if the customer chooses to send a bundle.
"""
from __future__ import annotations

import logging
import sys
import threading
import time
import traceback
from pathlib import Path
from types import TracebackType
from typing import Optional, Type

from fire.config.paths import logs_dir
from fire.diagnostics.redact import assert_clean, redact_text
from fire.version import BUILD_CHANNEL, VERSION

log = logging.getLogger(__name__)

# Frame locals can hold a private key, a signer, or a credentials object.
# Never render them, and drop the frame's local scope entirely.
_SENSITIVE_FRAME_NAMES = ("credential", "signer", "auth", "key", "secret")


def _format(exc_type: Type[BaseException], exc: BaseException,
            tb: Optional[TracebackType]) -> str:
    """A traceback with no local variables and no argument values."""
    frames = traceback.extract_tb(tb) if tb else []
    lines = [
        f"FIRE {VERSION} ({BUILD_CHANNEL})",
        f"time  {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
        f"error {exc_type.__name__}",
        "",
        "traceback (most recent call last):",
    ]
    for frame in frames:
        name = Path(frame.filename).name
        sensitive = any(s in name.lower() or s in (frame.name or "").lower()
                        for s in _SENSITIVE_FRAME_NAMES)
        source = "<source withheld>" if sensitive else (frame.line or "")
        lines.append(f"  {name}:{frame.lineno} in {frame.name}")
        if source:
            lines.append(f"      {source}")
    # str(exc) can contain interpolated values, so it is redacted like the rest
    lines += ["", f"message: {exc}"]
    return redact_text("\n".join(lines))


def write_report(exc_type: Type[BaseException], exc: BaseException,
                 tb: Optional[TracebackType]) -> Optional[Path]:
    """Write a scrubbed crash report. Returns the path, or None if it could
    not be written safely."""
    try:
        text = _format(exc_type, exc, tb)
        assert_clean(text)
    except AssertionError:
        # Redaction could not guarantee the report was clean. Losing the
        # report is strictly better than leaking a credential.
        log.error("crash report suppressed: redaction could not be verified")
        return None
    except Exception:
        return None

    try:
        path = logs_dir() / f"crash-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}.log"
        path.write_text(text, encoding="utf-8")
        return path
    except OSError:
        return None


def install(on_crash=None) -> None:
    """Route uncaught exceptions, including those on worker threads."""

    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        path = write_report(exc_type, exc, tb)
        log.error("unhandled %s", exc_type.__name__)
        if on_crash is not None:
            try:
                on_crash(path)
            except Exception:
                pass

    sys.excepthook = _hook

    def _thread_hook(args) -> None:
        _hook(args.exc_type, args.exc_value, args.exc_traceback)

    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_hook
