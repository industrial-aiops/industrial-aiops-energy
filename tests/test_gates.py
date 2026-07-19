"""The energy server must honour the base server's two registration gates.

WHY THIS FILE EXISTS
--------------------
This edition has no write tools and no egress tools of its OWN — every energy
connector (IEC-104 / DNP3 / IEC-61850) is monitor-only. That fact is a trap, not
a reassurance: it means a broken gate looks fine from the energy side while the
MIRRORED base brain tools (``historian_push``, ``rca_narrate``,
``stream_publish``, ``stream_publish_event``) stay exposed.

That was the real state before this change — ``register()`` applied neither
gate, so ``IAIOPS_NO_EGRESS=1`` on ``iaiops-energy-mcp`` was silently
ineffective while an operator believed it was on. On a 变电/电力 site, which is
where the compliance expectation is highest, a switch believed to be on is worse
than one known to be absent.

The assertions below are written against the DERIVED sets (whatever is currently
marked ``_risk_level``/``_egress``), never a hard-coded tool list, so a base
release that adds a write or egress tool is covered here the day it lands.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from mcp_server.noegress import apply_no_egress
from mcp_server.readonly import WRITE_RISK_LEVELS, apply_read_only

from iaiops_energy.mcp import server as energy_server
from iaiops_energy.mcp._app import mcp

pytestmark = pytest.mark.unit


@pytest.fixture
def registered_registry() -> Iterator[dict[str, Any]]:
    """Full energy surface registered, with the process-global registry restored."""
    energy_server.register()
    manager = mcp._tool_manager
    original = dict(manager._tools)
    try:
        yield original
    finally:
        manager._tools = original


def _risk_of(tool: Any) -> str | None:
    return getattr(getattr(tool, "fn", None), "_risk_level", None)


def _is_egress(tool: Any) -> bool:
    return bool(getattr(getattr(tool, "fn", None), "_egress", False))


def _writes(registry: dict[str, Any]) -> set[str]:
    return {n for n, t in registry.items() if _risk_of(t) in WRITE_RISK_LEVELS}


def _egress(registry: dict[str, Any]) -> set[str]:
    return {n for n, t in registry.items() if _is_egress(t)}


def test_mirrored_egress_tools_are_actually_present(registered_registry: dict[str, Any]) -> None:
    """Guard the guard: the gate tests below must not pass vacuously.

    If the base package ever stops mirroring egress-capable tools into this
    edition, the withholding assertions would succeed while proving nothing.
    """
    assert _egress(registered_registry), (
        "no egress-capable tool is mirrored into the energy surface — the "
        "no-egress assertions below would pass vacuously"
    )


def test_read_only_withholds_every_write_tool(registered_registry: dict[str, Any]) -> None:
    apply_read_only(mcp)
    assert not _writes(mcp._tool_manager._tools)


def test_no_egress_withholds_every_egress_tool(registered_registry: dict[str, Any]) -> None:
    withheld = apply_no_egress(mcp)
    assert not _egress(mcp._tool_manager._tools)
    assert set(withheld) == _egress(registered_registry)


def test_both_gates_compose(registered_registry: dict[str, Any]) -> None:
    """Neither gate may resurrect what the other withheld."""
    apply_read_only(mcp)
    apply_no_egress(mcp)
    remaining = mcp._tool_manager._tools
    assert not _writes(remaining)
    assert not _egress(remaining)
    assert remaining, "both gates on removed the entire surface — that is not a read-only tap"


def test_gates_leave_the_energy_protocol_tools_alone(
    registered_registry: dict[str, Any],
) -> None:
    """A monitor-only edition must lose nothing it needs to do its job."""
    energy_tools = {
        name
        for name, tool in registered_registry.items()
        if getattr(tool.fn, "__module__", "").startswith("iaiops_energy.")
    }
    assert energy_tools, "no energy-owned tools found — module prefix check is wrong"
    apply_read_only(mcp)
    apply_no_egress(mcp)
    assert energy_tools <= set(mcp._tool_manager._tools), (
        "a gate withheld an energy connector tool; this edition is monitor-only "
        "and must survive both gates intact"
    )


def test_governance_assertion_holds_under_both_gates(
    registered_registry: dict[str, Any],
) -> None:
    """Narrowing the surface must never leave it ungoverned."""
    apply_read_only(mcp)
    apply_no_egress(mcp)
    energy_server.assert_all_tools_governed()


def test_main_wires_both_gates() -> None:
    """The gates must be applied by the SERVER, not only reachable from tests.

    The defect this file was written for was exactly this: the modules were
    importable and the env vars were documented, but ``main()`` never called
    them, so the switches did nothing in production.
    """
    import inspect

    source = inspect.getsource(energy_server.main)
    assert "apply_read_only" in source, "main() never applies the read-only gate"
    assert "apply_no_egress" in source, "main() never applies the no-egress gate"
