# industrial-aiops-energy v0.1.1

**Energy edition (变电 / 电力)** of [Industrial-AIOps](https://github.com/industrial-aiops/industrial-aiops)
— read-only OT connectors for substation / utility telecontrol, built on top of
the shared `iaiops.core` (governance / brain / runtime / normalized model).

## What it is

Three read-only, vendor-neutral energy protocol connectors + their MCP tools:

- **IEC 60870-5-104** (`c104`) — RTU / substation telemetry: link status, general
  interrogation, single-point read.
- **DNP3 / IEEE 1815** (`pydnp3` / opendnp3) — outstation monitoring: link status
  and Class 0/1/2/3 integrity poll, grouped by measurement type.
- **IEC 61850 MMS** (`pyiec61850`, linux-only wheel) — IED device directory,
  browse, and attribute read.

Control direction (CROB / analog-output / setpoints / C_SC…) is intentionally
**not exposed** — this edition is monitoring-only.

## Install

```bash
pip install iaiops-energy[energy]      # all three energy protocols
pip install iaiops-energy[iec104]      # just IEC-104
pip install iaiops-energy[dnp3]        # just DNP3
pip install iaiops-energy[iec61850]    # just IEC-61850 (Linux only)
```

`iaiops-energy` pulls in the base **`iaiops>=0.7,<0.8`** automatically. Importing the
package registers its three protocols (and their default ports 2404 / 20000 / 102)
with the shared base config. Protocol client libs are imported **lazily**, so the
package installs cleanly without them; a missing lib degrades to a teaching error.

Run the MCP server (brain + energy tools over stdio):

```bash
iaiops-energy-mcp
```

## Depends on iaiops core

This edition adds only the three energy connectors + session builders + MCP tools.
It reuses the base package's shared governance (audit / budget / risk-tier / undo),
the cross-protocol brain, the normalized ISA-95/18.2 model, and the MCP server
infrastructure. No control-direction writes are exposed.

## Changes since 0.1.0

- **CI quality gate** green: `pytest` (25 mock-based unit tests) + `ruff` +
  `bandit` (0 Medium+), mirroring the base repo's gate.
- Energy protocols (`iec104` / `dnp3` / `iec61850`) and their default ports are now
  **registered with the base config** on import, and an `EnergyTarget` type adds the
  energy-specific addressing the base is neutral about (IEC-104 ASDU
  `common_address`, DNP3 `master_address`).
- **DNP3 live link state**: the master adapter now wires opendnp3's channel
  `OnStateChange` callback, so `is_online()` reflects the real channel state
  (OPEN / CLOSED) instead of merely that `enable()` ran. Falls back to the
  enable-latch before the first callback (no regression if a binding's listener
  never fires).
- **DNP3 promoted to verified (monitor path)**: the master adapter was exercised
  against a **real `opendnp3` outstation** (`pydnp3`) end to end — link online +
  Class 0/1/2/3 integrity poll returning the seeded database. Fixes found and made
  while doing so (all read/monitor direction):
  - the SOE handler is now a real `opendnp3.ISOEHandler` whose `Process(info, values)`
    harvests each typed collection via `ForeachItem` (the previous plain collector
    was never called by opendnp3);
  - the integrity poll uses `ScanClasses(ClassField.AllClasses())` (the old code
    picked `ScanAllObjects`, which takes a `GroupVariationID`, not a `ClassField`);
  - `DefaultMasterApplication` is taken from `asiodnp3` (not `opendnp3`);
  - the `DNP3Manager` is built with a log handler (a null handler aborts on
    `Enable()`), and the Python channel-listener / SOE-handler are held as
    references (opendnp3 does not keep them alive → reactor-thread callbacks would
    hit freed objects);
  - `shutdown()` is now bounded so a blocking `DNP3Manager.Shutdown()` (a `pydnp3`
    0.1.0 teardown limitation) can never hang the caller.
  New `tests/test_dnp3_live.py` (`@pytest.mark.integration`) drives the real
  round-trip in a Linux container and **skips cleanly when `pydnp3` is absent**, so
  the default host suite is unchanged.

## Validation status (honest)

Same honesty ladder as the base repo.

- **DNP3 — verified (monitor path).** Exercised against a **real `opendnp3`
  outstation** (not physical gear): `is_online()` reflects the real channel
  `OnStateChange`, and `integrity_poll()` (Class 0/1/2/3) returns the seeded
  binary/analog/counter database grouped by type. Read-only; control is not
  exposed. The deeper **master link-layer status** (`IMasterApplication.OnStateChange`
  / `LinkStatus`) is still not wired — channel state is the verified signal.
- **IEC-104 / IEC-61850 — preview (`待核实`).** Driver codec / API surface written
  against the real libraries and covered by mock/monkeypatched unit tests; **live RTU
  / IED reads are NOT yet hardware- or simulator-verified** (no gear in CI).

See the base repo's `docs/PREVIEW-VERIFICATION.md` for how a protocol is promoted.

## License

MIT — © wei. Part of the vendor-neutral, governed Industrial-AIOps line.
