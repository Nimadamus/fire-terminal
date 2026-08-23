"""First run setup.

Goals, in order:
  1. Let someone reach a working screen without an account. Demo is one click
     from the first thing they see.
  2. If they do connect an account, make it obvious the key never leaves this
     machine, because pasting a trading key into an unfamiliar app is a
     reasonable thing to be nervous about.
  3. Set a risk ceiling before the first live order, not after it.
"""
from __future__ import annotations

import tkinter as tk
from typing import Optional

from fire.config.credentials import CredentialStore, Credentials
from fire.config.prefs import Preferences, save as save_prefs
from fire.interfaces.venue import VenueMode
from fire.ui.theme import Font, Space, palette
from fire.ui.widgets import FlatButton, hrule


class OnboardingWindow(tk.Tk):
    """Runs before the terminal. Returns the mode the customer chose."""

    def __init__(self, prefs: Preferences) -> None:
        super().__init__()
        self.prefs = prefs
        self.pal = palette(prefs.theme)
        self.store = CredentialStore()
        self.result: Optional[str] = None
        self._next_mode = VenueMode.DEMO

        self.title("Welcome to FIRE")
        self.configure(bg=self.pal.ground)
        self.geometry("680x620")
        self.resizable(False, False)

        self.body = tk.Frame(self, bg=self.pal.ground)
        self.body.pack(fill="both", expand=True, padx=40, pady=32)
        self._show_welcome()

    # -- helpers -----------------------------------------------------------
    def _clear(self) -> tk.Frame:
        for child in self.body.winfo_children():
            child.destroy()
        return self.body

    def _heading(self, parent, text: str, sub: str = "") -> None:
        p = self.pal
        tk.Label(parent, text=text, bg=p.ground, fg=p.text,
                 font=(Font.title[0], 22, "bold"), anchor="w",
                 justify="left").pack(fill="x")
        if sub:
            tk.Label(parent, text=sub, bg=p.ground, fg=p.text_dim,
                     font=Font.body, anchor="w", justify="left",
                     wraplength=580).pack(fill="x", pady=(Space.sm, 0))

    def _bullet(self, parent, text: str) -> None:
        p = self.pal
        row = tk.Frame(parent, bg=p.ground)
        row.pack(fill="x", pady=3)
        tk.Label(row, text="•", bg=p.ground, fg=p.accent,
                 font=Font.body).pack(side="left", padx=(0, Space.sm))
        tk.Label(row, text=text, bg=p.ground, fg=p.text_dim, font=Font.body,
                 anchor="w", justify="left", wraplength=560).pack(side="left")

    # -- step 1: welcome ---------------------------------------------------
    def _show_welcome(self) -> None:
        p, box = self.pal, self._clear()
        tk.Label(box, text="FIRE", bg=p.ground, fg=p.text,
                 font=(Font.title[0], 30, "bold"), anchor="w").pack(fill="x")
        tk.Label(box, text="A fast execution terminal for short duration markets.",
                 bg=p.ground, fg=p.text_dim, font=Font.body,
                 anchor="w").pack(fill="x", pady=(2, Space.lg))

        self._bullet(box, "Every open market on one screen, with live prices and depth.")
        self._bullet(box, "One click to buy either side, with the limit taken from the book.")
        self._bullet(box, "A maximum loss ceiling you set, checked before every order.")
        self._bullet(box, "Your API key stays on this computer. FIRE has no server.")

        hrule(box, p, pad=Space.lg)

        tk.Label(box, text="How do you want to start?", bg=p.ground, fg=p.text,
                 font=Font.heading, anchor="w").pack(fill="x", pady=(0, Space.md))

        demo = tk.Frame(box, bg=p.panel)
        demo.pack(fill="x", pady=(0, Space.md))
        tk.Label(demo, text="Try it first, no account needed", bg=p.panel,
                 fg=p.text, font=Font.heading, anchor="w").pack(
                     fill="x", padx=Space.lg, pady=(Space.md, 0))
        tk.Label(demo, text="Simulated markets and a simulated balance. Nothing "
                            "connects to an exchange and no money is involved.",
                 bg=p.panel, fg=p.text_dim, font=Font.small, anchor="w",
                 justify="left", wraplength=520).pack(fill="x", padx=Space.lg)
        FlatButton(demo, "Start in Demo", self._choose_demo, p,
                   bg=p.demo, hover=p.demo).pack(anchor="w", padx=Space.lg,
                                                 pady=Space.md)

        live = tk.Frame(box, bg=p.panel)
        live.pack(fill="x")
        tk.Label(live, text="Connect my exchange account", bg=p.panel,
                 fg=p.text, font=Font.heading, anchor="w").pack(
                     fill="x", padx=Space.lg, pady=(Space.md, 0))
        tk.Label(live, text="You will need an API key from your exchange. You can "
                            "also do this later at any time.",
                 bg=p.panel, fg=p.text_dim, font=Font.small, anchor="w",
                 justify="left", wraplength=520).pack(fill="x", padx=Space.lg)
        FlatButton(live, "Set up my account", self._show_credentials, p,
                   bg=p.panel_hi, fg=p.text, hover=p.rule).pack(
                       anchor="w", padx=Space.lg, pady=Space.md)

    # -- step 2: credentials ----------------------------------------------
    def _show_credentials(self) -> None:
        p, box = self.pal, self._clear()
        self._heading(box, "Connect your account",
                      "FIRE stores these using your operating system secure "
                      "credential store. They are never written to a plain file, "
                      "never sent anywhere, and never included in a support bundle.")

        tk.Label(box, text=f"Secure store on this computer: {self.store.backend_name()}",
                 bg=p.ground, fg=p.text_faint, font=Font.small,
                 anchor="w").pack(fill="x", pady=(Space.md, Space.lg))

        tk.Label(box, text="API KEY ID", bg=p.ground, fg=p.text_faint,
                 font=Font.label, anchor="w").pack(fill="x")
        self.key_id = tk.Entry(box, bg=p.panel, fg=p.text, insertbackground=p.text,
                               relief="flat", font=Font.data,
                               highlightthickness=1, highlightbackground=p.rule,
                               highlightcolor=p.accent)
        self.key_id.pack(fill="x", ipady=6, pady=(Space.xs, Space.md))

        tk.Label(box, text="PRIVATE KEY", bg=p.ground, fg=p.text_faint,
                 font=Font.label, anchor="w").pack(fill="x")
        self.key_pem = tk.Text(box, height=8, bg=p.panel, fg=p.text,
                               insertbackground=p.text, relief="flat",
                               font=Font.data_sm, wrap="none",
                               highlightthickness=1, highlightbackground=p.rule,
                               highlightcolor=p.accent)
        self.key_pem.pack(fill="x", pady=(Space.xs, Space.sm))
        tk.Label(box, text="Paste the whole key file, including its first and last lines.",
                 bg=p.ground, fg=p.text_faint, font=Font.small,
                 anchor="w").pack(fill="x")

        self.cred_msg = tk.Label(box, text="", bg=p.ground, fg=p.warn,
                                 font=Font.small, anchor="w", justify="left",
                                 wraplength=580)
        self.cred_msg.pack(fill="x", pady=Space.md)

        row = tk.Frame(box, bg=p.ground)
        row.pack(fill="x", side="bottom")
        FlatButton(row, "Back", self._show_welcome, p, bg=p.panel_hi,
                   fg=p.text_dim, hover=p.rule).pack(side="left")
        FlatButton(row, "Save and continue", self._save_credentials, p,
                   bg=p.accent, fg="#12171E", hover=p.accent).pack(side="right")

    def _save_credentials(self) -> None:
        key_id = self.key_id.get().strip()
        pem = self.key_pem.get("1.0", "end").strip()
        if not key_id:
            self.cred_msg.configure(text="Enter the key ID your exchange gave you.")
            return
        if not pem:
            self.cred_msg.configure(text="Paste your private key.")
            return

        # Validate by actually parsing it. Better than a string check, and it
        # lets us tell the customer precisely what is wrong.
        try:
            from cryptography.hazmat.primitives import serialization
            serialization.load_pem_private_key(pem.encode(), password=None)
        except Exception:
            self.cred_msg.configure(
                text="That does not look like a valid private key. Copy the whole "
                     "file, including its first and last lines, and check that it "
                     "is not password protected.")
            return

        try:
            self.store.save(Credentials(key_id=key_id, private_key_pem=pem))
        except Exception as exc:
            remedy = getattr(exc, "remedy", "")
            self.cred_msg.configure(
                text=f"FIRE could not save your credentials securely. {remedy} "
                     "Nothing was written to disk.")
            return
        self._show_risk(next_mode=VenueMode.LIVE)

    # -- step 3: risk ------------------------------------------------------
    def _show_risk(self, next_mode: str) -> None:
        p, box = self.pal, self._clear()
        self._next_mode = next_mode
        self._heading(box, "Set your limit",
                      "FIRE refuses any order whose worst case loss is larger than "
                      "this share of your balance. A binary contract can settle at "
                      "zero, so the worst case is the full cost of the order.")

        tk.Label(box, text="MAXIMUM LOSS PER ORDER", bg=p.ground, fg=p.text_faint,
                 font=Font.label, anchor="w").pack(fill="x", pady=(Space.lg, Space.sm))

        self.risk_var = tk.IntVar(value=int(self.prefs.max_loss_fraction * 100))
        scale_row = tk.Frame(box, bg=p.ground)
        scale_row.pack(fill="x")
        self.risk_scale = tk.Scale(
            scale_row, from_=1, to=100, orient="horizontal", variable=self.risk_var,
            bg=p.ground, fg=p.text, troughcolor=p.panel, highlightthickness=0,
            relief="flat", showvalue=False, sliderrelief="flat",
            activebackground=p.accent, command=lambda _v: self._risk_label())
        self.risk_scale.pack(side="left", fill="x", expand=True)
        self.risk_lbl = tk.Label(scale_row, text="", bg=p.ground, fg=p.accent,
                                 font=Font.price_sm, width=6)
        self.risk_lbl.pack(side="right")
        self._risk_label()

        tk.Label(box, text="You can change this at any time in Preferences.",
                 bg=p.ground, fg=p.text_faint, font=Font.small,
                 anchor="w").pack(fill="x", pady=Space.md)

        self.confirm_var = tk.BooleanVar(value=self.prefs.confirm_before_live_order)
        tk.Checkbutton(box, text="  Ask me to confirm before every live order",
                       variable=self.confirm_var, bg=p.ground, fg=p.text_dim,
                       selectcolor=p.panel, activebackground=p.ground,
                       activeforeground=p.text, font=Font.body,
                       highlightthickness=0, anchor="w",
                       borderwidth=0).pack(fill="x", pady=Space.sm)

        row = tk.Frame(box, bg=p.ground)
        row.pack(fill="x", side="bottom")
        FlatButton(row, "Back", self._show_welcome, p, bg=p.panel_hi,
                   fg=p.text_dim, hover=p.rule).pack(side="left")
        FlatButton(row, "Open FIRE", self._finish, p, bg=p.accent,
                   fg="#12171E", hover=p.accent).pack(side="right")

    def _risk_label(self) -> None:
        self.risk_lbl.configure(text=f"{self.risk_var.get()}%")

    # -- exits -------------------------------------------------------------
    def _choose_demo(self) -> None:
        self._show_risk(next_mode=VenueMode.DEMO)

    def _finish(self) -> None:
        self.prefs.max_loss_fraction = self.risk_var.get() / 100.0
        self.prefs.confirm_before_live_order = bool(self.confirm_var.get())
        self.prefs.onboarding_complete = True
        self.prefs.last_mode = self._next_mode
        save_prefs(self.prefs)
        self.result = self._next_mode
        self.destroy()


def run_onboarding(prefs: Preferences) -> Optional[str]:
    """Blocks until the customer finishes or closes the window."""
    win = OnboardingWindow(prefs)
    win.mainloop()
    return win.result
