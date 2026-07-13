# Changelog

All notable changes to `iaiops-energy` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.5] — 2026-07-13

> **IEC-104 promoted to `verified (monitor path)` + a real connector fix.** The `c104`
> client↔server round-trip now **passes in a Linux container** (`tests/test_iec104_live.py`),
> so IEC-104 joins DNP3 / IEC-61850 on the verified ladder (physical RTU still `待核实`).
> Getting there exposed a genuine bug shipped in 0.1.4: the client-side station/point
> **auto-discovery callbacks** (and the test server's `on_receive_raw` callback) were annotated
> `Any` / stringized by `from __future__ import annotations`, which `c104` **strictly rejects**
> — so discovery would have failed against any real c104 RTU. Fixed by setting the exact
> `c104`-expected signatures (`(client: c104.Client, connection: c104.Connection, common_address: int)`
> etc.) as real objects. No API change; monitor-only preserved. README + skill matrix flipped to
> verified. The existing CI (`pip install -e .[iec104,dev]` + `pytest -q`, integration not
> deselected) now runs this round-trip on every push.

## [0.1.4] — 2026-07-13

> **IEC-104 verification scaffolding + a real monitor-path fix.** Adds the in-process
> `c104` server-loopback harness + live test (mirrors DNP3 / IEC-61850) and the client-side
> station/point auto-discovery the connector was missing, so a general interrogation actually
> populates the model. **IEC-104 stays `preview (待核实)`** — the live test skips off-Linux
> (no macOS `c104` wheel); promote it by running `pytest -m integration` on Linux with `c104`.
> Also corrects a skill-matrix row that overclaimed IEC-104 as loopback-verified.

### Added — IEC-104 live round-trip scaffolding (NOT yet promoted)

- **`tests/iec104_server_harness.py` + `tests/test_iec104_live.py`**
  (`@pytest.mark.integration`): an in-process **real `c104` IEC-104 server**
  seeded with a measured value (`M_ME_NC_1` @ IOA 1001 = 50.0) and a single point
  (`M_SP_NA_1` @ IOA 1002) on ASDU common address 47, plus a live test that drives
  the connector's `iec104_connection_info` → `iec104_interrogate` →
  `iec104_read_point` against it over the real TCP/2404 profile in a short-lived
  child process (mirrors the DNP3 / IEC-61850 live tests). Asserts the seeded
  points round-trip with correct values/quality, that a bad IOA returns
  `found=False` with **no fabricated value**, and — via server-side ASDU-TypeID
  capture — that **no control command (C_SC / C_DC / C_SE …) is ever issued**
  (only C_IC general interrogation). Skips cleanly when `c104` is absent.
- **Connector monitor-path fixes** (needed for the read to work against a real
  RTU/server): `_build_iec104_client` now registers `on_new_station` /
  `on_new_point` auto-discovery callbacks (the documented c104 client pattern, so
  a general interrogation populates the client model), and the IEC-104 ops issue a
  best-effort general interrogation (`C_IC` / Class 0) before reading. Monitor
  direction only — no control point is ever created client-side.
- **Honesty:** `c104` ships no wheel for macOS and its 2.2.1 sdist fails to compile
  under Apple Clang in the dev env, so the live test currently **SKIPS locally** —
  the round-trip has **not** been executed here. IEC 60870-5-104 therefore stays
  **`preview (待核实)`** in the README/skill matrix; it is promoted to
  `verified (monitor path)` only once this test genuinely runs and passes against a
  real `c104` server (Linux/CI where the binding builds).

### Added — substation intelligence (SOE protection-trip analysis)

- **`substation_event_analysis` MCP tool** + `iaiops_energy/analysis/substation.py`:
  a pure, read-only Sequence-of-Events analysis that reasons over INJECTED events
  (relay pickups/trips, breaker open/close, lockouts, bus undervoltage) and returns
  a coordination `verdict` — `selective_trip` / `backup_operation` / `breaker_failure`
  / `insufficient` — with cite-first detail (every claim tied to a timestamped event).
  No live protocol I/O and no `endpoint`: an agent harvests the SOE and feeds it in.
  Monitor-only by design (governed at `risk=low`); tolerant timestamp parsing
  (trailing `Z`, mixed tz) and free-text `label` keyword inference; all output lists
  bounded. Registered in `ENERGY_TOOL_MODULES`, documented in the edition skill.

### Added — edge-native / Margo ecosystem alignment (docs + packaging skeleton)

- Mirrors the base repo's Margo positioning: `deploy/margo/` container + `margo.org/v1-alpha1`
  application-description skeleton (`Dockerfile` running `iaiops-energy-mcp`, hardened `compose.yaml`,
  `margo.yaml`); README "edge-native / Margo" subsection; `pyproject` keywords
  `+= edge/iiot/edge-computing/margo/edge-interoperability`.
- **Honesty:** NOT Margo-compliant yet — image build, hosted+signed package, and a conformance
  result are roadmap `⏳`. Every unconfirmed field marked `待核实`.

## [0.1.3] — 2026-07-02

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

- **Edition skill** (`skills/iaiops-energy/SKILL.md`): agent-facing routing +
  usage guide for the energy server — trigger-rich description (IEC-104 / DNP3 /
  IEC 61850 MMS / substation / RTU / IED / 遥测遥信; GOOSE/SV explicitly out of
  scope), the 8 monitor-only protocol tools, mounted base-brain note, honest
  support-version matrix (lib pins + 待核实 status), doctor-first workflow, and
  a redirect of factory/building/process protocols to the base `iaiops` server;
  anti-drift test `tests/test_skill_sync.py` pins the skill to the registered
  tool surface and to pyproject's protocol-lib pins.
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
