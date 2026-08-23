"""Positions and fills in one place.

The cards show the position on the market you are looking at. This window
answers the other question: what do I hold altogether, and what did I actually
get filled at.

Two deliberate choices.

Cost and payout sit next to each other because that is the whole shape of a
binary contract. What you paid is what you can lose, what it pays is what you
can win, and showing one without the other tells half the story.

Resting orders are shown even though FIRE's own orders are immediate or cancel
and therefore never rest. The number comes from the exchange, so it covers
orders placed elsewhere in the same account, and a customer who sees a resting
order they did not place from FIRE needs to know it is there.
"""
from __future__ import annotations

import time
import tkinter as tk

from fire.core.errors import FireError
from fire.ui.theme import Font, Space
from fire.ui.widgets import FlatButton, hrule

REFRESH_MS = 1500
MAX_POSITIONS = 12
MAX_FILLS = 25


class ActivityWindow(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app, self.pal = app, app.pal
        p = self.pal

        self.title("FIRE  ·  Activity")
        self.configure(bg=p.ground)
        self.geometry("760x540")
        self.transient(app)

        head = tk.Frame(self, bg=p.panel)
        head.pack(fill="x")
        tk.Label(head, text="Activity", bg=p.panel, fg=p.text,
                 font=Font.title).pack(side="left", padx=Space.lg, pady=Space.md)
        self.mode_lbl = tk.Label(
            head, text="SIMULATED" if app.session.is_demo else "LIVE ACCOUNT",
            bg=p.panel, fg=p.demo if app.session.is_demo else p.live,
            font=Font.label)
        self.mode_lbl.pack(side="right", padx=Space.lg)

        body = tk.Frame(self, bg=p.ground)
        body.pack(fill="both", expand=True, padx=Space.lg, pady=Space.md)

        self.summary = tk.Label(body, text="", bg=p.ground, fg=p.text_dim,
                                font=Font.small, anchor="w")
        self.summary.pack(fill="x")

        hrule(body, p, pad=Space.sm)
        tk.Label(body, text="POSITIONS", bg=p.ground, fg=p.text_faint,
                 font=Font.label, anchor="w").pack(fill="x")
        self.pos_host = tk.Frame(body, bg=p.ground)
        self.pos_host.pack(fill="x", pady=(Space.xs, 0))

        hrule(body, p, pad=Space.md)
        tk.Label(body, text="RECENT FILLS", bg=p.ground, fg=p.text_faint,
                 font=Font.label, anchor="w").pack(fill="x")
        self.fill_host = tk.Frame(body, bg=p.ground)
        self.fill_host.pack(fill="both", expand=True, pady=(Space.xs, 0))

        foot = tk.Frame(self, bg=p.ground)
        foot.pack(fill="x", padx=Space.lg, pady=Space.md)
        self.note = tk.Label(foot, text="", bg=p.ground, fg=p.text_faint,
                             font=Font.small, anchor="w", wraplength=520,
                             justify="left")
        self.note.pack(side="left", fill="x", expand=True)
        FlatButton(foot, "Close", self.destroy, p, bg=p.panel_hi,
                   fg=p.text_dim, hover=p.rule).pack(side="right")

        self._closed = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.refresh()
        self.after(REFRESH_MS, self._tick)

    # -- tables -------------------------------------------------------------
    # Cells are gridded directly into the host, not packed into per row frames.
    # Columns only line up if every row shares one grid, and mixing fonts
    # between the header and the values makes character widths lie.
    COLUMNS = ((24, "w"), (6, "w"), (7, "e"), (9, "e"), (11, "e"), (11, "e"))

    def _table(self, host, header, rows, empty: str) -> None:
        p = self.pal
        for child in host.winfo_children():
            child.destroy()

        for col, (width, _anchor) in enumerate(self.COLUMNS):
            host.columnconfigure(col, minsize=0, weight=0)

        for col, text in enumerate(header):
            width, anchor = self.COLUMNS[col]
            tk.Label(host, text=text, bg=p.ground, fg=p.text_faint,
                     font=Font.data_sm, width=width, anchor=anchor).grid(
                         row=0, column=col, sticky="ew", pady=(0, 2))

        if not rows:
            tk.Label(host, text=empty, bg=p.ground, fg=p.text_faint,
                     font=Font.data_sm, anchor="w").grid(
                         row=1, column=0, columnspan=len(header), sticky="w")
            return

        for r, (cells, tone) in enumerate(rows, start=1):
            for col, text in enumerate(cells):
                width, anchor = self.COLUMNS[col]
                tk.Label(host, text=text, bg=p.ground, fg=tone,
                         font=Font.data_sm, width=width, anchor=anchor).grid(
                             row=r, column=col, sticky="ew")

    # -- data ---------------------------------------------------------------
    def refresh(self) -> None:
        try:
            snap = self.app.session.account.snapshot()
            fills = list(self.app.session.recent_fills())
        except FireError as exc:
            self.note.configure(text=f"{exc.title}. {exc.remedy}", fg=self.pal.warn)
            return
        except Exception:
            self.note.configure(text="Activity could not be read just now.",
                                fg=self.pal.warn)
            return

        p = self.pal
        positions = list(snap.positions)
        risked = sum(x.cost_dollars for x in positions)
        payout = sum(x.payout_if_correct for x in positions)
        self.summary.configure(
            text=f"Balance ${snap.balance_dollars:,.2f}    "
                 f"At risk ${risked:,.2f}    "
                 f"Pays ${payout:,.2f} if every position is correct    "
                 f"Resting orders {snap.resting_orders}"
                 + ("    (figures may be out of date)" if snap.stale else ""))

        self._table(
            self.pos_host,
            ("MARKET", "SIDE", "COUNT", "AVERAGE", "COST", "PAYOUT"),
            [((pos.ticker, pos.side.value.upper(), f"{pos.count}",
               f"{pos.average_price:.2f}", f"${pos.cost_dollars:,.2f}",
               f"${pos.payout_if_correct:,.2f}"),
              p.yes if pos.side.value == "yes" else p.no)
             for pos in positions[:MAX_POSITIONS]],
            "flat")

        self._table(
            self.fill_host,
            ("MARKET", "SIDE", "COUNT", "PRICE", "COST", "TIME"),
            [((fill.ticker, fill.side.value.upper(), f"{fill.count}",
               f"{fill.price:.2f}",
               f"${fill.count * fill.price + fill.fee_dollars:,.2f}",
               time.strftime("%H:%M:%S", time.localtime(fill.epoch))),
              p.yes if fill.side.value == "yes" else p.no)
             for fill in fills[:MAX_FILLS]],
            "no fills yet")

        # Never let a cap look like the whole picture.
        hidden = []
        if len(positions) > MAX_POSITIONS:
            hidden.append(f"{len(positions) - MAX_POSITIONS} more positions")
        if len(fills) > MAX_FILLS:
            hidden.append(f"{len(fills) - MAX_FILLS} older fills")
        self.note.configure(
            text=("Not shown here: " + " and ".join(hidden) +
                  ". Your exchange account has the full record."
                  if hidden else
                  "Your exchange account is the authoritative record."),
            fg=p.text_faint)

    # -- lifecycle ----------------------------------------------------------
    def _tick(self) -> None:
        if self._closed:
            return
        self.refresh()
        self.after(REFRESH_MS, self._tick)

    def _on_close(self) -> None:
        self._closed = True
        self.destroy()
