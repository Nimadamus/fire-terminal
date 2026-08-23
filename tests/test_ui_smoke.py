"""UI construction smoke tests.

These do not assert on appearance. They assert that every window can actually
be built and torn down against a real session, which is what catches wiring
mistakes: a renamed attribute, a missing import, a callback pointing at
nothing. Those are invisible to the other suites because they only surface
when a window is opened.

Tkinter note: creating and destroying a Tk root repeatedly in one process
leaves Tcl in a state where the next root cannot initialise. So this module
builds exactly ONE root, shares it across the tests, and tears it down once.
Skipped automatically where there is no display.
"""
from __future__ import annotations

import time

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    """One MainWindow for the whole module. Built once, destroyed once."""
    from _pytest.monkeypatch import MonkeyPatch

    tmp = tmp_path_factory.mktemp("fire-ui")
    mp = MonkeyPatch()

    # keep the tests off the real user profile
    from fire.config import paths
    from fire.entitlement import local as local_mod
    mp.setattr(paths, "data_dir", lambda: tmp)
    mp.setattr(paths, "logs_dir", lambda: tmp)
    mp.setattr(paths, "prefs_file", lambda: tmp / "prefs.json")
    mp.setattr(paths, "entitlement_file", lambda: tmp / "ent.json")
    mp.setattr(local_mod, "entitlement_file", lambda: tmp / "ent.json")

    from fire.config.prefs import Preferences
    from fire.core.session import Session
    from fire.entitlement.local import LocalEntitlement
    from fire.interfaces.venue import VenueMode
    from fire.ui.main_window import MainWindow
    from fire.venues.demo.venue import DemoVenue

    venue = DemoVenue()
    session = Session(venue, VenueMode.DEMO, LocalEntitlement())
    session.connect()
    try:
        window = MainWindow(session, Preferences(), session._entitlement)
    except tk.TclError:
        session.disconnect()
        mp.undo()
        pytest.skip("no display available")

    window.withdraw()
    window.update()
    yield window

    try:
        session.disconnect()
        window.destroy()
    except Exception:
        pass
    mp.undo()


def _primed_card(app):
    """Populate the instrument map the refresh loop would have filled, then
    return a card that is actually pointing at a market."""
    app._instruments = {i.display: i
                        for i in app.session.market_data.instruments()}
    app.snapshot = app.session.account.snapshot()
    card = next(iter(app.cards.values()))
    card.refresh(time.time())
    assert card.ticker, "demo venue produced no tradeable instrument"
    return card


# -- structure -------------------------------------------------------------
def test_main_window_builds_and_paints(app):
    assert app.title().startswith("FIRE")
    assert len(app.cards) > 0
    app.update()


def test_main_window_shows_the_paper_banner(app):
    assert "PAPER" in app.banner.cget("text")
    assert "NO REAL ORDERS" in app.banner.cget("text")


def test_every_card_has_index_beat_and_gap(app):
    """The BEAT price is a first class element, not a footnote."""
    for card in app.cards.values():
        assert card.price.winfo_exists()
        assert card.strike.winfo_exists()
        assert card.gap.winfo_exists()


def test_beat_and_gap_populate_with_real_values(app):
    card = _primed_card(app)
    assert card.strike.cget("text") not in ("", "--")
    assert "above" in card.gap.cget("text") or "below" in card.gap.cget("text")


def test_cards_refresh_without_error(app):
    for card in app.cards.values():
        card.refresh(time.time())
    app.update()


# -- child windows ---------------------------------------------------------
def test_preferences_window_builds(app):
    from fire.ui.preferences_window import PreferencesWindow
    win = PreferencesWindow(app)
    win.update()
    win.destroy()


def test_account_window_builds(app):
    from fire.ui.account_window import AccountWindow
    win = AccountWindow(app)
    win.update()
    win.destroy()


def test_diagnostics_window_builds_and_shows_no_secrets(app):
    from fire.ui.diagnostics_window import DiagnosticsWindow
    win = DiagnosticsWindow(app)
    win.update()
    shown = win.text.get("1.0", "end")
    assert "-----" not in shown
    assert "BEGIN" not in shown
    win.destroy()


# -- the real order path ---------------------------------------------------
def test_placing_a_demo_order_from_the_ui_path(app):
    """Exercises the flow the BUY button actually calls, including risk."""
    from fire.core.models import Side
    card = _primed_card(app)
    app.risk.fraction, app.risk.enabled = 1.0, True
    before = app.session.account.snapshot().balance_dollars
    app.place_order(card, card.ticker, Side.YES, 25.0)
    app.update()
    assert app.session.account.snapshot().balance_dollars < before
    assert "Filled" in card.status.cget("text")


def test_risk_limit_blocks_an_oversized_order_in_the_ui(app):
    from fire.core.models import Side
    card = _primed_card(app)
    app.risk.fraction, app.risk.enabled = 0.001, True
    before = app.session.account.snapshot().balance_dollars
    app.place_order(card, card.ticker, Side.YES, 500.0)
    app.update()
    assert app.session.account.snapshot().balance_dollars == before
    assert "limit" in card.status.cget("text").lower()
    app.risk.fraction = 1.0


def test_a_bad_stake_entry_is_reported_not_raised(app):
    card = _primed_card(app)
    card.stake_var.set("not a number")
    card._buy(__import__("fire.core.models", fromlist=["Side"]).Side.YES)
    app.update()
    assert "dollars" in card.status.cget("text").lower()
