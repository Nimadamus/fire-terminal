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
