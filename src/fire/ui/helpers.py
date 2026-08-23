"""Small shared UI behaviours.

Opening a shipped document happens from more than one window, and getting it
wrong means a dead button. It lives here once.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
import webbrowser
from typing import Optional

from fire.config.paths import resource


def open_shipped_doc(parent, name: str, status: Optional[tk.Label] = None) -> bool:
    """Open a document that ships inside the build. Never raises."""
    path = resource(name)
    if path is None:
        if status is not None:
            status.configure(text="That guide is missing from this "
                                  "installation. Reinstall FIRE to restore it.")
        return False
    try:
        if sys.platform == "win32":
            os.startfile(str(path))            # noqa: S606
        else:
            webbrowser.open(path.as_uri())
        return True
    except Exception:
        if status is not None:
            status.configure(text=f"Open this file to read it: {path}")
        return False
