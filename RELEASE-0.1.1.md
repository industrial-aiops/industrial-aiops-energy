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

## Validation status (honest)

Same honesty ladder as the base repo — the connectors are **preview (`待核实`)**
against live gear:

- Driver **codec / API surface** is written against the real libraries; the
  **mock/monkeypatched unit tests run in CI** without hardware.
- **Live RTU / IED reads are NOT yet hardware-verified** (no gear in CI).
- **DNP3 `OnStateChange`**: the **channel-state** callback is wired and unit-tested
  (fake state change flips `is_online()`). The deeper **master link-layer status**
  (`IMasterApplication.OnStateChange` / `LinkStatus`) is not yet wired — `待核实`
  against a live outstation. The exact pydnp3 binding (SOEHandler / listener base
  classes, scan calls) may need adjustment against the installed `pydnp3` version.

See the base repo's `docs/PREVIEW-VERIFICATION.md` for how to promote a protocol to
verified.

## License

MIT — © wei. Part of the vendor-neutral, governed Industrial-AIOps line.
