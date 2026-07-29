"""Derive MCP ``ToolAnnotations`` from the governance harness.

Re-export of the base package's ``mcp_server.hints``. The two repos share
``@governed_tool``, so they must map its metadata onto the MCP hints identically —
a second implementation here could only drift.

This module briefly *was* a copy: the derivation shipped in both repos at once,
while the pin floor was still ``iaiops>=0.19`` and the base module first appeared
in 0.20.1. Raising the pin removed that reason, and the drift guard that watched
the copy (``tests/test_mcp_tool_hints.py``) went green against the real base
derivation before this file was collapsed.

Kept as a module rather than deleted so ``iaiops_energy.mcp`` has one obvious place
for hint derivation, and so a future divergence — if this edition ever needs a hint
the base cannot infer — has somewhere to live without touching every call site.
"""

from __future__ import annotations

from mcp_server.hints import hints_for

__all__ = ["hints_for"]
