"""``iaiops-energy-mcp`` — the energy edition's MCP server.

Runs the energy edition's OWN ``FastMCP("iaiops-energy")`` instance (see
``iaiops_energy.mcp._app``) with its own energy-specific identity/instructions:

  * this package's energy protocol tools (IEC-104 / DNP3 / IEC-61850) register
    directly onto the energy instance; and
  * the base package's cross-protocol **brain** (governance / diagnostics / OEE /
    compliance — ``mcp_server.tools``) is mirrored onto it, since those modules
    register onto the base's shared instance as an import side effect.

No server logic is duplicated; governance (audit / budget / risk-tier / undo)
comes from ``iaiops.core``. As defense-in-depth, startup refuses to run if any
registered tool lacks the ``_is_governed_tool`` harness marker.
"""

from __future__ import annotations

import importlib

from mcp_server import _shared as _base_shared
from mcp_server.profiles import BRAIN_MODULES

from iaiops_energy.mcp._app import mcp

# The energy edition's protocol tool modules (this package). ``substation_tools``
# is a pure, monitor-only SOE analysis tool (no live protocol I/O / no endpoint).
ENERGY_TOOL_MODULES: tuple[str, ...] = (
    "iec104_tools",
    "dnp3_tools",
    "iec61850_tools",
    "substation_tools",
)


def _mount_base_brain_tools() -> None:
    """Mirror the base cross-protocol brain tools onto the energy instance.

    The base tool modules register onto ``mcp_server._shared.mcp`` (the base
    server's instance) when imported; re-register each resulting tool callable
    onto the energy instance so agents connecting here see the brain too.
    Idempotent: already-mounted tool names are skipped.
    """
    for mod in BRAIN_MODULES:
        importlib.import_module(f"mcp_server.tools.{mod}")
    mounted = {tool.name for tool in mcp._tool_manager.list_tools()}
    for tool in _base_shared.mcp._tool_manager.list_tools():
        if tool.name in mounted:
            continue
        mcp.add_tool(
            tool.fn,
            name=tool.name,
            description=tool.description,
            annotations=getattr(tool, "annotations", None),
        )


def register() -> None:
    """Register the full energy surface: base brain + energy protocol tools."""
    _mount_base_brain_tools()
    for mod in ENERGY_TOOL_MODULES:
        importlib.import_module(f"iaiops_energy.mcp.tools.{mod}")


def assert_all_tools_governed() -> None:
    """Refuse to serve any tool that lacks the governance-harness marker.

    Every tool callable must carry ``_is_governed_tool`` (set by
    ``@governed_tool``). A future tool added without the harness would silently
    bypass audit / budget / risk-tier — fail loudly at startup instead.
    """
    ungoverned = tuple(
        tool.name
        for tool in mcp._tool_manager.list_tools()
        if not getattr(tool.fn, "_is_governed_tool", False)
    )
    if ungoverned:
        raise RuntimeError(
            f"refusing to start: MCP tools missing @governed_tool harness marker: {ungoverned}"
        )


def main() -> None:
    """Register the energy tool set, verify governance, and run it (stdio)."""
    register()
    assert_all_tools_governed()
    mcp.run()


if __name__ == "__main__":
    main()
