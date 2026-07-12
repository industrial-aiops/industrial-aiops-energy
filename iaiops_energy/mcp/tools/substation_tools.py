"""Substation SOE protection-trip analysis — one governed, pure, read-only tool.

Registers ``substation_event_analysis`` onto the energy FastMCP instance. Unlike
the protocol tools it performs NO live protocol I/O and takes NO ``endpoint``:
an agent harvests the Sequence-of-Events (via the energy reads or a station
export) and feeds it in for a selectivity / breaker-failure / backup-zone
read-out. Governed at risk_level='low' (monitor direction only); the analysis
itself lives in ``iaiops_energy.analysis.substation``.
"""

from typing import Any

from iaiops.core.governance import governed_tool
from mcp_server._shared import tool_errors

from iaiops_energy.analysis import substation
from iaiops_energy.mcp._app import mcp


@mcp.tool()
@governed_tool(risk_level="low")
@tool_errors("dict")
def substation_event_analysis(
    events: list[dict[str, Any]],
    breaker_fail_window_s: float = 0.25,
    backup_margin_s: float = 0.5,
) -> dict:
    """[READ][risk=low] Analyse a substation Sequence-of-Events for protection selectivity.

    Pure structural analysis over INJECTED events (no live protocol I/O, no
    endpoint): given relay pickups/trips, breaker open/close, lockouts and bus
    undervoltage with ISO-8601 timestamps, decide what tripped and whether
    protection coordinated — a selective trip (one zone contained), a
    non-selective backup operation (wider outage), or a breaker failure.
    Monitor-only, advisory, cite-first (every claim ties to a timestamped event).

    Args:
        events: SOE list of {ref, timestamp (ISO-8601), type, label?}; ``type``
            is one of protection_pickup / protection_trip / breaker_open /
            breaker_close / lockout / bus_undervoltage (a free-text ``label`` is
            keyword-matched when ``type`` is absent or unknown). ``ref`` is the
            point name / IOA.
        breaker_fail_window_s: Breaker-failure timer — the tripped breaker's own
            open must be seen within this many seconds (default 0.25).
        backup_margin_s: Backup coordination margin — a breaker opening later
            than this past the first protection event is treated as backup
            operation (default 0.5).

    Returns dict: {events_analyzed, ignored, verdict, first_protection,
        first_breaker_open, breakers_opened, breaker_open_count, affected_refs,
        timeline, coordination{status, detail}, note}. ``verdict`` is one of
        selective_trip / backup_operation / breaker_failure / insufficient.

    Example: substation_event_analysis(events=[
        {"ref": "R1", "type": "protection_trip", "timestamp": "2026-07-12T10:00:00Z"},
        {"ref": "BK1", "type": "breaker_open", "timestamp": "2026-07-12T10:00:00.08Z"}]).
    """
    return substation.substation_event_analysis(
        events,
        breaker_fail_window_s=breaker_fail_window_s,
        backup_margin_s=backup_margin_s,
    )
