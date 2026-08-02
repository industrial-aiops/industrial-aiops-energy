"""The energy edition's OWN FastMCP instance and server identity.

The energy server must not reuse the base package's shared ``FastMCP("iaiops")``
instance: its instructions describe the base protocol surface (OPC-UA / Modbus /
S7 …) and disclaim the energy edition, which would misdirect any agent connecting
to ``iaiops-energy-mcp``. Energy tool modules import ``mcp`` from here and
register onto this instance; ``iaiops_energy.mcp.server`` additionally mirrors
the base cross-protocol brain tools onto it.

Rule inherited from the base repo (``mcp_server/_shared.py``): keep
``Optional[X]`` (never PEP 604 ``X | None``) in any FastMCP-reflected tool
signature — on older mcp/pydantic the union eval'd to ``types.UnionType``
crashes FastMCP's ``issubclass`` check.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.types import Icon, ToolAnnotations

from iaiops_energy import __version__
from iaiops_energy.mcp.hints import hints_for

SERVER_NAME = "iaiops-energy"

INSTRUCTIONS = (
    "Governed, vendor-neutral, READ-FIRST energy/substation telecontrol data tap "
    "— the ENERGY edition of Industrial-AIOps (built on the iaiops base package). "
    "Protocols: IEC 60870-5-104 (RTU/substation link status, general "
    "interrogation, single monitored-point reads by IOA), DNP3 / IEEE 1815 "
    "(outstation link status, Class 0/1/2/3 integrity poll grouped by "
    "measurement type), and IEC 61850 MMS (IED logical-device directory, model "
    "browse, data-attribute reads by object reference + functional constraint). "
    "ALL energy tools are monitor-direction only: control/operate — CROB, analog "
    "output, setpoints, select-before-operate, IEC-104 command ASDUs (C_SC/C_DC/"
    "C_SE) — is intentionally NOT exposed. 未经授权勿对生产控制系统写入. The "
    "cross-protocol brain from the base package (diagnostics, OEE/downtime "
    "analytics, asset inventory, compliance self-assessment) is mounted on this "
    "server as well. An 'endpoint' selects a target from config (path via the "
    "IAIOPS_CONFIG env var); secrets live in an encrypted store unlocked via "
    "IAIOPS_MASTER_PASSWORD; every tool runs through the iaiops governance "
    "harness (audit / budget / risk-tier). Protocol client libs are optional "
    "extras (pip install 'iaiops-energy[iec104]' / '[dnp3]' / '[iec61850]'); a "
    "missing lib degrades to a teaching error, not a crash. Do NOT use for "
    "general IT/network devices, Kubernetes, hypervisors, or backups — this is "
    "OT telecontrol telemetry only. Need another protocol/action? Open a GitHub "
    "issue or PR on industrial-aiops/industrial-aiops-energy."
)


class _GovernedFastMCP(FastMCP):
    """FastMCP that annotates every tool from its ``@governed_tool`` metadata.

    ``@mcp.tool()`` is the OUTERMOST decorator on every energy tool, so the function
    it receives already carries the governance attributes ``hints_for`` reads. Doing
    the derivation here — once — keeps the registration sites free of hand-written
    hints that could drift from the risk tier they describe. Mirrors
    ``_GovernedFastMCP`` in the base repo's ``mcp_server/_shared.py``.

    Note this covers the tools registered *here*; the base brain tools mirrored in by
    ``iaiops_energy.mcp.server._mount_base_brain_tools`` arrive via ``add_tool`` and
    are annotated on that path instead.

    An explicit ``annotations=`` argument still wins.

    The signature mirrors ``FastMCP.tool`` keyword for keyword rather than taking
    ``*args, **kwargs``. A widened signature would silently absorb upstream's "did
    you forget to call it?" guard — ``@mcp.tool`` without parentheses would stop
    raising and start registering nothing at all, so the tool would vanish from the
    surface with no error to notice.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        # FastMCP takes no `version`, and the low-level server it builds defaults
        # to None — so the initialize handshake reported the MCP SDK's version as
        # THIS server's. A client asking which iaiops-energy it is talking to was
        # told about the `mcp` package. Mirrors the same fix in the base repo's
        # mcp_server/_shared.py (2026-08-02).
        self._mcp_server.version = __version__

    def tool(
        self,
        name: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        annotations: Optional[ToolAnnotations] = None,
        icons: Optional[list[Icon]] = None,
        meta: Optional[dict[str, Any]] = None,
        structured_output: Optional[bool] = None,
    ) -> Callable:
        if callable(name):
            raise TypeError(
                "The @tool decorator was used incorrectly. "
                "Did you forget to call it? Use @tool() instead of @tool"
            )

        def decorator(fn: Callable) -> Callable:
            return super(_GovernedFastMCP, self).tool(
                name=name,
                title=title,
                description=description,
                annotations=annotations if annotations is not None else hints_for(fn),
                icons=icons,
                meta=meta,
                structured_output=structured_output,
            )(fn)

        return decorator


mcp = _GovernedFastMCP(SERVER_NAME, instructions=INSTRUCTIONS)
