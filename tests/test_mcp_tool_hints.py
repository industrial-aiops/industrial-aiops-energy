"""MCP ``ToolAnnotations`` hints are DERIVED from the governance harness.

Mirrors the base repo's ``tests/test_mcp_tool_hints.py``. Two things are specific to
this edition:

* the mirrored base **brain** tools must be annotated too — they arrive through
  ``_mount_base_brain_tools`` rather than through ``@mcp.tool()``, so the mount path
  needs its own fallback;
* every energy protocol tool is monitor-direction only, so the whole native surface
  must come out ``readOnlyHint=True`` with nothing destructive. A destructive energy
  tool would mean control-direction code had appeared in a read-only edition.

The hints are declarative metadata for clients, never an authorisation gate —
enforcement stays in ``@governed_tool`` (base docs/HLD.md decision records D1/D3/D4).
"""

from __future__ import annotations

from typing import Any

import pytest
from iaiops.core.governance import governed_tool

from iaiops_energy.mcp.hints import hints_for


@pytest.mark.unit
def test_read_tool_is_read_only_and_not_destructive() -> None:
    @governed_tool(risk_level="low")
    def t() -> dict:
        return {}

    hints = hints_for(t)
    assert hints is not None
    assert hints.readOnlyHint is True
    assert hints.destructiveHint is False
    assert hints.openWorldHint is True


@pytest.mark.unit
def test_write_tool_is_destructive_and_not_read_only() -> None:
    @governed_tool(risk_level="high", preview_param="dry_run")
    def t(dry_run: bool = True) -> dict:
        return {}

    hints = hints_for(t)
    assert hints is not None
    assert hints.readOnlyHint is False
    assert hints.destructiveHint is True


@pytest.mark.unit
def test_egress_tool_is_not_read_only() -> None:
    """A low-risk tool that ships plant data off-box still acts on the world."""

    @governed_tool(risk_level="low", egress=True)
    def t() -> dict:
        return {}

    hints = hints_for(t)
    assert hints is not None
    assert hints.readOnlyHint is False
    assert hints.destructiveHint is False


@pytest.mark.unit
def test_medium_risk_is_neither_read_only_nor_destructive() -> None:
    @governed_tool(risk_level="medium")
    def t() -> dict:
        return {}

    hints = hints_for(t)
    assert hints is not None
    assert hints.readOnlyHint is False
    assert hints.destructiveHint is False


@pytest.mark.unit
def test_idempotent_flag_is_carried_through() -> None:
    @governed_tool(risk_level="medium", idempotent=True)
    def t() -> dict:
        return {}

    assert hints_for(t).idempotentHint is True


@pytest.mark.unit
def test_idempotent_is_unset_when_not_declared() -> None:
    """Undeclared means unspecified — never an assertion that repeats differ."""

    @governed_tool(risk_level="low")
    def t() -> dict:
        return {}

    assert hints_for(t).idempotentHint is None


@pytest.mark.unit
def test_ungoverned_function_gets_no_hints() -> None:
    def plain() -> dict:
        return {}

    assert hints_for(plain) is None


@pytest.mark.unit
def test_bare_decorator_still_raises_rather_than_registering_nothing() -> None:
    """``@mcp.tool`` without parens must keep failing loudly, as upstream does."""
    from iaiops_energy.mcp._app import _GovernedFastMCP

    server = _GovernedFastMCP("probe")

    def fn() -> dict:
        return {}

    with pytest.raises(TypeError, match="forget to call it"):
        server.tool(fn)
    assert not server._tool_manager._tools


@pytest.mark.unit
def test_explicit_annotations_win_over_the_derivation() -> None:
    from mcp.types import ToolAnnotations

    from iaiops_energy.mcp._app import _GovernedFastMCP

    server = _GovernedFastMCP("probe")
    override = ToolAnnotations(title="hand-written", readOnlyHint=False)

    @server.tool(annotations=override)
    @governed_tool(risk_level="low")
    def t() -> dict:
        return {}

    assert server._tool_manager._tools["t"].annotations == override


# ── whole-surface contract ────────────────────────────────────────────────────


@pytest.fixture
def registry() -> dict[str, Any]:
    from iaiops_energy.mcp._app import mcp
    from iaiops_energy.mcp.server import register

    register()
    return {tool.name: tool for tool in mcp._tool_manager.list_tools()}


@pytest.mark.unit
def test_every_registered_tool_is_annotated(registry: dict[str, Any]) -> None:
    """Includes the mirrored base brain tools, which do not go through @mcp.tool()."""
    missing = sorted(name for name, tool in registry.items() if tool.annotations is None)
    assert not missing, f"tools registered without MCP annotations: {missing}"


@pytest.mark.unit
def test_hints_agree_with_the_governance_harness(registry: dict[str, Any]) -> None:
    mismatched = [
        name
        for name, tool in sorted(registry.items())
        if hints_for(tool.fn) is None or tool.annotations != hints_for(tool.fn)
    ]
    assert not mismatched, f"annotations disagree with @governed_tool: {mismatched}"


@pytest.mark.unit
def test_no_energy_tool_is_destructive(registry: dict[str, Any]) -> None:
    """This edition exposes no control direction — nothing here may write to a device."""
    destructive = sorted(
        name for name, tool in registry.items() if tool.annotations.destructiveHint
    )
    assert not destructive, f"control-direction tools in a monitor-only edition: {destructive}"


@pytest.mark.unit
def test_hints_are_the_base_packages_derivation() -> None:
    """This module is a re-export; nothing may shadow or wrap the base derivation.

    Replaces the drift guard that watched the copy while the pin floor predated
    ``mcp_server.hints``. The copy is gone, so the only thing left to protect is
    that it stays gone — a future local reimplementation would silently reintroduce
    the divergence the copy was guarded against.
    """
    import mcp_server.hints

    assert hints_for is mcp_server.hints.hints_for
