<!-- mcp-name: io.github.industrial-aiops/iaiops-energy -->

# industrial-aiops-energy — 能源 edition (变电 / 电力)

The **energy edition** of [Industrial-AIOps](https://github.com/industrial-aiops/industrial-aiops),
split out into its own repo: read-only OT connectors for **substation / utility
telecontrol** protocols, built **on top of `iaiops.core`**.

- **IEC 60870-5-104** (`c104`) — RTU / substation telemetry
- **DNP3 / IEEE 1815** (`pydnp3`) — outstation monitoring
- **IEC 61850 MMS** (`pyiec61850`, linux-only wheel) — substation IED reads

It reuses the base package's shared **governance** (audit / budget / risk-tier /
undo), **cross-protocol brain** (data-flow / alarm / OEE / downtime RCA on the
normalized ISA-95/18.2 model), and MCP server infrastructure — this repo only adds
the three energy connectors + their session builders + MCP tools. Read-first: no
control-direction writes are exposed.

## Why a separate repo

Energy targets a distinct buyer (utilities / substations), has heavier
platform-specific deps (`pyiec61850` is a linux-only SWIG wheel; `pydnp3` builds a
native ext), and its own compliance surface (电力监控系统安全防护). Splitting keeps
the base install light. See the base repo's `docs/ENERGY-SPINOUT.md` for the plan.

## Install

```bash
pip install iaiops-energy[energy]      # all three energy protocols
pip install iaiops-energy[iec104]      # just IEC-104
```

`iaiops-energy` pulls in `iaiops` (the shared core) automatically.

## Use (MCP)

```bash
iaiops-energy-mcp                       # brain + energy tools over stdio
```

Point a target at your substation gear in `~/.iaiops/config.yaml`
(`protocol: iec104|dnp3|iec61850`, `host`, `port`, `common_address` / `unit_id`).

## Validation status (honest)

The connectors are **preview (`待核实`)** against live gear — the same honesty ladder
as the base repo. Driver **codec / API surface** is verified against the real
libraries; the mock/monkeypatched **unit tests run in CI** without hardware. **Live
RTU / IED reads are not yet hardware-verified** (no gear in CI). See the base repo's
`docs/PREVIEW-VERIFICATION.md` runbook for how to promote a protocol to verified.

## License

MIT — © wei. Part of the vendor-neutral, governed Industrial-AIOps line.
