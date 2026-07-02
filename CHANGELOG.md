# Changelog

All notable changes to `iaiops-energy` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **MCP server identity**: `iaiops-energy-mcp` now runs its OWN
  `FastMCP("iaiops-energy")` instance (`iaiops_energy/mcp/_app.py`) with
  energy-specific instructions covering IEC 60870-5-104 / DNP3 / IEC 61850,
  read-first governance, and the no-control/operate stance — instead of reusing
  the base package's shared `FastMCP("iaiops")` instance, whose instructions
  described the base protocol surface (OPC-UA / Modbus / S7 …) and disclaimed
  the energy edition ("ships separately"). The base cross-protocol brain tools
  are mirrored onto the energy instance at registration time.
- **PEP 604 unions in FastMCP-reflected tool signatures**: all energy tool
  signatures converted from `X | None` to `typing.Optional[X]` (base-repo rule —
  the union crashes FastMCP's `issubclass` check on older mcp/pydantic).
  Matching ruff `per-file-ignores` (`UP007`, `UP045`) added for
  `iaiops_energy/mcp/**` so the linter does not revert it.
- **Install hints**: tool-module docstrings now point at this package's extras
  (`pip install iaiops-energy[iec104]` / `[dnp3]` / `[iec61850]`) instead of the
  base's `iaiops[...]` extras, which were removed from the base in 0.8.0.
- **server.json metadata**: title corrected to "Industrial-AIOps Energy" and
  `environmentVariables` documented for the server's config surface
  (`IAIOPS_CONFIG`, `IAIOPS_MASTER_PASSWORD`).

### Added

- **Startup governance assertion**: the server refuses to start if any
  registered tool callable lacks the `_is_governed_tool` harness marker
  (defense-in-depth so a future unguarded tool cannot ship).
- **Protocol-consistency contract tests** (`tests/test_protocol_consistency.py`,
  ported from the base repo's pattern): every registered energy tool must carry
  the governance marker, start its docstring with a `[READ]`-style risk tag,
  document an `Args:` section, and return errors in the canonical
  `{error, hint}` shape; plus server-identity assertions.
- This `CHANGELOG.md`.

## [0.1.2] - 2026-07-01

Summarized from `RELEASE-0.1.2.md`.

### Added

- CI quality gate (mirrors the base repo): `pytest` (25 mock-based unit tests) +
  `ruff` + `bandit` (0 Medium+).
- `EnergyTarget` — extends the base `TargetConfig` with energy telecontrol
  addressing (IEC-104 ASDU `common_address`, DNP3 `master_address`); the energy
  protocols and default ports (2404 / 20000 / 102) register with the base config
  on import.
- Live integration tests: `tests/test_dnp3_live.py` (real `opendnp3` outstation)
  and `tests/test_iec61850_live.py` + `tests/iec61850_server_harness.py` (real
  in-process `libiec61850` MMS server); both skip cleanly when the binding is
  absent.

### Changed

- **DNP3 promoted to verified (monitor path)** against a real `opendnp3`
  outstation: real `ISOEHandler.Process` harvesting via `ForeachItem`, integrity
  poll via `ScanClasses(ClassField.AllClasses())`, `DefaultMasterApplication`
  from `asiodnp3`, log handler + held listener references (callback lifetime),
  bounded `shutdown()`, and channel `OnStateChange`-backed `is_online()`.
- **IEC 61850 promoted to verified (monitor path)** against a real in-process
  `libiec61850` MMS server: `[payload, IedClientError]` return-shape decoding,
  `LinkedList` walking, level-dispatched directory browsing (LD/LN/DO), MMS-type-
  aware value decoding, `MMS_DATA_ACCESS_ERROR` surfacing, and C-resource frees.
- IEC-104 remains **preview (待核实)** — mock-covered, not yet live-verified.
