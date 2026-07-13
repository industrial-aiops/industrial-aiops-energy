"""Anti-drift sync between the edition skill and the actual server surface.

``skills/iaiops-energy/SKILL.md`` is what an agent reads to decide whether and
how to use this server, so it must never drift from reality:

  - every ``@mcp.tool``-registered energy tool name must appear in the skill
    (a shipped-but-undocumented tool is invisible to agents; a documented-but-
    unregistered tool would be hallucination bait); and
  - the library pins quoted in the skill's support-version matrix must match
    the pins actually declared in ``pyproject.toml`` extras.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from iaiops_energy.mcp import server as energy_server
from iaiops_energy.mcp._app import mcp

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = REPO_ROOT / "skills" / "iaiops-energy" / "SKILL.md"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

# The extras whose (single) protocol-lib pin the skill matrix must quote.
PROTOCOL_EXTRAS = ("iec104", "dnp3", "iec61850")

ENERGY_TOOL_PREFIXES = ("iec104_", "dnp3_", "iec61850_")


@pytest.fixture(scope="module", autouse=True)
def _registered() -> None:
    """Register the full energy surface once (idempotent)."""
    energy_server.register()


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not SKILL_PATH.is_file():
        pytest.fail(f"edition skill missing: {SKILL_PATH}")
    return SKILL_PATH.read_text(encoding="utf-8")


def _registered_energy_tool_names() -> tuple[str, ...]:
    return tuple(name for name in mcp._tool_manager._tools if name.startswith(ENERGY_TOOL_PREFIXES))


def _protocol_pins_from_pyproject() -> dict[str, str]:
    """Extra name → bare pin spec (environment marker stripped)."""
    with PYPROJECT_PATH.open("rb") as fh:
        pyproject = tomllib.load(fh)
    extras = pyproject["project"]["optional-dependencies"]
    pins: dict[str, str] = {}
    for extra in PROTOCOL_EXTRAS:
        requirements = extras[extra]
        assert len(requirements) == 1, (
            f"extra {extra!r} now has {len(requirements)} requirements; "
            f"update the skill matrix and this test"
        )
        pins[extra] = requirements[0].split(";")[0].strip()
    return pins


def test_every_registered_energy_tool_is_documented_in_skill(skill_text: str) -> None:
    """A shipped energy tool the skill never names is invisible to agents."""
    names = _registered_energy_tool_names()
    assert names, "no energy tools registered — server registration is broken"
    missing = tuple(name for name in names if f"`{name}`" not in skill_text)
    assert not missing, f"energy tools registered but absent from SKILL.md: {missing}"


def test_skill_does_not_document_phantom_energy_tools(skill_text: str) -> None:
    """Every backticked energy-prefixed name in the skill must really exist."""
    documented = set(re.findall(r"`((?:iec104|dnp3|iec61850)_[a-z0-9_]+)`", skill_text))
    registered = set(_registered_energy_tool_names())
    phantoms = documented - registered
    # ``iec104_session`` is the connector-internal session builder cited as
    # loopback-verification evidence, not an MCP tool.
    phantoms -= {"iec104_session"}
    assert not phantoms, f"SKILL.md documents unregistered energy tools: {sorted(phantoms)}"


def test_skill_matrix_pins_match_pyproject(skill_text: str) -> None:
    """The pins quoted in the skill matrix must be pyproject's, verbatim."""
    for extra, pin in _protocol_pins_from_pyproject().items():
        assert f"`{pin}`" in skill_text, (
            f"pyproject extra {extra!r} pins {pin!r} but SKILL.md quotes "
            f"something else — update the support-version matrix"
        )


def test_skill_keeps_honest_unverified_marking(skill_text: str) -> None:
    """Live RTU/IED runs are still unproven — the skill must say 待核实."""
    assert "待核实" in skill_text
