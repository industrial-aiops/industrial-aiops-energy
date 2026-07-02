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

The same honesty ladder as the base repo. Driver **codec / API surface** is verified
against the real libraries; the mock/monkeypatched **unit tests run in CI** without
hardware. See the base repo's `docs/PREVIEW-VERIFICATION.md` runbook for how a
protocol is promoted.

| Protocol | Status | Evidence |
| --- | --- | --- |
| **DNP3 / IEEE 1815** | **verified (monitor path)** | Real master↔outstation round-trip against a live **opendnp3** outstation (`pydnp3`): `is_online()` reflects the real channel `OnStateChange`, and `integrity_poll()` (Class 0/1/2/3) returns the seeded binary/analog/counter database grouped by type. See `tests/test_dnp3_live.py` (`@pytest.mark.integration`, skips when `pydnp3` is absent). No physical RTU. |
| IEC 60870-5-104 | preview (`待核实`) | Not yet live-verified (no gear / simulator in CI). |
| **IEC 61850 (MMS)** | **verified (monitor path)** | Real client↔server MMS round-trip against an in-process **libiec61850** MMS server built with `pyiec61850`'s server API: `iec61850_device_directory` lists the logical device (and browses its logical nodes / data objects), and `iec61850_read` returns a seeded measurand (`TotW.mag.f`, FC `MX`) over real ISO-on-TCP; a bad reference surfaces an MMS data-access error instead of a fabricated value. See `tests/test_iec61850_live.py` (`@pytest.mark.integration`, skips when `pyiec61850` / its server API is absent). No physical IED. Read/monitor only — control / GOOSE / SV out of scope. |

DNP3 notes: read-only / monitor direction only (no control). `pydnp3` 0.1.0 ships no
wheel and needs a native opendnp3 build, so the live test runs in a Linux container;
its `DNP3Manager.Shutdown()` can block in a long-lived interpreter, so the connector
bounds teardown (`_Pydnp3MasterAdapter.shutdown`) and the test drives the round-trip
in a short-lived child process.

## License

MIT — © wei. Part of the vendor-neutral, governed Industrial-AIOps line.
