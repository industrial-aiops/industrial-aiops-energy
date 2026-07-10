# `deploy/margo/` — iaiops-energy as a Margo edge application (skeleton)

> **Status: roadmap `⏳` — NOT Margo-compliant yet.** Mirrors the base repo's edge-app packaging
> ([industrial-aiops `docs/MARGO-ALIGNMENT.md`](https://github.com/industrial-aiops/industrial-aiops/blob/main/docs/MARGO-ALIGNMENT.md)).
> The energy edition reuses `iaiops.core` and simply runs its **own** MCP server
> (`iaiops-energy-mcp`) in a hardened container. Conformance run is pending; no material claims
> compliance until it passes.

| File | Purpose |
|------|---------|
| `Dockerfile` | Non-root, read-only-rootfs-friendly image; installs `iaiops-energy[energy]`; entrypoint `iaiops-energy-mcp`. Build-arg `EXTRAS` (energy / iec104,dnp3 / …). |
| `compose.yaml` | Hardened run: `read_only` + tmpfs `/tmp`, `cap_drop: ALL`, no-new-privileges, **no inbound ports**, single state volume. |
| `margo.yaml` | Margo **ApplicationDescription** (`margo.org/v1-alpha1`) for the energy edition — remaining `待核实` = hosted+signed package + secret-parameter flag + IEC-61850 native-lib needs. |

```bash
docker build -t iaiops-energy:latest -f deploy/margo/Dockerfile .
# IGEL OS 12 / any Margo host: deploy as an OCI Managed Container (outbound-only to substation gear).
```

Same neutrality + honesty discipline as the base repo: read-first, air-gap friendly, governed
(audit / budget / risk-tier / undo) via `iaiops.core`; not compliant until conformance passes.
