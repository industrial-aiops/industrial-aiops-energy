"""Credential-redaction contract for the energy MCP surface.

Mirrors the base repo's ``tests/test_credential_redaction_contract.py``. It is
worth having here rather than trusting the base's copy because **this edition's
registered surface is not the base's**: the three egress tools that leaked
(``stream_publish``, ``stream_publish_event``, ``historian_push``) reach this
server through ``_mount_base_brain_tools``, not through ``@mcp.tool()``, so a base
fix only lands here once the pin moves — which is exactly the window in which this
edition shipped the leak while the base was already fixed.

The energy connectors take no credential parameters of their own (substation
targets are addressed by host / common-address / unit-id, and secrets come from
the encrypted store by name). This test therefore mostly guards the *mirrored*
surface plus anything added here later.

There is no CLI in this package, so the base's two-front-end assertion has no
counterpart; the base repo covers ``iaiops``'s CLI.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

# Substrings that mark a parameter as carrying a credential value.
_CREDENTIAL_HINTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "credential",
    "private_key",
)

# Parameters whose name matches a hint but which hold a REFERENCE to a credential
# rather than the credential itself — redacting them would blind the audit trail
# while protecting nothing. Kept identical to the base repo's list on purpose: the
# two surfaces overlap, so a divergence here would be a divergence in what the two
# packages consider a secret.
_REFERENCE_NOT_SECRET = frozenset({"secret_name"})


@pytest.fixture
def registry() -> dict[str, Any]:
    from iaiops_energy.mcp._app import mcp
    from iaiops_energy.mcp.server import register

    register()
    return {tool.name: tool for tool in mcp._tool_manager.list_tools()}


def _undeclared_credentials(name: str, fn: Any) -> list[str]:
    declared = set(getattr(fn, "_sensitive_params", []) or [])
    try:
        params = inspect.signature(inspect.unwrap(fn)).parameters
    except (TypeError, ValueError):  # pragma: no cover - builtins have no signature
        return []
    return [
        f"{name}.{param}"
        for param in params
        if param not in _REFERENCE_NOT_SECRET
        and param not in declared
        and any(hint in param.lower() for hint in _CREDENTIAL_HINTS)
    ]


@pytest.mark.unit
def test_no_registered_tool_audits_a_credential_in_the_clear(registry) -> None:
    assert registry, "expected tools to be registered"
    leaks = sorted(
        leak for name, tool in registry.items() for leak in _undeclared_credentials(name, tool.fn)
    )
    assert not leaks, (
        "credential params not declared in sensitive_params — these land in "
        f"audit.db (and any SIEM forward) verbatim: {leaks}"
    )


@pytest.mark.unit
def test_the_mirrored_egress_tools_are_the_ones_being_guarded(registry) -> None:
    """Pins the reason this file exists in a package that defines no credential params.

    If these three stop being mirrored, the test above would pass vacuously and
    nobody would notice the guard had become decorative. It should then be this
    assertion that fails, saying so.
    """
    mirrored = {"stream_publish", "stream_publish_event", "historian_push"}
    missing = sorted(mirrored - set(registry))
    assert not missing, (
        f"expected the base egress tools to be mirrored here: {missing} — if they were "
        "deliberately dropped, drop this assertion too"
    )
    for name in mirrored:
        declared = set(getattr(registry[name].fn, "_sensitive_params", []) or [])
        assert declared, f"{name} arrived from the base package with no credential declared"
