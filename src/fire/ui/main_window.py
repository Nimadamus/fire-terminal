"""The FIRE terminal window."""
from __future__ import annotations

import time
import tkinter as tk
from tkinter import messagebox
from typing import Optional

from fire.config.prefs import Preferences, save as save_prefs
from fire.core.errors import FireError
from fire.core.models import ConnectionState, Side
from fire.core.session import Session
from fire.entitlement.policy import (
    short_suspension_reason, suspension_reason, trading_allowed,
)
from fire.entitlement.watch import EntitlementWatch
from fire.interfaces.entitlement import EntitlementStatus
from fire.interfaces.venue import VenueMode
from fire.risk.limits import RiskLimiter
from fire.ui.theme import CARD_H, CARD_W, Font, Space, palette
from fire.ui.widgets import Badge, Card, FlatButton, american_odds, hrule, kv_row
from fire.version import VERSION

REFRESH_MS = 400


class CoinCard(Card):
    """One market. Everything the customer needs to act, nothing else."""

    def __init__(self, parent, app: "MainWindow", code: str):
        super().__init__(parent, app.pal)
        self.app, self.code, self.pal = app, code, app.pal
        self.ticker: Optional[str] = None
        self._build()

    def _build(self) -> None:
        p, box = self.pal, self.inner
        box.configure(padx=Space.md, pady=Space.md)

        head = tk.Frame(box, bg=p.panel)
        head.pack(fill="x")
        tk.Label(head, text=self.code, bg=p.panel, fg=p.accent,
                 font=Font.heading).pack(side="left")
        self.clock = tk.Label(head, text="--:--", bg=p.panel, fg=p.text_faint,
                              font=Font.data)
        self.clock.pack(side="right")

        # INDEX is where the market is. BEAT is what it has to finish past.
        # Both are first class: the decision is the relationship between them.
        prices = tk.Frame(box, bg=p.panel)
        prices.pack(fill="x", pady=(Space.sm, 0))

        row_index = tk.Frame(prices, bg=p.panel)
        row_index.pack(fill="x")
        tk.Label(row_index, text="INDEX", bg=p.panel, fg=p.text_faint,
                 font=Font.label, width=6, anchor="w").pack(side="left")
        self.price = tk.Label(row_index, text="--", bg=p.panel, fg=p.text,
                              font=Font.price, anchor="w")
        self.price.pack(side="left")

        row_beat = tk.Frame(prices, bg=p.panel)
        row_beat.pack(fill="x")
        tk.Label(row_beat, text="BEAT", bg=p.panel, fg=p.accent,
                 font=Font.label, width=6, anchor="w").pack(side="left")
        self.strike = tk.Label(row_beat, text="--", bg=p.panel, fg=p.text_dim,
                               font=Font.price_sm, anchor="w")
        self.strike.pack(side="left")

        self.gap = tk.Label(box, text="", bg=p.panel, fg=p.text_faint,
                            font=Font.data_sm, anchor="w")
        self.gap.pack(fill="x", pady=(1, 0))

        hrule(box, p)

        odds = tk.Frame(box, bg=p.panel)
        odds.pack(fill="x")
        self.yes_odds = tk.Label(odds, text="YES --", bg=p.panel, fg=p.yes,
                                 font=Font.price_sm)
        self.yes_odds.pack(side="left")
        self.no_odds = tk.Label(odds, text="NO --", bg=p.panel, fg=p.no,
                                font=Font.price_sm)
        self.no_odds.pack(side="right")

        stake = tk.Frame(box, bg=p.panel)
        stake.pack(fill="x", pady=(Space.md, Space.xs))
        tk.Label(stake, text="$", bg=p.panel, fg=p.text_faint,
                 font=Font.body).pack(side="left")
        self.stake_var = tk.StringVar(value=f"{self.app.prefs.default_stake:.0f}")
        self.stake_entry = tk.Entry(
            stake, textvariable=self.stake_var, width=7, justify="left",
            bg=p.panel_hi, fg=p.text, insertbackground=p.text,
            relief="flat", font=Font.data, highlightthickness=1,
            highlightbackground=p.rule, highlightcolor=p.accent,
        )
        self.stake_entry.pack(side="left", padx=(3, Space.sm), ipady=4)

        presets = tk.Frame(box, bg=p.panel)
        presets.pack(fill="x")
        for amount in self.app.prefs.stake_presets[:5]:
            b = tk.Label(presets, text=f"{amount:g}", bg=p.panel_hi, fg=p.text_dim,
                         font=Font.data_sm, padx=6, pady=3, cursor="hand2")
            b.pack(side="left", padx=(0, 3))
            b.bind("<Button-1>", lambda _e, a=amount: self.stake_var.set(f"{a:g}"))

        self.limit_note = tk.Label(box, text="", bg=p.panel, fg=p.text_faint,
                                   font=Font.data_sm, anchor="w")
        self.limit_note.pack(fill="x", pady=(Space.sm, Space.sm))

        buttons = tk.Frame(box, bg=p.panel)
        buttons.pack(fill="x")
        self.buy_yes = FlatButton(buttons, "BUY YES", lambda: self._buy(Side.YES),
                                  p, bg=p.yes, hover=p.yes_hi)
        self.buy_yes.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.buy_no = FlatButton(buttons, "BUY NO", lambda: self._buy(Side.NO),
                                 p, bg=p.no, hover=p.no_hi)
        self.buy_no.pack(side="left", fill="x", expand=True, padx=(2, 0))

        hrule(box, p)
        self.position = kv_row(box, p, "position", "flat")
        self.status = tk.Label(box, text="", bg=p.panel, fg=p.text_faint,
                               font=Font.data_sm, anchor="w", wraplength=CARD_W - 30,
                               justify="left")
        self.status.pack(fill="x", pady=(Space.xs, 0))

    # -- actions -----------------------------------------------------------
    def _stake(self) -> Optional[float]:
        try:
            v = float(self.stake_var.get().replace("$", "").replace(",", "").strip())
        except ValueError:
            self._say("Enter an amount in dollars.", self.pal.warn)
            return None
        if v <= 0:
            self._say("Amount must be more than zero.", self.pal.warn)
            return None
        return v

    def set_trading_enabled(self, on: bool, reason: str = "") -> None:
        self.buy_yes.set_enabled(on)
        self.buy_no.set_enabled(on)
        self.stake_entry.configure(state="normal" if on else "disabled")
        if not on:
            self._say(reason or "Order entry is switched off.", self.pal.warn)
        elif self.status.cget("text") == reason:
            self._say("")

    def _buy(self, side: Side) -> None:
        # The buttons are already disabled, but a preset click or a stray key
        # binding must not find a second way in.
        if not self.app.trading_enabled:
            self._say(self.app.suspension_note or
                      "Order entry is switched off.", self.pal.warn)
            return
        if not self.ticker:
            self._say("This market is between windows.", self.pal.text_faint)
            return
        budget = self._stake()
        if budget is None:
            return
        self.app.place_order(self, self.ticker, side, budget)

    def _say(self, text: str, colour: Optional[str] = None) -> None:
        self.status.configure(text=text, fg=colour or self.pal.text_faint)

    # -- refresh -----------------------------------------------------------
    def refresh(self, now: float) -> None:
        app, p = self.app, self.pal
        md = app.session.market_data
        inst = app.instrument_for(self.code)
        if inst is None:
            self.ticker = None
            if app.trading_enabled:
                self._say("Waiting for the next window.")
            return
        self.ticker = inst.ticker

        q = md.index_quote(f"DEMO.{self.code}" if app.session.is_demo else self.code)
        digits = 2
        if q:
            digits = 2 if q.value >= 10 else (4 if q.value >= 0.5 else 5)
            self.price.configure(text=f"{q.value:,.{digits}f}")
        if inst.strike is not None:
            self.strike.configure(text=f"{inst.strike:,.{digits}f}")
            if q:
                gap = q.value - inst.strike
                above = gap >= 0
                self.price.configure(fg=p.yes if above else p.no)
                pct = (abs(gap) / inst.strike * 100.0) if inst.strike else 0.0
                self.gap.configure(
                    text=f"{'+' if above else '-'}{abs(gap):,.{digits}f}  "
                         f"({pct:.3f}%)  {'above' if above else 'below'}",
                    fg=p.yes if above else p.no,
                )

        left = inst.seconds_left(now)
        if left is not None:
            self.clock.configure(
                text=f"{int(left // 60):d}:{int(left % 60):02d}",
                fg=p.warn if left < 60 else p.text_faint,
            )

        book = md.book(inst.ticker)
        if book:
            ya, na = book.best(Side.YES), book.best(Side.NO)
            self.yes_odds.configure(
                text=f"YES {american_odds(ya.price)}" if ya else "YES --")
            self.no_odds.configure(
                text=f"NO {american_odds(na.price)}" if na else "NO --")
            if ya and na:
                self.limit_note.configure(
                    text=f"ask  yes {ya.price:.2f} x{ya.size}   no {na.price:.2f} x{na.size}")

        snap = app.snapshot
        held = [x for x in (snap.positions if snap else [])
                if x.ticker == inst.ticker]
        if held:
            pos = held[0]
            self.position.configure(
                text=f"{pos.count} {pos.side.value.upper()} @ {pos.average_price:.2f}",
                fg=p.text)
        else:
            self.position.configure(text="flat", fg=p.text_faint)


class MainWindow(tk.Tk):
    def __init__(self, session: Session, prefs: Preferences, entitlement) -> None:
        super().__init__()
        self.session, self.prefs, self.entitlement = session, prefs, entitlement
        self.pal = palette(prefs.theme)
        self.risk = RiskLimiter(prefs.max_loss_fraction, prefs.max_loss_enabled)
        self.snapshot = None
        self._instruments = {}
        self.cards: dict[str, CoinCard] = {}
        self.trading_enabled = True
        self.suspension_note = ""
        # Set when the customer asks to come back in another mode. `app.main`
        # reads it after the window closes and reopens there.
        self.restart_mode: Optional[str] = None
        self.watch = EntitlementWatch(entitlement) if entitlement else None

        self.title(f"FIRE {VERSION}")
        self.configure(bg=self.pal.ground)
        self.geometry("1400x900")
        self.minsize(920, 620)

        self._build_chrome()
        self._build_grid()
        self._apply_trading_state()
        # Only live sessions need the periodic check. In demo there is no order
        # to lose and no reason to keep a thread awake.
        if self.watch and self.session.is_live:
            self.watch.start()
        self.after(200, self._tick)

    # -- chrome ------------------------------------------------------------
    def _build_chrome(self) -> None:
        p = self.pal

        bar = tk.Frame(self, bg=p.panel, height=54)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        inner = tk.Frame(bar, bg=p.panel)
        inner.pack(fill="both", expand=True, padx=Space.lg)

        tk.Label(inner, text="FIRE", bg=p.panel, fg=p.text,
                 font=Font.title).pack(side="left", pady=Space.md)
        is_demo = self.session.is_demo
        Badge(inner, "DEMO" if is_demo else "LIVE", p,
              p.demo if is_demo else p.live).pack(side="left", padx=Space.md)

        right = tk.Frame(inner, bg=p.panel)
        right.pack(side="right")
        self.ent_lbl = tk.Label(right, text="", bg=p.panel, fg=p.text_faint,
                                font=Font.small, cursor="hand2")
        self.ent_lbl.pack(side="right", padx=(Space.md, 0))
        self.ent_lbl.bind("<Button-1>", lambda _e: self._open_account())
        FlatButton(right, "Activity", self._open_activity, p,
                   bg=p.panel_hi, fg=p.text_dim, hover=p.rule,
                   font=Font.small, pady=5).pack(side="right", padx=4)
        FlatButton(right, "Diagnostics", self._open_diagnostics, p,
                   bg=p.panel_hi, fg=p.text_dim, hover=p.rule,
                   font=Font.small, pady=5).pack(side="right", padx=4)
        FlatButton(right, "Preferences", self._open_preferences, p,
                   bg=p.panel_hi, fg=p.text_dim, hover=p.rule,
                   font=Font.small, pady=5).pack(side="right", padx=4)
        if is_demo:
            FlatButton(right, "Reset demo", self._reset_demo, p,
                       bg=p.panel_hi, fg=p.text_dim, hover=p.rule,
                       font=Font.small, pady=5).pack(side="right", padx=4)
        self.conn_lbl = tk.Label(right, text="", bg=p.panel, fg=p.text_faint,
                                 font=Font.small)
        self.conn_lbl.pack(side="right", padx=Space.md)
        self.bal_lbl = tk.Label(right, text="--", bg=p.panel, fg=p.text,
                                font=Font.price_sm)
        self.bal_lbl.pack(side="right")
        tk.Label(right, text="BALANCE", bg=p.panel, fg=p.text_faint,
                 font=Font.label).pack(side="right", padx=(0, Space.sm))

        # mode banner
        banner_bg = p.demo if is_demo else p.live
        self.banner = tk.Label(
            self,
            text=("PAPER  ·  SIMULATED ACCOUNT  ·  NO REAL ORDERS" if is_demo
                  else "LIVE  ·  REAL MONEY  ·  ORDERS ARE FINAL"),
            bg=banner_bg, fg="#FFFFFF", font=Font.label, pady=6)
        self.banner.pack(fill="x")

        # Shown only when order entry has been switched off. It carries the
        # reason and both ways out, so the customer is never just stuck.
        self.lapse_bar = tk.Frame(self, bg=p.panel_hi)
        row = tk.Frame(self.lapse_bar, bg=p.panel_hi)
        row.pack(fill="x", padx=Space.lg, pady=Space.sm)
        self.lapse_msg = tk.Label(row, text="", bg=p.panel_hi, fg=p.warn,
                                  font=Font.small, anchor="w", justify="left",
                                  wraplength=900)
        self.lapse_msg.pack(side="left", fill="x", expand=True)
        FlatButton(row, "Switch to demo mode", self._switch_to_demo, p,
                   bg=p.panel, fg=p.text_dim, hover=p.rule,
                   font=Font.small, pady=6).pack(side="right", padx=(Space.sm, 0))
        FlatButton(row, "Manage subscription", self._open_account, p,
                   bg=p.accent, fg="#12171E", hover=p.accent,
                   font=Font.small, pady=6).pack(side="right")

    def _build_grid(self) -> None:
        p = self.pal
        wrap = tk.Frame(self, bg=p.ground)
        wrap.pack(fill="both", expand=True, padx=Space.lg, pady=Space.md)
        self.grid_host = tk.Frame(wrap, bg=p.ground)
        self.grid_host.pack(fill="both", expand=True)

        codes = [i.display for i in self.session.market_data.instruments()]
        if self.prefs.coins_visible:
            codes = [c for c in codes if c in self.prefs.coins_visible]
        per_row = 5
        for idx, code in enumerate(codes[:self.prefs.panels_per_page]):
            card = CoinCard(self.grid_host, self, code)
            card.grid(row=idx // per_row, column=idx % per_row,
                      padx=Space.sm, pady=Space.sm, sticky="nsew")
            self.cards[code] = card
        for c in range(per_row):
            self.grid_host.columnconfigure(c, weight=1, minsize=CARD_W)
        for r in range((len(self.cards) + per_row - 1) // per_row):
            self.grid_host.rowconfigure(r, weight=1, minsize=CARD_H)

        self.footer = tk.Label(self, text="", bg=p.ground, fg=p.text_faint,
                               font=Font.data_sm, anchor="w")
        self.footer.pack(fill="x", padx=Space.lg, pady=(0, Space.sm))

    # -- data --------------------------------------------------------------
    def instrument_for(self, code: str):
        return self._instruments.get(code)

    def _tick(self) -> None:
        now = time.time()
        try:
            self._instruments = {i.display: i
                                 for i in self.session.market_data.instruments()}
            self.snapshot = self.session.account.snapshot()
            for card in self.cards.values():
                card.refresh(now)
            self._refresh_chrome()
            if self.watch and self.watch.take_transition():
                self._apply_trading_state()
        except FireError as exc:
            self.footer.configure(text=f"{exc.title}. {exc.remedy}",
                                  fg=self.pal.warn)
        except Exception:
            self.footer.configure(text="FIRE hit an unexpected problem. "
                                       "Open Diagnostics to send a support bundle.",
                                  fg=self.pal.bad)
        self.after(REFRESH_MS, self._tick)

    def _refresh_chrome(self) -> None:
        p = self.pal
        if self.snapshot:
            self.bal_lbl.configure(text=f"${self.snapshot.balance_dollars:,.2f}")
        state = self.session.market_data.connection_state()
        colours = {
            ConnectionState.READY: (p.good, "connected"),
            ConnectionState.CONNECTING: (p.warn, "connecting"),
            ConnectionState.DEGRADED: (p.warn, "degraded"),
            ConnectionState.AUTH_FAILED: (p.bad, "sign in required"),
            ConnectionState.OFFLINE: (p.text_faint, "offline"),
        }
        colour, text = colours.get(state, (p.text_faint, "unknown"))
        self.conn_lbl.configure(text=f"● {text}", fg=colour)

        ent = self.watch.latest() if self.watch else self.session.entitlement()
        if ent:
            tone = p.warn if ent.is_warning else p.text_faint
            label = {
                EntitlementStatus.TRIAL: ent.message or "Trial",
                EntitlementStatus.ACTIVE: "Subscription active",
                EntitlementStatus.EXPIRED: "Subscription expired",
                EntitlementStatus.REVOKED: "Access revoked",
                EntitlementStatus.UNLICENSED: "No licence",
            }.get(ent.status, "")
            self.ent_lbl.configure(text=label, fg=tone)

    # -- entitlement -------------------------------------------------------
    def _apply_trading_state(self) -> None:
        """Switch order entry on or off to match the subscription.

        Called at startup and whenever the watch reports a change, so the
        customer sees the state before they click, not after.
        """
        ent = self.watch.latest() if self.watch else self.session.entitlement()
        allowed = trading_allowed(self.session.mode, ent)
        note = "" if allowed else suspension_reason(self.session.mode, ent)
        brief = "" if allowed else short_suspension_reason(self.session.mode, ent)
        if allowed == self.trading_enabled and note == self.suspension_note:
            return
        self.trading_enabled, self.suspension_note = allowed, note

        # The card gets the short version; the bar across the top carries the
        # full explanation and the two ways out.
        for card in self.cards.values():
            card.set_trading_enabled(allowed, brief)

        if allowed:
            self.lapse_bar.pack_forget()
        else:
            self.lapse_msg.configure(text=note)
            self.lapse_bar.pack(fill="x", after=self.banner)
        self._refresh_chrome()

    def entitlement_changed(self) -> None:
        """Called after the customer redeems or refreshes a licence, so the
        terminal reflects it immediately instead of on the next poll."""
        if self.watch:
            self.watch.poll_once()
            self.watch.take_transition()      # already handled here
        self._apply_trading_state()
        self._refresh_chrome()

    def _switch_to_demo(self) -> None:
        """Reopen in demo. Never automatic: a simulated balance appearing where
        a real one was is the kind of thing that gets someone hurt."""
        if self.session.is_live:
            ok = messagebox.askokcancel(
                "Switch to demo mode",
                "FIRE will reopen with a simulated account.\n\n"
                "Any real positions you hold stay open at the exchange. FIRE "
                "will not close them and will not show them while in demo "
                "mode. Manage them from your exchange account.",
                parent=self)
            if not ok:
                return
        self.prefs.last_mode = "demo"
        self.restart_mode = VenueMode.DEMO
        self.on_close()

    # -- order flow --------------------------------------------------------
    def place_order(self, card: CoinCard, ticker: str, side: Side,
                    budget: float) -> None:
        p = self.pal
        try:
            execution = self.session.execution
            request = execution.plan(ticker, side, budget)
            balance = self.snapshot.balance_dollars if self.snapshot else 0.0
            decision = self.risk.enforce(request, balance)

            if self.session.is_live and self.prefs.confirm_before_live_order:
                ok = messagebox.askokcancel(
                    "Confirm live order",
                    f"Buy {request.count} {side.value.upper()} on {card.code}\n"
                    f"at {request.limit_price:.2f} or better.\n\n"
                    f"Maximum loss: ${decision.max_loss_dollars:,.2f}\n\n"
                    "This spends real money.",
                    parent=self)
                if not ok:
                    card._say("Cancelled. Nothing was sent.", p.text_faint)
                    return

            result = execution.submit(request)
            if result.filled_count:
                card._say(
                    f"Filled {result.filled_count} @ {result.average_price:.2f}"
                    f"  ·  risked ${result.cost_dollars:,.2f}", p.good)
            else:
                card._say(result.message or "Not filled. Nothing was charged.", p.warn)
        except FireError as exc:
            card._say(f"{exc.title}. {exc.remedy}", p.warn)
        except Exception:
            card._say("Order could not be sent. Nothing was charged. "
                      "See Diagnostics.", p.bad)

    # -- chrome actions ----------------------------------------------------
    def _reset_demo(self) -> None:
        try:
            self.session.raw_venue().reset()
            for card in self.cards.values():
                card._say("Demo account reset.", self.pal.text_faint)
        except FireError as exc:
            messagebox.showwarning("Reset", exc.title, parent=self)

    def _open_diagnostics(self) -> None:
        from fire.ui.diagnostics_window import DiagnosticsWindow
        DiagnosticsWindow(self)

    def _open_preferences(self) -> None:
        from fire.ui.preferences_window import PreferencesWindow
        PreferencesWindow(self)

    def _open_activity(self) -> None:
        from fire.ui.activity_window import ActivityWindow
        ActivityWindow(self)

    def _open_account(self) -> None:
        from fire.ui.account_window import AccountWindow
        AccountWindow(self)

    def report_crash(self, path) -> None:
        """Called by the crash handler. Says what happened in plain words and
        never shows the traceback."""
        try:
            self.footer.configure(
                text=("FIRE hit an unexpected problem. Your account and orders "
                      "were not affected. Open Diagnostics to send us the detail."
                      if path else
                      "FIRE hit an unexpected problem. Open Diagnostics for help."),
                fg=self.pal.bad)
        except Exception:
            pass

    def on_close(self) -> None:
        if self.watch:
            self.watch.stop()
        save_prefs(self.prefs)
        self.session.disconnect()
        self.destroy()
