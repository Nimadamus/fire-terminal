"""Visual tokens for the FIRE terminal.

One place for every colour, size and font so the product reads as designed
rather than assembled. Deliberately not the internal tool's palette.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    ground: str
    panel: str
    panel_hi: str
    rule: str
    rule_soft: str
    text: str
    text_dim: str
    text_faint: str
    accent: str
    accent_dim: str
    yes: str
    yes_hi: str
    no: str
    no_hi: str
    good: str
    warn: str
    bad: str
    demo: str
    live: str


DARK = Palette(
    ground="#0B0E13", panel="#141920", panel_hi="#1B2129",
    rule="#262E38", rule_soft="#1D242C",
    text="#E6EBF2", text_dim="#96A1AF", text_faint="#5F6975",
    accent="#E3A544", accent_dim="#8A6520",
    yes="#2FA36B", yes_hi="#38BE7D", no="#C9524A", no_hi="#DC6058",
    good="#2FA36B", warn="#D9A441", bad="#DC6058",
    demo="#4E8FD0", live="#C9524A",
)

LIGHT = Palette(
    ground="#F2F4F7", panel="#FFFFFF", panel_hi="#E9EDF2",
    rule="#D5DBE3", rule_soft="#E6EAEF",
    text="#131922", text_dim="#4E5866", text_faint="#7E8896",
    accent="#A6720C", accent_dim="#E8D6AF",
    yes="#1B7D50", yes_hi="#176B45", no="#A93B33", no_hi="#93312A",
    good="#1B7D50", warn="#8A6410", bad="#A93B33",
    demo="#2C6494", live="#A93B33",
)


def palette(name: str = "dark") -> Palette:
    return LIGHT if name == "light" else DARK


# -- type ------------------------------------------------------------------
if sys.platform == "win32":
    UI_FACE, MONO_FACE = "Segoe UI", "Consolas"
elif sys.platform == "darwin":
    UI_FACE, MONO_FACE = "SF Pro Text", "SF Mono"
else:
    UI_FACE, MONO_FACE = "DejaVu Sans", "DejaVu Sans Mono"


class Font:
    title = (UI_FACE, 15, "bold")
    heading = (UI_FACE, 11, "bold")
    body = (UI_FACE, 10)
    small = (UI_FACE, 9)
    micro = (UI_FACE, 8)
    label = (UI_FACE, 8, "bold")
    price = (MONO_FACE, 21, "bold")
    price_sm = (MONO_FACE, 13, "bold")
    data = (MONO_FACE, 9)
    data_sm = (MONO_FACE, 8)
    button = (UI_FACE, 10, "bold")


# -- spacing ---------------------------------------------------------------
class Space:
    xs, sm, md, lg, xl = 3, 6, 10, 16, 24


CARD_W, CARD_H = 330, 340
