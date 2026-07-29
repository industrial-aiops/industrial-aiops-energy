"""Derive MCP ``ToolAnnotations`` from the governance harness.

Mirrors the base repo's ``mcp_server/hints.py``. It is duplicated rather than
imported because this package pins ``iaiops>=0.19``, and the base module first
ships in the release *after* 0.19.0 — importing it would break every install on the
supported floor. Once the pin can be raised this module collapses to a re-export;
until then ``tests/test_mcp_tool_hints.py`` asserts the two derivations agree
whenever the installed base package does carry one, so they cannot drift silently.

``@governed_tool`` (shared with the base package) already declares what a tool does
to the world. Translating that into the four MCP hints lets a client — not just a
human reading the ``[READ]``/``[WRITE]`` docstring tag — tell a monitor read from a
tool that acts, and put a confirm prompt in front of the latter.

**These are hints, not a gate.** The MCP spec is explicit that annotations must not
be relied on for security decisions, and this line agrees: authorisation is the
caller's call, the tap's guarantee is un-bypassable audit (base docs/HLD.md decision
records D1/D3/D4). Enforcement stays entirely in ``@governed_tool``.

Every tool in *this* edition is monitor-direction only, so in practice the native
surface derives to ``readOnlyHint=True`` throughout; the write branches exist for the
mirrored base brain tools and to keep the mapping identical to the base repo's.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.types import ToolAnnotations

# Risk tiers whose real (non-preview) call changes device state.
_DESTRUCTIVE_TIERS = ("high", "critical")


def hints_for(fn: Any) -> Optional[ToolAnnotations]:
    """Return the hints implied by ``fn``'s ``@governed_tool`` metadata.

    Returns ``None`` for a function carrying no governance metadata — an honest
    "unknown" beats guessing ``readOnlyHint`` for something we know nothing about.

    ``readOnlyHint`` is deliberately narrow: low risk AND no dry-run/preview
    parameter (having one means the tool has a real write mode) AND no egress.
    Egress matters because a tool can ship plant data to a caller-named destination
    without touching a device — low risk, but emphatically not read-only.
    ``openWorldHint`` is always true: every tool reaches substation equipment or an
    external system, never a closed local domain.
    """
    if not getattr(fn, "_is_governed_tool", False):
        return None

    risk_level = getattr(fn, "_risk_level", "low")
    has_write_mode = getattr(fn, "_preview_param", None) is not None
    egresses = bool(getattr(fn, "_egress", False))

    return ToolAnnotations(
        readOnlyHint=risk_level == "low" and not has_write_mode and not egresses,
        destructiveHint=risk_level in _DESTRUCTIVE_TIERS,
        idempotentHint=bool(getattr(fn, "_idempotent", False)),
        openWorldHint=True,
    )
