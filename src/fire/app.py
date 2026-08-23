"""Application wiring. The only place that knows which concrete pieces exist.

Swapping the billing backend, adding a venue or changing the credential store
is a change to this file and nothing else.
"""
from __future__ import annotations

import logging
import sys

from fire.config import prefs as prefs_module
from fire.config.credentials import CredentialStore
from fire.config.paths import logs_dir
from fire.core.errors import FireError
from fire.core.session import Session
from fire.diagnostics.redact import redact_text
from fire.entitlement.local import LocalEntitlement
from fire.interfaces.venue import VenueMode
from fire.venues.demo.venue import DemoVenue
from fire.version import VERSION


class _RedactingFormatter(logging.Formatter):
    """Redaction happens at the write boundary. A secret that reaches a log
    file has already leaked, so we never rely on cleaning it up later."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


def _setup_logging() -> None:
    handler = logging.FileHandler(logs_dir() / "fire.log", encoding="utf-8")
    handler.setFormatter(_RedactingFormatter(
        "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    logging.getLogger("fire").info("FIRE %s starting", VERSION)


# Set by --view. A viewer install shows a real account and cannot trade.
VIEW_ONLY = False


def build_entitlement():
    """The licence service if this build has one, a local trial if not.

    This is the only place that decides. Everything above it sees one
    interface, so connecting billing changed no other file.
    """
    from fire.version import LICENCE_API_URL, LICENCE_PUBLIC_KEY
    if LICENCE_API_URL and LICENCE_PUBLIC_KEY:
        from fire.entitlement.remote import RemoteEntitlement
        return RemoteEntitlement(LICENCE_API_URL,
                                 LICENCE_PUBLIC_KEY.encode("ascii"))
    return LocalEntitlement()


def build_session(mode: str) -> Session:
    entitlement = build_entitlement()
    if mode == VenueMode.LIVE:
        from fire.venues.kalshi.venue import build_live_venue
        venue = build_live_venue(CredentialStore(), read_only=VIEW_ONLY)
    else:
        venue = DemoVenue()
    return Session(venue, venue.mode, entitlement)


def choose_mode(prefs, requested: str | None = None) -> str:
    """Demo unless the customer has explicitly set up a live account."""
    if requested in (VenueMode.DEMO, VenueMode.LIVE):
        return requested
    if prefs.last_mode == "live" and CredentialStore().has_credentials():
        return VenueMode.LIVE
    return VenueMode.DEMO


def _run(mode: str, prefs) -> str | None:
    """Open the terminal in one mode. Returns a mode to reopen in, or None."""
    try:
        session = build_session(mode)
    except FireError as exc:
        # Live is unavailable (no approved endpoint, or no credentials saved).
        # Demo always works, so fall back rather than refusing to start.
        logging.getLogger("fire").warning(
            "live venue unavailable (%s), falling back to demo",
            type(exc).__name__)
        session = build_session(VenueMode.DEMO)

    session.connect()

    from fire.ui.main_window import MainWindow
    window = MainWindow(session, prefs, session._entitlement)

    # Uncaught errors are written locally, scrubbed, and never shown raw.
    from fire.diagnostics import crash
    crash.install(on_crash=window.report_crash)

    if prefs.check_for_updates:
        from fire import updates
        updates.check_in_background(window.offer_update)

    window.protocol("WM_DELETE_WINDOW", window.on_close)
    window.mainloop()

    next_mode = window.restart_mode
    try:
        window.destroy()
    except Exception:
        pass
    session.disconnect()
    return next_mode


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    requested = None
    global VIEW_ONLY
    if "--view" in argv:
        VIEW_ONLY = True
    if "--demo" in argv:
        requested = VenueMode.DEMO
    elif "--live" in argv or VIEW_ONLY:
        requested = VenueMode.LIVE

    _setup_logging()
    prefs = prefs_module.load()

    # First run: let them choose demo or a real account before anything
    # connects. Closing the window means they did not consent to either.
    if not prefs.onboarding_complete and requested is None:
        from fire.ui.onboarding import run_onboarding
        chosen = run_onboarding(prefs)
        if chosen is None:
            return 0
        prefs = prefs_module.load()
        requested = chosen

    mode = choose_mode(prefs, requested)

    # A customer whose subscription lapses can drop to demo without restarting
    # FIRE by hand. Bounded so a wiring mistake cannot spin here forever.
    for _ in range(4):
        mode = _run(mode, prefs)
        if mode is None:
            return 0
        prefs = prefs_module.load()
    return 0
