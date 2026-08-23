"""Account and subscription.

Everything about entitlement that a customer can see or act on. It reads the
`EntitlementProvider` interface and nothing else, so connecting a real billing
backend later changes no code in this file.
"""
from __future__ import annotations

import time
import tkinter as tk

from fire.interfaces.entitlement import EntitlementStatus
from fire.ui.theme import Font, Space
from fire.ui.widgets import FlatButton, hrule

_HEADLINE = {
    EntitlementStatus.TRIAL: "You are on a free trial",
    EntitlementStatus.ACTIVE: "Your subscription is active",
    EntitlementStatus.EXPIRED: "Your subscription has ended",
    EntitlementStatus.REVOKED: "This installation's access was revoked",
    EntitlementStatus.UNLICENSED: "No licence on this installation",
}

_EXPLAIN = {
    EntitlementStatus.TRIAL:
        "Live trading is available for the rest of your trial. Demo mode stays "
        "available either way.",
    EntitlementStatus.ACTIVE:
        "Live trading and demo mode are both available.",
    EntitlementStatus.EXPIRED:
        "Live trading is paused until you renew. Demo mode still works, and "
        "nothing you have saved has been removed.",
    EntitlementStatus.REVOKED:
        "Live trading is unavailable on this installation. If you think this is "
        "a mistake, send us a support bundle from Diagnostics.",
    EntitlementStatus.UNLICENSED:
        "Enter a licence key to enable live trading. Demo mode is always "
        "available without one.",
}


class AccountWindow(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app, self.pal = app, app.pal
        self.provider = app.entitlement
        p = self.pal

        self.title("FIRE  ·  Account")
        self.configure(bg=p.ground)
        self.geometry("520x460")
        self.transient(app)
        self.resizable(False, False)

        head = tk.Frame(self, bg=p.panel)
        head.pack(fill="x")
        tk.Label(head, text="Account", bg=p.panel, fg=p.text,
                 font=Font.title).pack(side="left", padx=Space.lg, pady=Space.md)

        self.box = tk.Frame(self, bg=p.ground)
        self.box.pack(fill="both", expand=True, padx=Space.lg, pady=Space.lg)
        self._render()

    def _render(self) -> None:
        p = self.pal
        for child in self.box.winfo_children():
            child.destroy()

        ent = self.provider.current()
        tone = p.warn if ent.is_warning else (
            p.good if ent.status is EntitlementStatus.ACTIVE else p.text)

        tk.Label(self.box, text=_HEADLINE.get(ent.status, "Subscription"),
                 bg=p.ground, fg=tone, font=(Font.title[0], 17, "bold"),
                 anchor="w", justify="left", wraplength=460).pack(fill="x")
        tk.Label(self.box, text=_EXPLAIN.get(ent.status, ""), bg=p.ground,
                 fg=p.text_dim, font=Font.body, anchor="w", justify="left",
                 wraplength=460).pack(fill="x", pady=(Space.sm, 0))

        if ent.expires_epoch:
            when = time.strftime("%d %B %Y", time.localtime(ent.expires_epoch))
            word = "Renews" if ent.status is EntitlementStatus.ACTIVE else "Ends"
            if ent.status in (EntitlementStatus.EXPIRED, EntitlementStatus.REVOKED):
                word = "Ended"
            tk.Label(self.box, text=f"{word} {when}", bg=p.ground,
                     fg=p.text_faint, font=Font.small,
                     anchor="w").pack(fill="x", pady=(Space.md, 0))

        if ent.plan:
            tk.Label(self.box, text=f"Plan: {ent.plan}", bg=p.ground,
                     fg=p.text_faint, font=Font.small,
                     anchor="w").pack(fill="x")

        hrule(self.box, p, pad=Space.lg)

        tk.Label(self.box, text="LICENCE KEY", bg=p.ground, fg=p.text_faint,
                 font=Font.label, anchor="w").pack(fill="x")
        self.key_entry = tk.Entry(self.box, bg=p.panel, fg=p.text,
                                  insertbackground=p.text, relief="flat",
                                  font=Font.data, highlightthickness=1,
                                  highlightbackground=p.rule,
                                  highlightcolor=p.accent)
        self.key_entry.pack(fill="x", ipady=6, pady=(Space.xs, Space.sm))

        self.msg = tk.Label(self.box, text="", bg=p.ground, fg=p.text_faint,
                            font=Font.small, anchor="w", justify="left",
                            wraplength=460)
        self.msg.pack(fill="x", pady=Space.sm)

        row = tk.Frame(self.box, bg=p.ground)
        row.pack(fill="x", pady=Space.md)
        FlatButton(row, "Apply licence", self._redeem, p, bg=p.accent,
                   fg="#12171E", hover=p.accent).pack(side="left")
        FlatButton(row, "Refresh", self._refresh, p, bg=p.panel_hi,
                   fg=p.text_dim, hover=p.rule).pack(side="left", padx=Space.sm)
        FlatButton(row, "Close", self.destroy, p, bg=p.panel_hi,
                   fg=p.text_dim, hover=p.rule).pack(side="right")

        tk.Label(self.box,
                 text="Demo mode never requires a subscription.",
                 bg=p.ground, fg=p.text_faint, font=Font.small,
                 anchor="w").pack(fill="x", side="bottom")

    def _redeem(self) -> None:
        key = self.key_entry.get().strip()
        if not key:
            self.msg.configure(text="Paste the licence key from your receipt.",
                               fg=self.pal.warn)
            return
        try:
            ent = self.provider.redeem(key)
        except Exception:
            self.msg.configure(text="That licence could not be applied right now. "
                                    "Check your connection and try again.",
                               fg=self.pal.warn)
            return
        if ent.allows_live_trading:
            self._render()
            self.msg.configure(text="Licence applied.", fg=self.pal.good)
        else:
            self.msg.configure(text=ent.message or "That licence key was not accepted.",
                               fg=self.pal.warn)

    def _refresh(self) -> None:
        try:
            self.provider.refresh()
        except Exception:
            pass
        self._render()
        self.msg.configure(text="Checked just now.", fg=self.pal.text_faint)
