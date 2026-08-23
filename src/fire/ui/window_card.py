"""What filled in the window that is open right now.

Not a fill history. The question this answers is "what do we hold in THIS
fifteen minute window", so a fill from the previous window is not shown at all,
and the count resets to zero every time a new window opens. Showing yesterday's
fills under a live window is worse than showing nothing, because it reads as a
position you do not have.

Membership is decided by ticker: a fill counts only if its market is one of the
markets currently open on screen. That is exact and needs no clock arithmetic,
and it cannot drift out of step with the cards beside it.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

from fire.ui.theme import Font, Palette, Space
from fire.ui.widgets import Card

MAX_POSITIONS = 2

# Kalshi's own fee, so STAKE and IF CORRECT reconcile with a settled net
# rather than being a rough guess.
def _fee(price: float, contracts: float) -> float:
    return 0.07 * price * (1.0 - price) * contracts


class WindowCard(Card):
    """Bottom right: this window's fills, their stake and what they pay."""

    def __init__(self, parent, app) -> None:
        super().__init__(parent, app.pal)
        self.app, self.pal = app, app.pal
        self._build()

    def _build(self) -> None:
        p, box = self.pal, self.inner
        box.configure(padx=Space.lg, pady=Space.lg)

        tk.Label(box, text="THIS WINDOW", bg=p.panel, fg=p.accent,
                 font=(Font.heading[0], 17, "bold")).pack(pady=(2, 0))
        tk.Label(box, text="fills in the market open right now", bg=p.panel,
                 fg=p.text_faint, font=Font.small).pack(pady=(0, Space.md))

        self.count = tk.Label(box, text=f"0 / {MAX_POSITIONS} POSITIONS",
                              bg=p.panel, fg=p.text_faint,
                              font=(Font.heading[0], 26, "bold"))
        self.count.pack(pady=(Space.sm, Space.xs))

        tk.Frame(box, bg=p.rule, height=2).pack(fill="x", pady=Space.md)

        self.rows = []
        for _ in range(MAX_POSITIONS):
            row = tk.Label(box, text=" ", bg=p.panel, fg=p.text,
                           font=(Font.data[0], 12, "bold"), justify="left")
            row.pack(pady=(0, 3))
            self.rows.append(row)

        self.stake = tk.Label(box, text="STAKE  $0.00", bg=p.panel,
                              fg=p.text_faint, font=(Font.data[0], 16, "bold"))
        self.stake.pack(pady=(Space.md, 0))
        self.profit = tk.Label(box, text="IF CORRECT  +$0.00", bg=p.panel,
                               fg=p.text_faint, font=(Font.data[0], 16, "bold"))
        self.profit.pack()

        self.foot = tk.Label(box, text="waiting for a fill", bg=p.panel,
                             fg=p.text_faint, font=Font.small)
        self.foot.pack(pady=(Space.md, 2))

    # -- data ---------------------------------------------------------------
    def refresh(self, fills, open_tickers: set) -> None:
        p = self.pal
        rows = self._positions(fills, open_tickers)

        if not rows:
            self.count.configure(text=f"0 / {MAX_POSITIONS} POSITIONS",
                                 font=(Font.heading[0], 26, "bold"),
                                 fg=p.text_faint)
            for row in self.rows:
                row.configure(text=" ")
            self.stake.configure(text="STAKE  $0.00", fg=p.text_faint)
            self.profit.configure(text="IF CORRECT  +$0.00", fg=p.text_faint)
            self.foot.configure(text="waiting for a fill")
            return

        # When something is held, the coin is the headline, not the count.
        held = "  +  ".join(f"{r['coin']} {r['side'].upper()}"
                            for r in rows[:MAX_POSITIONS])
        self.count.configure(
            text=f"{min(len(rows), MAX_POSITIONS)}/{MAX_POSITIONS}  ·  {held}",
            font=(Font.heading[0], 19, "bold"),
            fg=p.good if len(rows) >= MAX_POSITIONS else p.accent)

        for index, row in enumerate(self.rows):
            if index < len(rows):
                r = rows[index]
                row.configure(
                    text=(f"{r['coin']} {r['side'].upper()}   {r['contracts']:g} ct"
                          f"  @ {r['price'] * 100:.1f}¢"
                          f"   ${r['stake']:,.2f}  →  +${r['profit']:,.2f}"),
                    fg=p.text)
            else:
                row.configure(text=" ")

        total_stake = sum(r["stake"] for r in rows)
        total_profit = sum(r["profit"] for r in rows)
        total_ct = sum(r["contracts"] for r in rows)
        self.stake.configure(
            text=f"STAKE  ${total_stake:,.2f}  ·  {total_ct:g} ct", fg=p.text)
        self.profit.configure(text=f"IF CORRECT  +${total_profit:,.2f}",
                              fg=p.good)
        self.foot.configure(text="settles at the close of this window")

    def _positions(self, fills, open_tickers: set) -> list[dict]:
        """Aggregate this window's fills per market and side."""
        agg: dict[tuple, dict] = {}
        for fill in fills or ():
            if fill.ticker not in open_tickers:
                continue                   # a different window: not ours
            price = float(fill.price or 0.0)
            if not 0.0 < price < 1.0:
                continue                   # no trustworthy fill price
            key = (fill.ticker, fill.side.value)
            entry = agg.setdefault(key, {"contracts": 0.0, "cost": 0.0,
                                         "ticker": fill.ticker,
                                         "side": fill.side.value})
            entry["contracts"] += fill.count
            entry["cost"] += fill.count * price

        rows = []
        for entry in agg.values():
            contracts = entry["contracts"]
            if contracts <= 0:
                continue
            price = entry["cost"] / contracts
            cost = entry["cost"]
            fee = _fee(price, contracts)
            # A binary pays one dollar a contract, so the profit on a win is
            # what it pays less what it cost less the fee.
            rows.append({
                "coin": _coin(entry["ticker"]),
                "side": entry["side"],
                "contracts": contracts,
                "price": price,
                "stake": cost,
                "profit": contracts - cost - fee,
            })
        rows.sort(key=lambda r: -r["stake"])
        return rows


def _coin(ticker: str) -> str:
    head = ticker.split("-")[0]
    return head.replace("KX", "").replace("15M", "") or ticker
