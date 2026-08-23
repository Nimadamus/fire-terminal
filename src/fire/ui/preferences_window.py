"""Preferences. Everything the customer is allowed to change, in one place."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox

from fire.config.credentials import CredentialStore
from fire.config.prefs import save as save_prefs
from fire.ui.theme import Font, Space
from fire.ui.widgets import FlatButton, hrule


class PreferencesWindow(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app, self.pal = app, app.pal
        self.prefs = app.prefs
        self.store = CredentialStore()
        p = self.pal

        self.title("FIRE  ·  Preferences")
        self.configure(bg=p.ground)
        self.geometry("560x680")
        self.transient(app)
        self.resizable(False, False)

        head = tk.Frame(self, bg=p.panel)
        head.pack(fill="x")
        tk.Label(head, text="Preferences", bg=p.panel, fg=p.text,
                 font=Font.title).pack(side="left", padx=Space.lg, pady=Space.md)

        box = tk.Frame(self, bg=p.ground)
        box.pack(fill="both", expand=True, padx=Space.lg, pady=Space.md)

        # -- risk ----------------------------------------------------------
        self._section(box, "Risk")
        tk.Label(box, text="Maximum loss per order, as a share of your balance",
                 bg=p.ground, fg=p.text_dim, font=Font.small,
                 anchor="w").pack(fill="x")
        row = tk.Frame(box, bg=p.ground)
        row.pack(fill="x", pady=(Space.xs, Space.sm))
        self.risk_var = tk.IntVar(value=int(self.prefs.max_loss_fraction * 100))
        tk.Scale(row, from_=1, to=100, orient="horizontal", variable=self.risk_var,
                 bg=p.ground, fg=p.text, troughcolor=p.panel, highlightthickness=0,
                 relief="flat", showvalue=False, sliderrelief="flat",
                 activebackground=p.accent,
                 command=lambda _v: self.risk_lbl.configure(
                     text=f"{self.risk_var.get()}%")).pack(
                         side="left", fill="x", expand=True)
        self.risk_lbl = tk.Label(row, text=f"{self.risk_var.get()}%", bg=p.ground,
                                 fg=p.accent, font=Font.price_sm, width=6)
        self.risk_lbl.pack(side="right")

        self.risk_on = tk.BooleanVar(value=self.prefs.max_loss_enabled)
        self._check(box, "Enforce this limit", self.risk_on)
        self.confirm_on = tk.BooleanVar(value=self.prefs.confirm_before_live_order)
        self._check(box, "Ask me to confirm before every live order", self.confirm_on)

        # -- order entry -----------------------------------------------------
        hrule(box, p, pad=Space.md)
        self._section(box, "Order entry")
        tk.Label(box, text="Stake buttons, comma separated",
                 bg=p.ground, fg=p.text_dim, font=Font.small,
                 anchor="w").pack(fill="x")
        self.presets = tk.Entry(box, bg=p.panel, fg=p.text, insertbackground=p.text,
                                relief="flat", font=Font.data, highlightthickness=1,
                                highlightbackground=p.rule, highlightcolor=p.accent)
        self.presets.insert(0, ", ".join(f"{v:g}" for v in self.prefs.stake_presets))
        self.presets.pack(fill="x", ipady=5, pady=(Space.xs, Space.sm))

        tk.Label(box, text="Default amount", bg=p.ground, fg=p.text_dim,
                 font=Font.small, anchor="w").pack(fill="x")
        self.default_stake = tk.Entry(box, bg=p.panel, fg=p.text,
                                      insertbackground=p.text, relief="flat",
                                      font=Font.data, highlightthickness=1,
                                      highlightbackground=p.rule,
                                      highlightcolor=p.accent)
        self.default_stake.insert(0, f"{self.prefs.default_stake:g}")
        self.default_stake.pack(fill="x", ipady=5, pady=(Space.xs, Space.sm))

        # -- display ---------------------------------------------------------
        hrule(box, p, pad=Space.md)
        self._section(box, "Display")
        row2 = tk.Frame(box, bg=p.ground)
        row2.pack(fill="x", pady=Space.xs)
        tk.Label(row2, text="Markets per page", bg=p.ground, fg=p.text_dim,
                 font=Font.small).pack(side="left")
        self.per_page = tk.IntVar(value=self.prefs.panels_per_page)
        tk.Spinbox(row2, from_=4, to=12, textvariable=self.per_page, width=5,
                   bg=p.panel, fg=p.text, relief="flat", font=Font.data,
                   buttonbackground=p.panel_hi,
                   highlightthickness=1, highlightbackground=p.rule).pack(side="right")

        self.theme_var = tk.StringVar(value=self.prefs.theme)
        row3 = tk.Frame(box, bg=p.ground)
        row3.pack(fill="x", pady=Space.sm)
        tk.Label(row3, text="Theme", bg=p.ground, fg=p.text_dim,
                 font=Font.small).pack(side="left")
        for name in ("dark", "light"):
            tk.Radiobutton(row3, text=name.title(), value=name,
                           variable=self.theme_var, bg=p.ground, fg=p.text_dim,
                           selectcolor=p.panel, activebackground=p.ground,
                           activeforeground=p.text, font=Font.small,
                           highlightthickness=0, borderwidth=0).pack(side="right",
                                                                     padx=Space.sm)

        self.sound_on = tk.BooleanVar(value=self.prefs.sound_on_fill)
        self._check(box, "Play a sound when an order fills", self.sound_on)
        self.updates_on = tk.BooleanVar(value=self.prefs.check_for_updates)
        self._check(box, "Check for updates automatically", self.updates_on)

        # -- account ---------------------------------------------------------
        hrule(box, p, pad=Space.md)
        self._section(box, "Account")
        configured = self.store.has_credentials()
        tk.Label(box,
                 text=("Exchange credentials are saved on this computer."
                       if configured else "No exchange credentials saved."),
                 bg=p.ground, fg=p.text_dim, font=Font.small,
                 anchor="w").pack(fill="x")
        tk.Label(box, text=f"Secure store: {self.store.backend_name()}",
                 bg=p.ground, fg=p.text_faint, font=Font.small,
                 anchor="w").pack(fill="x", pady=(0, Space.sm))
        if configured:
            FlatButton(box, "Remove saved credentials", self._clear_credentials, p,
                       bg=p.panel_hi, fg=p.no, hover=p.rule,
                       font=Font.small, pady=6).pack(anchor="w")

        # -- footer ----------------------------------------------------------
        foot = tk.Frame(self, bg=p.ground)
        foot.pack(fill="x", padx=Space.lg, pady=Space.md, side="bottom")
        self.msg = tk.Label(foot, text="", bg=p.ground, fg=p.text_faint,
                            font=Font.small, anchor="w", wraplength=380,
                            justify="left")
        self.msg.pack(side="left", fill="x", expand=True)
        FlatButton(foot, "Save", self._save, p, bg=p.accent, fg="#12171E",
                   hover=p.accent).pack(side="right")
        FlatButton(foot, "Cancel", self.destroy, p, bg=p.panel_hi,
                   fg=p.text_dim, hover=p.rule).pack(side="right", padx=Space.sm)

    # -- helpers -----------------------------------------------------------
    def _section(self, parent, text: str) -> None:
        tk.Label(parent, text=text.upper(), bg=self.pal.ground,
                 fg=self.pal.text_faint, font=Font.label,
                 anchor="w").pack(fill="x", pady=(0, Space.sm))

    def _check(self, parent, text: str, var: tk.BooleanVar) -> None:
        p = self.pal
        tk.Checkbutton(parent, text="  " + text, variable=var, bg=p.ground,
                       fg=p.text_dim, selectcolor=p.panel,
                       activebackground=p.ground, activeforeground=p.text,
                       font=Font.small, highlightthickness=0, anchor="w",
                       borderwidth=0).pack(fill="x", pady=1)

    # -- actions -----------------------------------------------------------
    def _clear_credentials(self) -> None:
        if not messagebox.askokcancel(
                "Remove credentials",
                "FIRE will forget your exchange API key. You can add it again "
                "later. This does not revoke the key at the exchange.",
                parent=self):
            return
        self.store.clear()
        self.msg.configure(text="Credentials removed from this computer.",
                           fg=self.pal.good)

    def _save(self) -> None:
        try:
            presets = [float(x.strip()) for x in self.presets.get().split(",")
                       if x.strip()]
            presets = [x for x in presets if x > 0][:5]
            if not presets:
                raise ValueError
        except ValueError:
            self.msg.configure(text="Stake buttons must be numbers, "
                                    "for example 25, 100, 250.", fg=self.pal.warn)
            return
        try:
            default_stake = float(self.default_stake.get().strip())
            if default_stake <= 0:
                raise ValueError
        except ValueError:
            self.msg.configure(text="Default amount must be a number above zero.",
                               fg=self.pal.warn)
            return

        prefs = self.prefs
        theme_changed = prefs.theme != self.theme_var.get()
        layout_changed = prefs.panels_per_page != int(self.per_page.get())

        prefs.max_loss_fraction = self.risk_var.get() / 100.0
        prefs.max_loss_enabled = bool(self.risk_on.get())
        prefs.confirm_before_live_order = bool(self.confirm_on.get())
        prefs.stake_presets = presets
        prefs.default_stake = default_stake
        prefs.panels_per_page = int(self.per_page.get())
        prefs.theme = self.theme_var.get()
        prefs.sound_on_fill = bool(self.sound_on.get())
        prefs.check_for_updates = bool(self.updates_on.get())
        save_prefs(prefs)

        # apply what can be applied without a restart
        self.app.risk.fraction = prefs.max_loss_fraction
        self.app.risk.enabled = prefs.max_loss_enabled

        if theme_changed or layout_changed:
            self.msg.configure(
                text="Saved. Restart FIRE to apply the theme and layout changes.",
                fg=self.pal.text_dim)
        else:
            self.destroy()
