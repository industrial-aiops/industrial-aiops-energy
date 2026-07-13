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

Current release: **0.1.5** (requires `iaiops>=0.9,<1.0`). New in 0.1.5: the IEC-104
**monitor path is now verified** — a real `c104` client↔server round-trip (link status →
general interrogation → point read, monitor-only) passes in a Linux container
(`tests/test_iec104_live.py`), joining DNP3 / IEC-61850 on the verified ladder; and a
callback-signature bug in the client-side station/point **auto-discovery** (added 0.1.4,
never runnable off-Linux) is fixed so a real outstation's points actually populate.
**Physical RTU still `待核实`.** Since 0.1.3 the server has
its **own MCP identity** — `iaiops-energy-mcp` runs a dedicated `FastMCP("iaiops-energy")`
instance with energy-specific instructions (IEC-104 / DNP3 / IEC-61850, read-first,
no control/operate), with the base cross-protocol brain tools mirrored onto it — plus
an **edition skill** (`skills/iaiops-energy/SKILL.md`, anti-drift-tested against the
registered tool surface) and **protocol-consistency contract tests** (every tool must
carry the governance marker, a `[READ]`-style risk tag, an `Args:` section, and the
canonical `{error, hint}` error shape; the server refuses to start if any registered
tool lacks the governance marker).

## 🧪 测试与共创 / Beta testing & co-creation

**变电站现场的测试反馈是这个包最缺的东西。** IEC-104 / DNP3 / IEC-61850 三条监视路径均已
对真实库(c104 / opendnp3 / libiec61850 的进程内 server)在 Linux 容器里 loopback 往返验证,但 **真实 RTU / IED
物理设备一律 `待核实`** —— 如果你能在授权的测试环境里对真实变电设备跑一遍
`iaiops doctor`,我们非常想听结果。经你验证的设备会署名写进支持矩阵。

**Live substation RTU / IED / IEC-104 field testing is what this package needs most.**
The IEC-104, DNP3 and IEC-61850 monitor paths are library-loopback-verified, but real gear stays
`待核实`. Report results (protocol + device model + `iaiops doctor` output) via the base
repo's pinned issue:
👉 [industrial-aiops#28 — Call for field-testing partners (v0.10.0)](https://github.com/industrial-aiops/industrial-aiops/issues/28)

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

## Edge deployment & ecosystem (edge-native / Margo)

Like the base package, the energy edition rides on a hardened, centrally-managed **edge host** as a
portable, governed **edge application** — mapping onto the [Margo](https://margo.org/)
edge-interoperability roles (immutable host · compliant orchestrator · **iaiops-energy = the
OT-domain app**), deployable as an OCI **Managed Container** (outbound-only to substation RTUs/IEDs,
no inbound). A container + `margo.org/v1-alpha1` application-description skeleton is in
[`deploy/margo/`](deploy/margo/); the full alignment + honest gap analysis lives in the base repo's
[`docs/MARGO-ALIGNMENT.md`](https://github.com/industrial-aiops/industrial-aiops/blob/main/docs/MARGO-ALIGNMENT.md).
> **Honest status:** a natural Margo edge application, but **NOT Margo-compliant yet** — image build,
> hosted+signed package, and a published conformance result are roadmap `⏳`. No claim of compliance
> until that result exists.

## Validation status (honest)

The same honesty ladder as the base repo. Driver **codec / API surface** is verified
against the real libraries; the mock/monkeypatched **unit tests run in CI** without
hardware. See the base repo's `docs/PREVIEW-VERIFICATION.md` runbook for how a
protocol is promoted.

| Protocol | Status | Evidence |
| --- | --- | --- |
| **DNP3 / IEEE 1815** | **verified (monitor path)** | Real master↔outstation round-trip against a live **opendnp3** outstation (`pydnp3`): `is_online()` reflects the real channel `OnStateChange`, and `integrity_poll()` (Class 0/1/2/3) returns the seeded binary/analog/counter database grouped by type. See `tests/test_dnp3_live.py` (`@pytest.mark.integration`, skips when `pydnp3` is absent). No physical RTU. |
| **IEC 60870-5-104** | **verified (monitor path)** | Real client↔server round-trip against an in-process **`c104`** server (`tests/test_iec104_live.py` + `tests/iec104_server_harness.py`, `@pytest.mark.integration`, passes in a Linux container): `iec104_connection_info` discovers the seeded station, `iec104_interrogate` (general interrogation / C_IC) returns the seeded `M_ME_NC_1` + `M_SP_NA_1` points with quality, `iec104_read_point` reads the measurand, a bad IOA yields `found=False` with **no fabricated value**, and server-side ASDU capture proves **no control ASDU** (C_SC / C_DC / C_SE) is ever issued. `c104` ships no macOS wheel so the test skips on macOS (runs in CI / Linux). No physical RTU. Monitor/read only. |
| **IEC 61850 (MMS)** | **verified (monitor path)** | Real client↔server MMS round-trip against an in-process **libiec61850** MMS server built with `pyiec61850`'s server API: `iec61850_device_directory` lists the logical device (and browses its logical nodes / data objects), and `iec61850_read` returns a seeded measurand (`TotW.mag.f`, FC `MX`) over real ISO-on-TCP; a bad reference surfaces an MMS data-access error instead of a fabricated value. See `tests/test_iec61850_live.py` (`@pytest.mark.integration`, skips when `pyiec61850` / its server API is absent). No physical IED. Read/monitor only — control / GOOSE / SV out of scope. |

DNP3 notes: read-only / monitor direction only (no control). `pydnp3` 0.1.0 ships no
wheel and needs a native opendnp3 build, so the live test runs in a Linux container;
its `DNP3Manager.Shutdown()` can block in a long-lived interpreter, so the connector
bounds teardown (`_Pydnp3MasterAdapter.shutdown`) and the test drives the round-trip
in a short-lived child process.

## License

MIT — © wei. Part of the vendor-neutral, governed Industrial-AIOps line.
