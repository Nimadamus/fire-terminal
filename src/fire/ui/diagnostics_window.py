"""Diagnostics and support page."""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox

from fire.diagnostics import bundle
from fire.ui.theme import Font, Space
from fire.ui.widgets import FlatButton, hrule


class DiagnosticsWindow(tk.Toplevel):
    def __init__(self, app) -> None:
        super().__init__(app)
        self.app, self.pal = app, app.pal
        p = self.pal
        self.title("FIRE  ·  Diagnostics")
        self.configure(bg=p.ground)
        self.geometry("720x640")
        self.transient(app)

        head = tk.Frame(self, bg=p.panel)
        head.pack(fill="x")
        tk.Label(head, text="Diagnostics", bg=p.panel, fg=p.text,
                 font=Font.title).pack(side="left", padx=Space.lg, pady=Space.md)

        body = tk.Frame(self, bg=p.ground)
        body.pack(fill="both", expand=True, padx=Space.lg, pady=Space.md)

        tk.Label(body,
                 text="This is what FIRE knows about your installation. "
                      "Nothing here identifies you and no credentials are included.",
                 bg=p.ground, fg=p.text_dim, font=Font.small,
                 wraplength=660, justify="left", anchor="w").pack(fill="x")

        hrule(body, p, pad=Space.md)

        self.text = tk.Text(body, bg=p.panel, fg=p.text_dim, font=Font.data,
                            relief="flat", wrap="none", height=18,
                            insertbackground=p.text, highlightthickness=1,
                            highlightbackground=p.rule)
        self.text.pack(fill="both", expand=True)
        self._load_report()

        tk.Label(body, text="Anything you want us to know (optional)",
                 bg=p.ground, fg=p.text_faint, font=Font.label,
                 anchor="w").pack(fill="x", pady=(Space.md, Space.xs))
        self.note = tk.Text(body, bg=p.panel, fg=p.text, font=Font.body,
                            relief="flat", height=4, wrap="word",
                            insertbackground=p.text, highlightthickness=1,
                            highlightbackground=p.rule)
        self.note.pack(fill="x")

        actions = tk.Frame(body, bg=p.ground)
        actions.pack(fill="x", pady=Space.md)
        FlatButton(actions, "Create support bundle", self._create, p,
                   bg=p.accent, fg="#12171E", hover=p.accent).pack(side="left")
        FlatButton(actions, "Close", self.destroy, p, bg=p.panel_hi,
                   fg=p.text_dim, hover=p.rule).pack(side="right")

        self.status = tk.Label(body, text="", bg=p.ground, fg=p.text_faint,
                               font=Font.small, anchor="w", wraplength=660,
                               justify="left")
        self.status.pack(fill="x")

    def _load_report(self) -> None:
        try:
            report = bundle.environment_report(
                self.app.session, self.app.prefs, self.app.entitlement)
            self.text.insert("1.0", json.dumps(report, indent=2))
        except Exception:
            self.text.insert("1.0", "Diagnostics could not be gathered.")
        self.text.configure(state="disabled")

    def _create(self) -> None:
        try:
            path = bundle.create(self.app.session, self.app.prefs,
                                 self.app.entitlement,
                                 note=self.note.get("1.0", "end").strip())
            self.status.configure(
                text=f"Saved to {path}. Attach it to your support email.",
                fg=self.pal.good)
        except AssertionError:
            self.status.configure(
                text="Bundle blocked: FIRE found something sensitive it could not "
                     "safely remove. Nothing was written. Please report this.",
                fg=self.pal.bad)
        except Exception:
            messagebox.showwarning(
                "Support bundle",
                "FIRE could not write the support bundle. Check that you have "
                "space and permission in your FIRE data folder.", parent=self)
