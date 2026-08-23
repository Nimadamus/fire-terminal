"""Small reusable widgets. Plain tkinter, themed by hand."""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from fire.ui.theme import Font, Palette, Space


class FlatButton(tk.Frame):
    """A button that actually looks interactive, with hover and disabled states."""

    def __init__(self, parent, text: str, command: Callable[[], None],
                 pal: Palette, *, bg: str, fg: str = "#FFFFFF",
                 hover: Optional[str] = None, font=None, pady: int = 9,
                 padx: int = 10, **kw):
        super().__init__(parent, bg=bg, highlightthickness=0, **kw)
        self._pal, self._bg = pal, bg
        self._hover = hover or bg
        self._enabled = True
        self._command = command
        self._label = tk.Label(self, text=text, bg=bg, fg=fg,
                               font=font or Font.button, pady=pady, padx=padx,
                               cursor="hand2")
        self._label.pack(fill="both", expand=True)
        for w in (self, self._label):
            w.bind("<Button-1>", self._click)
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)

    def _click(self, _evt=None):
        if self._enabled:
            self._command()

    def _enter(self, _evt=None):
        if self._enabled:
            self.configure(bg=self._hover)
            self._label.configure(bg=self._hover)

    def _leave(self, _evt=None):
        if self._enabled:
            self.configure(bg=self._bg)
            self._label.configure(bg=self._bg)

    def set_text(self, text: str) -> None:
        self._label.configure(text=text)

    def set_enabled(self, on: bool) -> None:
        self._enabled = on
        bg = self._bg if on else self._pal.panel_hi
        fg = "#FFFFFF" if on else self._pal.text_faint
        self.configure(bg=bg)
        self._label.configure(bg=bg, fg=fg, cursor="hand2" if on else "arrow")


class Badge(tk.Label):
    def __init__(self, parent, text: str, pal: Palette, colour: str, **kw):
        super().__init__(parent, text=f" {text} ", bg=colour, fg="#FFFFFF",
                         font=Font.label, padx=6, pady=2, **kw)


class Card(tk.Frame):
    """A panel surface with a hairline border."""

    def __init__(self, parent, pal: Palette, **kw):
        super().__init__(parent, bg=pal.rule, highlightthickness=0, **kw)
        self.inner = tk.Frame(self, bg=pal.panel)
        self.inner.pack(fill="both", expand=True, padx=1, pady=1)


def hrule(parent, pal: Palette, pad: int = Space.sm) -> tk.Frame:
    f = tk.Frame(parent, bg=pal.rule_soft, height=1)
    f.pack(fill="x", pady=pad)
    return f


def kv_row(parent, pal: Palette, key: str, value: str = "",
           value_font=None, value_fg: Optional[str] = None) -> tk.Label:
    row = tk.Frame(parent, bg=pal.panel)
    row.pack(fill="x")
    tk.Label(row, text=key, bg=pal.panel, fg=pal.text_faint,
             font=Font.data_sm).pack(side="left")
    lbl = tk.Label(row, text=value, bg=pal.panel, fg=value_fg or pal.text_dim,
                   font=value_font or Font.data)
    lbl.pack(side="right")
    return lbl


def american_odds(price: float) -> str:
    """Decimal probability to American odds, for traders who read them that way."""
    p = min(0.9999, max(0.0001, price))
    if p >= 0.5:
        return f"-{round(p / (1 - p) * 100):d}"
    return f"+{round((1 - p) / p * 100):d}"
