"""DNP3 operations — read-only outstation telemetry (via the ``dnp3`` extra).

DNP3 (IEEE 1815) is widely used in electric/water utilities between a master and
field RTUs/outstations. This connector is **read-only monitoring**: link status
and an integrity poll (Class 0/1/2/3) that returns the outstation's measurement
database — binary inputs, analog inputs, counters — grouped by type. Control
(CROB/analog-output) is OT-dangerous and intentionally NOT exposed in this preview.

The opendnp3 binding is callback-heavy and isolated behind the adapter in
``iaiops_energy.connectors.dnp3.driver``. The binding/API shape is loopback-verified
against an in-process opendnp3 outstation (see ``tests/test_dnp3_live.py``); a
PHYSICAL outstation is 待核实. The ops below work against that adapter's uniform
interface and are mock-testable.
"""

from __future__ import annotations

from typing import Any

from iaiops.core.brain._shared import num, s
from iaiops.core.runtime.connection import OTConnectionError

from iaiops_energy.runtime.sessions import dnp3_session

MAX_POINTS = 5000


def _point_brief(p: dict) -> dict:
    """Normalize one adapter point dict to a JSON-safe descriptor."""
    raw = p.get("value")
    return {
        "type": s(p.get("type", ""), 32),
        "group": p.get("group"),
        "index": p.get("index"),
        "value": num(raw) if num(raw) is not None else s(raw, 64),
        "quality": s(p.get("quality", ""), 48),
        "timestamp": s(p.get("timestamp", ""), 40),
    }


def dnp3_link_status(target: Any) -> dict:
    """[READ] Bring the master online and report the link/outstation status.

    ``online`` is the verified channel-state reading; ``link_layer`` adds the
    deeper master-application signals (keep-alive/link result + whether any IIN
    bits were seen) when the pydnp3 build exposes ``IMasterApplication`` — 待核实
    against a live outstation.
    """
    with dnp3_session(target) as adapter:
        online = bool(adapter.is_online())
        link_layer = adapter.link_status() if hasattr(adapter, "link_status") else None
    return {
        "endpoint": s(getattr(target, "name", ""), 64),
        "host": s(getattr(target, "host", ""), 40),
        "port": int(getattr(target, "port", 0) or 20000),
        "outstation_address": int(getattr(target, "unit_id", 0) or 0),
        "master_address": int(getattr(target, "master_address", 0) or 1),
        "online": online,
        "link_layer": link_layer,
        "note": "DNP3 read-only link check (channel state + master link-layer "
        "signals). Control (CROB / analog output) is not exposed in this preview.",
    }


def dnp3_integrity_poll(target: Any) -> dict:
    """[READ] Class 0/1/2/3 integrity poll → the outstation's measurement database.

    Returns all static points grouped by measurement type (binary_input,
    analog_input, counter, …) plus per-type counts.
    """
    with dnp3_session(target) as adapter:
        raw = list(adapter.integrity_poll() or [])[:MAX_POINTS]
    points = [_point_brief(p) for p in raw]
    by_type: dict[str, int] = {}
    for p in points:
        by_type[p["type"]] = by_type.get(p["type"], 0) + 1
    return {
        "endpoint": s(getattr(target, "name", ""), 64),
        "outstation_address": int(getattr(target, "unit_id", 0) or 0),
        "point_count": len(points),
        "by_type": by_type,
        "points": points,
        "note": "Integrity poll (Class 0/1/2/3), monitor direction. Static snapshot "
        "of the outstation database.",
    }


__all__ = ["dnp3_link_status", "dnp3_integrity_poll", "OTConnectionError"]
