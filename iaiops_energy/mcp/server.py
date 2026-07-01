"""``iaiops-energy-mcp`` — the energy edition's MCP server.

A thin wrapper that reuses the base ``iaiops`` install: it registers the shared
cross-protocol **brain** (governance / diagnostics / OEE / compliance — from
``mcp_server``) plus this package's **energy protocol tools** (IEC-104 / DNP3 /
IEC-61850) on the same shared ``mcp`` instance, then runs it. No server logic is
duplicated; governance (audit / budget / risk-tier / undo) comes from iaiops.core.
"""

from __future__ import annotations

import importlib

from mcp_server._shared import mcp
from mcp_server.profiles import BRAIN_MODULES

# The energy edition's protocol tool modules (this package).
ENERGY_TOOL_MODULES: tuple[str, ...] = ("iec104_tools", "dnp3_tools", "iec61850_tools")


def register() -> None:
    """Import the brain + energy tool modules so their @mcp.tool decorators run."""
    for mod in BRAIN_MODULES:
        importlib.import_module(f"mcp_server.tools.{mod}")
    for mod in ENERGY_TOOL_MODULES:
        importlib.import_module(f"iaiops_energy.mcp.tools.{mod}")


def main() -> None:
    """Register the energy tool set on the shared server and run it (stdio)."""
    register()
    mcp.run()


if __name__ == "__main__":
    main()
