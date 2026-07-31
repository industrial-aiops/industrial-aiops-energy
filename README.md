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

Current release: **0.1.10** (requires `iaiops>=0.20.2,<1.0`). New in 0.1.10 — a **security
fix inherited from the base package**: three egress tools this edition mirrors
(`stream_publish`, `stream_publish_event`, `historian_push`) wrote their credential — a NATS
auth token, a TSDB password — into the audit log in the clear, and `audit_forward` shipped
that row to the configured SIEM. They are defined in `iaiops`, so this edition could not fix
it alone; the pin moves to `iaiops>=0.20.2`, and a contract test now fails the build if the
whole registered surface ever again carries an undeclared credential parameter. **If you have
passed a token or historian password to these tools, rotate it** and check existing audit
rows. The energy connectors themselves take no credential parameters. Previously in 0.1.9 — every tool
ships the MCP `ToolAnnotations` hints (`readOnlyHint` / `destructiveHint` / `openWorldHint`),
**derived** from the `@governed_tool` harness rather than hand-written, so a client can tell a
monitor read from a tool that acts without parsing the `[READ]`/`[WRITE]` docstring tag. On the
wire that is 59 tools, 55 read-only and **0 destructive** — this edition exposes no control
direction, and that is now enforced by a test rather than only documented. They are hints, not a
gate: the MCP spec forbids relying on annotations for security decisions, and enforcement stays in
`@governed_tool`. The base pin moved to `iaiops>=0.20.1` so the hint derivation is imported from
`mcp_server.hints` instead of duplicated here.

Previously in 0.1.8 — the base
`IAIOPS_READ_ONLY` gate was **removed** in iaiops 0.19.0 (read/write authorisation is the
caller's decision — agent judgement / account management — not the tap's; every tool is
governed and audited via the base `@governed_tool` harness), so this edition drops it too.
It keeps the **`IAIOPS_NO_EGRESS=1`** gate — a data-exfiltration / airgap axis that withholds
data-shipping tools from `list_tools()` at registration time. This edition runs its own
`FastMCP` instance, so the gate is wired into its own `main()`; without it `IAIOPS_NO_EGRESS=1`
would still expose `historian_push`, `rca_narrate` and the `stream_publish*` pair mirrored in
from the base brain. The energy connectors themselves are monitor-only and survive the gate
intact. See `CHANGELOG.md`.

Previously in 0.1.6 — an
**audit-hardening pass** over the three read-only connectors: DNP3 no longer reports an
offline outstation as online or returns a partial integrity-poll database; IEC-61850 gained
a bounded connect/request timeout and stopped fabricating `0.0`/empty-success on failure; the
substation analyzer no longer calls a lone breaker-open a "selective trip"; tests isolate
`IAIOPS_HOME`; and the base pin was raised to `iaiops>=0.14` so the governance endpoint-scoping
fix applies. See `CHANGELOG.md` §0.1.6. (0.1.5 verified the IEC-104 monitor path — a real `c104`
client↔server round-trip in a Linux container, `tests/test_iec104_live.py`.)
**Physical RTU/IED still `待核实`.** Since 0.1.3 the server has
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
物理设备一律 `待核实`**。三者的证据新鲜度并不相同:IEC-104 与 IEC-61850 的 loopback 测试
**每次 CI 都真实执行**;DNP3 的 loopback 只在 2026-07-02 手工跑过一次 —— `pydnp3` 无 wheel、
需从源码编译 opendnp3,托管 runner 上构建失败,所以 `test_dnp3_live.py` 在每次 CI 中都被跳过 —— 如果你能在授权的测试环境里对真实变电设备跑一遍
`iaiops doctor`,我们非常想听结果。经你验证的设备会署名写进支持矩阵。

**Live substation RTU / IED / IEC-104 field testing is what this package needs most.**
The IEC-104, DNP3 and IEC-61850 monitor paths are library-loopback-verified, but real gear stays
`待核实`. The three do not carry equally fresh evidence: the IEC-104 and IEC-61850 loopback tests
**run on every CI build**, while the DNP3 one was executed manually once, on 2026-07-02 — `pydnp3`
ships no wheel and needs an opendnp3 source build that fails on hosted runners, so
`test_dnp3_live.py` is skipped by every CI run. Report results (protocol + device model + `iaiops doctor` output) via the base
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
The descriptor is validated against Margo's published `margo.org/v1-alpha1` LinkML schema on every
PR (CI job `margo-descriptor`) and passes clean — structural validity only, see
[`deploy/margo/schema/PROVENANCE.md`](deploy/margo/schema/PROVENANCE.md).

> **Honest status:** a natural Margo edge application, but **NOT Margo-compliant yet** — image build,
> hosted+signed package, and a published conformance result are roadmap `⏳`. No claim of compliance
> until that result exists, and the schema pass above is **not** a step toward it: the compliance
> test suite cannot be run today because it does not exist yet (no conformance repo in the `margo`
> org; a first PR1 vertical slice was still being scoped as of 2026-01-15).

## Validation status (honest)

The same honesty ladder as the base repo. Driver **codec / API surface** is verified
against the real libraries; the mock/monkeypatched **unit tests run in CI** without
hardware. See the base repo's `docs/PREVIEW-VERIFICATION.md` runbook for how a
protocol is promoted.

| Protocol | Status | CI coverage | Evidence |
| --- | --- | --- | --- |
| **DNP3 / IEEE 1815** | **verified (monitor path)** | ⏭ skips on hosted CI ¹ | Real master↔outstation round-trip against a live **opendnp3** outstation (`pydnp3`): `is_online()` reflects the real channel `OnStateChange`, and `integrity_poll()` (Class 0/1/2/3) returns the seeded binary/analog/counter database grouped by type. See `tests/test_dnp3_live.py` (`@pytest.mark.integration`, skips when `pydnp3` is absent). No physical RTU. |
| **IEC 60870-5-104** | **verified (monitor path)** | ✅ runs every push | Real client↔server round-trip against an in-process **`c104`** server (`tests/test_iec104_live.py` + `tests/iec104_server_harness.py`, `@pytest.mark.integration`, passes in a Linux container): `iec104_connection_info` discovers the seeded station, `iec104_interrogate` (general interrogation / C_IC) returns the seeded `M_ME_NC_1` + `M_SP_NA_1` points with quality, `iec104_read_point` reads the measurand, a bad IOA yields `found=False` with **no fabricated value**, and server-side ASDU capture proves **no control ASDU** (C_SC / C_DC / C_SE) is ever issued. `c104` ships no macOS wheel so the test skips on macOS (runs in CI / Linux). No physical RTU. Monitor/read only. |
| **IEC 61850 (MMS)** | **verified (monitor path)** | ⏭ skips on hosted CI ¹ | Real client↔server MMS round-trip against an in-process **libiec61850** MMS server built with `pyiec61850`'s server API: `iec61850_device_directory` lists the logical device (and browses its logical nodes / data objects), and `iec61850_read` returns a seeded measurand (`TotW.mag.f`, FC `MX`) over real ISO-on-TCP; a bad reference surfaces an MMS data-access error instead of a fabricated value. See `tests/test_iec61850_live.py` (`@pytest.mark.integration`, skips when `pyiec61850` / its server API is absent). No physical IED. Read/monitor only — control / GOOSE / SV out of scope. |

**¹ CI-coverage caveat (honest).** Only **IEC-104**'s monitor path is CI-gated: the
CI job hard-installs the `iec104` extra, so `test_iec104_live.py` runs its full
loopback round-trip on **every push**. **DNP3** and **IEC-61850** are loopback-verified
only via **manual / Docker runs** — their native libraries (`opendnp3` via `pydnp3`,
`libiec61850` via `pyiec61850`) do **not** build on hosted GitHub runners, so CI installs
them best-effort and `test_dnp3_live.py` / `test_iec61850_live.py` **SKIP** there. A
regression in the DNP3 or IEC-61850 monitor path is therefore **not caught by CI** and
must be re-checked with a manual/Docker run — the "verified (monitor path)" claim for
those two rests on those out-of-CI runs, not on the green CI badge.

DNP3 notes: read-only / monitor direction only (no control). `pydnp3` 0.1.0 ships no
wheel and needs a native opendnp3 build, so the live test runs in a Linux container;
its `DNP3Manager.Shutdown()` can block in a long-lived interpreter, so the connector
bounds teardown (`_Pydnp3MasterAdapter.shutdown`) and the test drives the round-trip
in a short-lived child process.

## License

MIT — © wei. Part of the vendor-neutral, governed Industrial-AIOps line.
