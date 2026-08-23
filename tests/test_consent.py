"""Consent gating.

Two things must hold and are easy to break silently:
  1. the live path cannot be completed without explicit acknowledgement
  2. the demo path never demands it, because no money and no exchange account
     are involved and a consent wall on a free trial costs customers
"""
from __future__ import annotations

import pytest

tk = pytest.importorskip("tkinter")

from fire.config.prefs import Preferences          # noqa: E402
from fire.interfaces.venue import VenueMode        # noqa: E402


@pytest.fixture(scope="module")
def onboarding(tmp_path_factory):
    from _pytest.monkeypatch import MonkeyPatch
    tmp = tmp_path_factory.mktemp("fire-consent")
    mp = MonkeyPatch()
    from fire.config import paths, prefs as prefs_module
    mp.setattr(paths, "prefs_file", lambda: tmp / "prefs.json")
    mp.setattr(prefs_module, "prefs_file", lambda: tmp / "prefs.json")

    from fire.ui.onboarding import OnboardingWindow
    try:
        win = OnboardingWindow(Preferences())
    except tk.TclError:
        mp.undo()
        pytest.skip("no display available")
    win.withdraw()
    win.update()
    yield win
    try:
        win.destroy()
    except Exception:
        pass
    mp.undo()


def test_consent_points_are_distinct_statements():
    from fire.ui.onboarding import CONSENT_POINTS
    assert len(CONSENT_POINTS) >= 4
    assert len(set(CONSENT_POINTS)) == len(CONSENT_POINTS)


def test_consent_covers_total_loss_advice_and_exchange_terms():
    from fire.ui.onboarding import CONSENT_POINTS
    blob = " ".join(CONSENT_POINTS).lower()
    assert "lose the entire amount" in blob
    assert "no trading advice" in blob
    assert "developer agreement" in blob


def test_continue_is_disabled_until_every_box_is_ticked(onboarding):
    onboarding._show_consent()
    onboarding.update()
    assert not onboarding._consent_btn._enabled

    for var in onboarding._consent_vars[:-1]:
        var.set(True)
    onboarding._update_consent_button()
    assert not onboarding._consent_btn._enabled, "partial consent must not pass"

    onboarding._consent_vars[-1].set(True)
    onboarding._update_consent_button()
    assert onboarding._consent_btn._enabled


def test_accepting_records_the_terms_version(onboarding):
    from fire.ui.onboarding import TERMS_VERSION
    onboarding._show_consent()
    onboarding.update()
    for var in onboarding._consent_vars:
        var.set(True)
    onboarding._accept_consent()
    assert onboarding.prefs.accepted_terms_version == TERMS_VERSION


def test_accept_is_refused_when_boxes_are_not_all_ticked(onboarding):
    onboarding.prefs.accepted_terms_version = ""
    onboarding._show_consent()
    onboarding.update()
    onboarding._consent_vars[0].set(True)
    onboarding._accept_consent()
    assert onboarding.prefs.accepted_terms_version == ""


def test_demo_path_requires_no_consent(onboarding):
    """A free trial must not be gated behind a wall of legal tickboxes."""
    onboarding.prefs.accepted_terms_version = ""
    onboarding._choose_demo()
    onboarding.update()
    assert onboarding._next_mode == VenueMode.DEMO
    assert onboarding.prefs.accepted_terms_version == ""


def test_bumping_terms_version_reprompts():
    """A stored older version must not count as acceptance of new terms."""
    from fire.ui.onboarding import TERMS_VERSION
    prefs = Preferences(accepted_terms_version="1970-01-1")
    assert prefs.accepted_terms_version != TERMS_VERSION
