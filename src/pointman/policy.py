# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vince Bono
"""What the agent may touch. Everything is denied until the config file allows it."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


class Denied(Exception):
    """The policy refused a request. The message is safe to show to the agent."""


@dataclass(frozen=True)
class Policy:
    allowed_apps: frozenset[str] = frozenset()  # executable names, lower case, e.g. "notepad.exe"
    allow_actions: bool = False  # clicking and typing; reading is controlled by allowed_apps alone
    kill_switch: Path = Path("~/.pointman/STOP").expanduser()
    audit_log: Path = Path("~/.pointman/audit.jsonl").expanduser()

    @classmethod
    def load(cls, path: Path) -> Policy:
        with path.open("rb") as f:
            raw = tomllib.load(f)
        unknown = set(raw) - {"allowed_apps", "allow_actions", "kill_switch", "audit_log"}
        if unknown:  # a typo such as "allow_action" must not silently leave a default in place
            raise ValueError(f"{path}: unknown setting(s) {', '.join(sorted(unknown))}")
        default = cls()
        return cls(
            allowed_apps=frozenset(str(a).lower() for a in raw.get("allowed_apps", [])),
            allow_actions=raw.get("allow_actions", False) is True,
            kill_switch=Path(raw.get("kill_switch", default.kill_switch)).expanduser(),
            audit_log=Path(raw.get("audit_log", default.audit_log)).expanduser(),
        )

    def allows(self, app: str) -> bool:
        return app.lower() in self.allowed_apps

    def check_read(self, app: str) -> None:
        if self.kill_switch.exists():
            raise Denied(f"stopped: the kill switch file {self.kill_switch} exists")
        if not self.allows(app):
            raise Denied(f"{app} is not in allowed_apps")

    def check_action(self, app: str) -> None:
        self.check_read(app)
        if not self.allow_actions:
            raise Denied("read-only: allow_actions is not set to true in the config")
