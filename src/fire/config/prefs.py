"""Customer preferences, persisted locally as plain JSON.

Nothing secret goes in here. Credentials live in the platform secret store,
see `fire.config.credentials`.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from typing import Any

from fire.config.paths import prefs_file


@dataclass
class Preferences:
    # startup
    last_mode: str = "demo"                  # demo | live
    onboarding_complete: bool = False

    # order entry
    stake_presets: list[float] = field(default_factory=lambda: [25, 100, 250, 500, 1000])
    default_stake: float = 100.0
    confirm_before_live_order: bool = True

    # risk
    max_loss_fraction: float = 0.10          # of balance, per order
    max_loss_enabled: bool = True

    # display
    coins_visible: list[str] = field(default_factory=list)   # empty = all
    panels_per_page: int = 10
    theme: str = "dark"
    sound_on_fill: bool = True

    # updates
    check_for_updates: bool = True

    def clamp(self) -> "Preferences":
        self.max_loss_fraction = min(1.0, max(0.005, float(self.max_loss_fraction)))
        self.default_stake = max(1.0, float(self.default_stake))
        self.panels_per_page = min(12, max(4, int(self.panels_per_page)))
        if self.last_mode not in ("demo", "live"):
            self.last_mode = "demo"
        return self


def load() -> Preferences:
    path = prefs_file()
    if not path.exists():
        return Preferences()
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return Preferences()
    known = {f.name for f in fields(Preferences)}
    return Preferences(**{k: v for k, v in raw.items() if k in known}).clamp()


def save(prefs: Preferences) -> None:
    prefs.clamp()
    tmp = prefs_file().with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(prefs), indent=2), encoding="utf-8")
    tmp.replace(prefs_file())
