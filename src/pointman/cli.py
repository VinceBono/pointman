# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vince Bono
"""pointman serve: MCP server over stdio. pointman verify-audit: check the action log was not edited."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .audit import AuditLog, verify
from .core import Pointman
from .policy import Policy

INSTRUCTIONS = (
    "Operate Windows apps through their accessibility tree. Call list_windows, then read_window to get "
    "element refs, then click or set_text. A reply starting with DENIED is a policy decision by the "
    "computer's owner: report it, do not try another route."
)


def build_server(pointman: Pointman):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("pointman", instructions=INSTRUCTIONS)
    for method in (pointman.list_windows, pointman.read_window, pointman.click, pointman.set_text):
        server.tool()(method)
    return server


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="pointman", description=__doc__)
    ap.add_argument("command", choices=["serve", "verify-audit"])
    ap.add_argument("--config", type=Path, default=Path("pointman.toml"), help="policy file (default pointman.toml)")
    args = ap.parse_args(argv)

    try:
        # No config file means the built-in policy: no apps allowed, no actions.
        policy = Policy.load(args.config) if args.config.exists() else Policy()
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.command == "verify-audit":
        if not policy.audit_log.exists():
            print(f"no log at {policy.audit_log}")
            return 0
        count, problem = verify(policy.audit_log)
        print(f"FAIL: {problem}" if problem else f"OK: {count} entries, chain intact")
        return 1 if problem else 0

    build_server(Pointman(policy, AuditLog(policy.audit_log))).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
