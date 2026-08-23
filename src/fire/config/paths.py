"""Where FIRE keeps customer data. Per user, never inside the install dir."""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "FIRE"


def _base() -> Path:
    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(root) / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(root) / APP_NAME.lower()


def data_dir() -> Path:
    p = _base()
    p.mkdir(parents=True, exist_ok=True)
    return p


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def prefs_file() -> Path:
    return data_dir() / "preferences.json"


def credentials_file() -> Path:
    return data_dir() / "credentials.dat"


def entitlement_file() -> Path:
    return data_dir() / "entitlement.json"


def bundles_dir() -> Path:
    p = data_dir() / "support"
    p.mkdir(parents=True, exist_ok=True)
    return p


def resource(name: str):
    """A read-only file shipped with the application, or None if it is missing.

    Frozen builds unpack these next to the executable; running from source they
    sit in `docs/` at the top of the repository. Returns None rather than
    raising, because a missing help file must never stop the terminal opening.
    """
    candidates = []
    meipass = getattr(sys, "_MEIPASS", None)
    here = Path(__file__).resolve()
    if name.endswith((".ico", ".png")):
        if meipass:
            candidates.append(Path(meipass) / name)
        candidates.append(here.parents[3] / "packaging" / name)
    else:
        if meipass:
            candidates.append(Path(meipass) / "docs" / name)
        candidates.append(here.parents[3] / "docs" / name)  # <repo>/docs
    for path in candidates:
        if path.is_file():
            return path
    return None
