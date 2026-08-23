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


def build_session(mode: str) -> Session:
    entitlement = LocalEntitlement()
    if mode == VenueMode.LIVE:
        from fire.venues.kalshi.venue import build_live_venue
        venue = build_live_venue(CredentialStore())
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


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    requested = None
    if "--demo" in argv:
        requested = VenueMode.DEMO
    elif "--live" in argv:
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

    try:
        session = build_session(mode)
    except FireError as exc:
        # Live is unavailable (no approved endpoint, or no credentials saved).
        # Demo always works, so fall back rather than refusing to start.
        logging.getLogger("fire").warning(
            "live venue unavailable (%s), falling back to demo",
            type(exc).__name__)
        session = build_session(VenueMode.DEMO)
        mode = VenueMode.DEMO

    session.connect()

    from fire.ui.main_window import MainWindow
    window = MainWindow(session, prefs, session._entitlement)
    window.protocol("WM_DELETE_WINDOW", window.on_close)
    window.mainloop()
    return 0
