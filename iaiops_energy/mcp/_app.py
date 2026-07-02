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

from mcp.server.fastmcp import FastMCP

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

mcp = FastMCP(SERVER_NAME, instructions=INSTRUCTIONS)
