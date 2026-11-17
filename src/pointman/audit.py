# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vince Bono
"""Append-only log where each line carries the hash of the line before it, so edits and deletions show."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

GENESIS = "0" * 64


def _digest(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class AuditLog:
    # shortcut: the chain has no key, so someone who can write the file can rebuild it from scratch;
    # it catches edits, not a determined local attacker. Ship lines off the machine if that matters.
    def __init__(self, path: Path):
        self.path = path
        self._last = GENESIS
        if path.exists():
            lines = path.read_text(encoding="utf-8").splitlines()
            if lines:
                self._last = json.loads(lines[-1])["hash"]

    def record(self, tool: str, outcome: str, **detail: object) -> None:
        entry = {"time": datetime.now(timezone.utc).isoformat(), "tool": tool, "outcome": outcome, **detail, "prev": self._last}
        entry["hash"] = _digest(entry)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, sort_keys=True) + "\n")
        self._last = entry["hash"]


def verify(path: Path) -> tuple[int, str | None]:
    """(lines checked, first problem or None)."""
    prev = GENESIS
    count = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            entry = json.loads(line)
            ok = entry["prev"] == prev and entry["hash"] == _digest(entry)
        except (ValueError, KeyError, TypeError):
            ok = False
        if not ok:
            return count, f"line {number} was changed, or a line before it was removed"
        prev = entry["hash"]
        count += 1
    return count, None
