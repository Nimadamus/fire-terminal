"""Fill notifications, bottom right.

A fill is the one event worth interrupting for: it is money that has already
moved, and it is the thing you want to see without having the window in front
of you. Everything else FIRE knows can wait for you to look.

Deliberately borderless, click to dismiss, and self expiring, so a run of fills
cannot bury the screen. They stack upwards from the bottom right corner and
never steal focus, because taking focus from whatever you are typing into is
worse than missing the toast.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

from fire.ui.theme import Font, Palette, Space

WIDTH, HEIGHT = 300, 78
MARGIN, GAP = 18, 10
LIFETIME_MS = 9000
MAX_VISIBLE = 4

_live: list["Toast"] = []


class Toast(tk.Toplevel):
    def __init__(self, root: tk.Misc, pal: Palette, title: str, body: str,
                 accent: Optional[str] = None) -> None:
        super().__init__(root)
        self.pal = pal
        self.overrideredirect(True)          # no title bar, no taskbar entry
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.97)
        except Exception:
            pass
        self.configure(bg=pal.rule)

        inner = tk.Frame(self, bg=pal.panel)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        stripe = tk.Frame(inner, bg=accent or pal.accent, width=4)
        stripe.pack(side="left", fill="y")

        text = tk.Frame(inner, bg=pal.panel)
        text.pack(side="left", fill="both", expand=True,
                  padx=(Space.md, Space.md), pady=Space.sm)
        tk.Label(text, text=title, bg=pal.panel, fg=accent or pal.accent,
                 font=Font.label, anchor="w").pack(fill="x")
        tk.Label(text, text=body, bg=pal.panel, fg=pal.text,
                 font=Font.data_sm, anchor="w", justify="left",
                 wraplength=WIDTH - 40).pack(fill="x", pady=(3, 0))

        for widget in (self, inner, text, *text.winfo_children()):
            widget.bind("<Button-1>", lambda _e: self.close())

        _live.append(self)
        _restack(root)
        self.after(LIFETIME_MS, self.close)

    def close(self) -> None:
        if self in _live:
            _live.remove(self)
        try:
            self.destroy()
        except Exception:
            pass
        try:
            _restack(self.master)
        except Exception:
            pass


def _restack(root: tk.Misc) -> None:
    """Newest at the bottom, older ones pushed up."""
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    x = screen_w - WIDTH - MARGIN
    for index, toast in enumerate(reversed(_live[-MAX_VISIBLE:])):
        y = screen_h - MARGIN - HEIGHT - index * (HEIGHT + GAP)
        try:
            toast.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")
        except Exception:
            pass
    # Anything beyond the visible cap is dropped rather than queued: a backlog
    # of stale fill popups is noise, and the Activity window has the full list.
    for extra in _live[:-MAX_VISIBLE]:
        try:
            extra.destroy()
        except Exception:
            pass
    del _live[:-MAX_VISIBLE]


def fill_toast(root: tk.Misc, pal: Palette, fill) -> None:
    """One filled trade, whoever placed it."""
    side = fill.side.value.upper()
    cost = fill.count * fill.price + fill.fee_dollars
    Toast(root, pal,
          f"FILLED  {side}",
          f"{fill.count} @ {fill.price:.2f}   ${cost:,.2f}\n{fill.ticker}",
          accent=pal.yes if side == "YES" else pal.no)
