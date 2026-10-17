"""Every ``tools/call`` on the energy MCP server records ``origin="mcp"`` on its audit row.

``iaiops`` 0.29.0 added call origin to the audit chain: each front-end declares itself
at its own boundary and ``@governed_tool`` records it (``origin``, the client's
self-reported ``clientInfo``, a per-connection session id). The base server does this
in its ``_GovernedFastMCP.call_tool``. This edition runs its OWN ``FastMCP`` instance,
so it has to declare the boundary itself — without it every energy MCP call lands on a
shared trail as ``origin=""`` ("unknown"), indistinguishable from library code.

Both kinds of tool on this server are covered: the energy tools registered here, and the
base brain tools mirrored in by ``_mount_base_brain_tools`` (those travel through the
same ``call_tool``, so they need no separate scope — this checks that they get one).
"""

from __future__ import annotations

import anyio
import pytest
from iaiops.core.governance.audit import get_engine
from mcp import types
from mcp.shared.memory import create_connected_server_and_client_session

from iaiops_energy.mcp import server as energy_server
from iaiops_energy.mcp._app import mcp

_SOE = [
    {"ref": "R1", "timestamp": "2026-10-17T00:00:00.000Z", "type": "protection_trip"},
    {"ref": "CB1", "timestamp": "2026-10-17T00:00:00.080Z", "type": "breaker_open"},
]


def _rows(tool: str) -> list[dict]:
    return list(reversed(get_engine().query(tool=tool, limit=100)))


async def _call(client_name: str) -> None:
    info = types.Implementation(name=client_name, version="9.9")
    async with create_connected_server_and_client_session(mcp, client_info=info) as client:
        await client.call_tool("substation_event_analysis", {"events": _SOE})
        await client.call_tool("protocols_supported", {})


@pytest.fixture(scope="module", autouse=True)
def _registered() -> None:
    energy_server.register()


@pytest.mark.unit
def test_an_energy_tool_call_records_origin_mcp_with_client_and_session() -> None:
    anyio.run(_call, "probe-agent")
    anyio.run(_call, "other-agent")
    first, second = _rows("substation_event_analysis")
    assert [first["origin"], second["origin"]] == ["mcp", "mcp"]
    assert (first["origin_client"], second["origin_client"]) == (
        "probe-agent/9.9",
        "other-agent/9.9",
    )
    assert first["origin_session"].startswith("mcp-")
    # One id per client connection, so two connections never share one.
    assert first["origin_session"] != second["origin_session"]


@pytest.mark.unit
def test_a_mirrored_brain_tool_call_records_origin_mcp() -> None:
    anyio.run(_call, "probe-agent")
    (row,) = _rows("protocols_supported")
    assert (row["origin"], row["origin_client"]) == ("mcp", "probe-agent/9.9")
    # Same connection as the energy call made just before it.
    (energy_row,) = _rows("substation_event_analysis")
    assert row["origin_session"] == energy_row["origin_session"]


@pytest.mark.unit
def test_the_scope_does_not_outlive_the_call() -> None:
    from iaiops.core.governance import origin as origin_mod

    anyio.run(_call, "probe-agent")
    assert origin_mod.current() is None
