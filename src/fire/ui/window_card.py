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


class TradeRow(tk.Frame):
    """One filled trade, written the way a person reads it.

    A trade is four separate facts, so it gets four columns rather than one
    run-on line: what was bought, how much of it and at what price, what it
    cost, and what it pays. The label above each number says what the number
    is, so nothing has to be decoded.
    """

    def __init__(self, parent, pal: Palette) -> None:
        super().__init__(parent, bg=pal.rule, highlightthickness=0)
        self.pal = pal

        body = tk.Frame(self, bg=pal.panel_hi)
        body.pack(fill="both", expand=True, padx=1, pady=1)

        # A colour bar down the side: which way the trade went, readable
        # before a single word is.
        self.bar = tk.Frame(body, bg=pal.accent, width=6)
        self.bar.pack(side="left", fill="y")

        grid = tk.Frame(body, bg=pal.panel_hi, padx=Space.md, pady=Space.sm)
        grid.pack(side="left", fill="both", expand=True)
        for column, weight in ((0, 0), (1, 1), (2, 1), (3, 1)):
            grid.grid_columnconfigure(column, weight=weight, uniform="trade")

        # -- market and side, the headline of the row
        head = tk.Frame(grid, bg=pal.panel_hi)
        head.grid(row=0, column=0, rowspan=2, sticky="w", padx=(0, Space.lg))
        self.coin = tk.Label(head, text="", bg=pal.panel_hi, fg=pal.text,
                             font=(Font.heading[0], 26, "bold"), anchor="w")
        self.coin.pack(anchor="w")
        self.side = tk.Label(head, text="", bg=pal.accent, fg="#FFFFFF",
                             font=(Font.heading[0], 12, "bold"),
                             padx=10, pady=1)
        self.side.pack(anchor="w", pady=(2, 0))

        self.size_value = self._column(grid, 1, "BOUGHT", pal.text)
        self.stake_value = self._column(grid, 2, "AMOUNT INVESTED", pal.text)
        self.profit_value = self._column(grid, 3, "PROFIT IF SUCCESSFUL",
                                         pal.good)

    def _column(self, grid, column: int, caption: str, fg: str) -> tk.Label:
        p = self.pal
        tk.Label(grid, text=caption, bg=p.panel_hi, fg=p.text_faint,
                 font=(Font.heading[0], 11, "bold"), anchor="w").grid(
                     row=0, column=column, sticky="w")
        value = tk.Label(grid, text="", bg=p.panel_hi, fg=fg,
                         font=(Font.data[0], 18, "bold"), anchor="w")
        value.grid(row=1, column=column, sticky="w", pady=(1, 0))
        return value

    # -- data ---------------------------------------------------------------
    def show(self, r: dict) -> None:
        p = self.pal
        side = r["side"].upper()
        colour = p.yes if side == "YES" else p.no
        self.bar.configure(bg=colour)
        self.coin.configure(text=r["coin"])
        self.side.configure(text=side, bg=colour)
        contracts = f"{r['contracts']:g}"
        self.size_value.configure(
            text=f"{contracts} contracts at {r['price'] * 100:.2f}¢")
        self.stake_value.configure(text=f"${r['stake']:,.2f}")
        self.profit_value.configure(text=f"+${r['profit']:,.2f}")
        self.pack(fill="x", pady=(0, Space.sm))

    def hide(self) -> None:
        self.pack_forget()


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

        self.rows_host = tk.Frame(box, bg=p.panel)
        self.rows_host.pack(fill="x")

        self.rows = [TradeRow(self.rows_host, p) for _ in range(MAX_POSITIONS)]

        self.stake = tk.Label(box, text="TOTAL INVESTED  $0.00", bg=p.panel,
                              fg=p.text_faint, font=(Font.data[0], 16, "bold"))
        self.stake.pack(pady=(Space.md, 0))
        self.profit = tk.Label(box, text="TOTAL PROFIT IF CORRECT  +$0.00", bg=p.panel,
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
                row.hide()
            self.stake.configure(text="TOTAL INVESTED  $0.00", fg=p.text_faint)
            self.profit.configure(text="TOTAL PROFIT IF CORRECT  +$0.00", fg=p.text_faint)
            self.foot.configure(text="waiting for a fill")
            return

        # When something is held, the coin is the headline, not the count.
        held = "  +  ".join(f"{r['coin']} {r['side'].upper()}"
                            for r in rows[:MAX_POSITIONS])
        self.count.configure(
            text=f"{min(len(rows), MAX_POSITIONS)}/{MAX_POSITIONS}  ·  {held}",
            font=(Font.heading[0], 19, "bold"),
            fg=p.good if len(rows) >= MAX_POSITIONS else p.accent)

        # Hidden first, then shown in order, so a swap in ranking cannot
        # leave the second trade packed above the first.
        for row in self.rows:
            row.hide()
        for index, row in enumerate(self.rows):
            if index < len(rows):
                row.show(rows[index])

        total_stake = sum(r["stake"] for r in rows)
        total_profit = sum(r["profit"] for r in rows)
        total_ct = sum(r["contracts"] for r in rows)
        self.stake.configure(
            text=f"TOTAL INVESTED  ${total_stake:,.2f}  ·  {total_ct:g} contracts",
            fg=p.text)
        self.profit.configure(text=f"TOTAL PROFIT IF CORRECT  +${total_profit:,.2f}",
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
