"""Energy-edition tool-contract consistency — ported from the base repo's
``test_protocol_consistency.py`` / ``test_smoke.py`` meta-test pattern.

Every energy MCP tool is wired through several independent conventions:

  - the ``@governed_tool`` harness marker (``_is_governed_tool``) — audit /
    budget / risk-tier;
  - a docstring that STARTS with a risk tag (this edition is monitor-only, so
    every tool must be ``[READ]``) and documents an ``Args:`` section;
  - the canonical ``@tool_errors`` failure shape ``{error, hint}``.

Drift in any of them is a latent bug (an ungoverned tool, an agent that cannot
judge risk, an error a model cannot recover from). These assertions pin them
together, plus the server's own identity (fixed in the [Unreleased] changelog:
the energy server must not reuse/disclaim the base ``iaiops`` identity).
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from iaiops_energy.mcp import server as energy_server
from iaiops_energy.mcp._app import mcp

pytestmark = pytest.mark.unit

# Every energy protocol tool is monitor-direction only in this edition.
ENERGY_TOOL_PREFIXES = ("iec104_", "dnp3_", "iec61850_")
EXPECTED_ENERGY_TOOLS = frozenset(
    {
        "iec104_connection_info",
        "iec104_interrogate",
        "iec104_read_point",
        "dnp3_link_status",
        "dnp3_integrity_poll",
        "iec61850_device_directory",
        "iec61850_browse",
        "iec61850_read",
    }
)

# Dummy values per annotation for calling a tool's required params in the
# error-shape probe (the endpoint resolver is forced to raise, so values are
# never interpreted).
_DUMMY_BY_ANNOTATION: dict[Any, Any] = {int: 1, str: "x", bool: False, float: 1.0}


@pytest.fixture(scope="module", autouse=True)
def _registered() -> None:
    """Register the full energy surface once (idempotent)."""
    energy_server.register()


def _all_tools() -> dict[str, Any]:
    return dict(mcp._tool_manager._tools)


def _energy_tools() -> dict[str, Any]:
    return {
        name: tool
        for name, tool in _all_tools().items()
        if name.startswith(ENERGY_TOOL_PREFIXES)
    }


def test_server_has_energy_identity() -> None:
    """The server must present as iaiops-energy and describe THIS edition."""
    assert mcp.name == "iaiops-energy"
    instructions = mcp.instructions or ""
    for protocol in ("IEC 60870-5-104", "DNP3", "IEC 61850"):
        assert protocol in instructions, f"instructions never mention {protocol!r}"
    for stance in ("READ-FIRST", "governance"):
        assert stance in instructions, f"instructions never state {stance!r}"
    assert "NOT exposed" in instructions, "instructions must state no control/operate tools"
    # The base instance's text disclaims the energy edition — must not leak here.
    assert "ships separately" not in instructions, (
        "server is reusing the base iaiops instructions (self-disclaiming identity)"
    )


def test_expected_energy_tools_are_registered() -> None:
    registered = set(_energy_tools())
    assert EXPECTED_ENERGY_TOOLS <= registered, (
        f"missing energy tools: {EXPECTED_ENERGY_TOOLS - registered}"
    )


def test_every_registered_tool_is_governed() -> None:
    """Every tool callable (brain + energy) must carry the harness marker."""
    for name, tool in _all_tools().items():
        fn = getattr(tool, "fn", None)
        assert fn is not None, f"{name} has no fn"
        assert getattr(fn, "_is_governed_tool", False), (
            f"{name} is not wrapped with @governed_tool (harness marker missing)"
        )


def test_startup_governance_assertion_accepts_current_surface() -> None:
    """The startup defense-in-depth check must pass for the shipped surface."""
    energy_server.assert_all_tools_governed()


def test_startup_governance_assertion_rejects_ungoverned_tool() -> None:
    """An unguarded tool must abort startup, not silently ship."""

    def sneaky_ungoverned_tool() -> dict:
        """[READ][risk=low] A tool that skipped the governance harness.

        Args:
            (none)
        """
        return {}

    mcp._tool_manager.add_tool(sneaky_ungoverned_tool)
    try:
        with pytest.raises(RuntimeError, match="sneaky_ungoverned_tool"):
            energy_server.assert_all_tools_governed()
    finally:
        mcp._tool_manager.remove_tool("sneaky_ungoverned_tool")


def test_every_energy_tool_docstring_declares_read_risk_tag() -> None:
    """Monitor-only edition: every docstring starts with a [READ] risk tag."""
    for name, tool in _energy_tools().items():
        doc = inspect.getdoc(tool.fn) or ""
        assert doc.startswith("[READ]"), (
            f"{name} docstring must start with a '[READ]' risk tag, got: {doc[:40]!r}"
        )


def test_every_energy_tool_docstring_has_args_section() -> None:
    for name, tool in _energy_tools().items():
        doc = inspect.getdoc(tool.fn) or ""
        assert "Args:" in doc, f"{name} docstring lacks an 'Args:' section"


def test_every_energy_tool_signature_avoids_pep604_optionals() -> None:
    """Base-repo rule: FastMCP-reflected signatures use Optional[X], not X | None."""
    for name, tool in _energy_tools().items():
        source = inspect.getsource(inspect.unwrap(tool.fn))
        signature_src = source.split('"""', 1)[0]
        assert "| None" not in signature_src, (
            f"{name} signature uses a PEP 604 union; use typing.Optional[X] "
            "(crashes FastMCP's issubclass check on older mcp/pydantic)"
        )


def test_every_energy_tool_error_response_has_error_and_hint(monkeypatch) -> None:
    """Failures must return the canonical {error, hint} teaching shape."""
    for module_name in energy_server.ENERGY_TOOL_MODULES:
        module = __import__(
            f"iaiops_energy.mcp.tools.{module_name}", fromlist=[module_name]
        )

        def _boom(_name: Any = None) -> Any:
            raise ValueError("contract-test forced failure")

        # Pure-analysis modules (e.g. substation_tools) resolve no endpoint and
        # have no ``_target`` to force-fail; only the protocol tools do.
        if hasattr(module, "_target"):
            monkeypatch.setattr(module, "_target", _boom)

    for name, tool in _energy_tools().items():
        kwargs = {
            param.name: _DUMMY_BY_ANNOTATION[param.annotation]
            for param in inspect.signature(tool.fn).parameters.values()
            if param.default is inspect.Parameter.empty
        }
        result = tool.fn(**kwargs)
        assert isinstance(result, dict), f"{name} error response is not a dict"
        assert "error" in result and "hint" in result, (
            f"{name} error response must follow the {{error, hint}} shape, got "
            f"{sorted(result)}"
        )
        assert "contract-test forced failure" in result["error"]
