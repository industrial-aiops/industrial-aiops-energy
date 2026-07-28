# iaiops-energy (substation/utility edition) as a Margo-style edge application. Mirrors the base
# repo's deploy/margo pattern (github.com/industrial-aiops/industrial-aiops, docs/MARGO-ALIGNMENT.md).
# Reuses iaiops.core (governance/brain/runtime) pulled in transitively. NOT Margo-compliant yet —
# roadmap `⏳`; conformance run pending. Headless, non-root, read-only-rootfs friendly.
#
# Build: docker build -t iaiops-energy:latest -f deploy/margo/Dockerfile .
ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS build
# Energy protocols to bake in. `energy` = iec104 + dnp3 + iec61850. The IEC-61850 binding
# (`pyiec61850`, libiec61850 SWIG) is a linux-only wheel — 待核实 whether a given base image needs
# extra system libs; drop to `iec104,dnp3` if it fails on your target.
ARG EXTRAS=energy
ARG IAIOPS_ENERGY_VERSION=0.1.8
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install "iaiops-energy[${EXTRAS}]==${IAIOPS_ENERGY_VERSION}"

FROM python:${PYTHON_VERSION}-slim AS runtime
RUN useradd --create-home --uid 10001 iaiops
COPY --from=build /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    IAIOPS_HOME=/home/iaiops/.iaiops \
    PYTHONUNBUFFERED=1
USER iaiops
WORKDIR /home/iaiops
VOLUME ["/home/iaiops/.iaiops"]
# Read-first tap — outbound-only to the substation RTUs/IEDs you configure; no inbound ports.
HEALTHCHECK --interval=1m --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import iaiops_energy"]
# Energy edition runs its OWN MCP server (brain + IEC-104 / DNP3 / IEC-61850 tools) over stdio.
# 待核实: MCP transport under a Margo orchestrator (stdio vs socket/HTTP) — same open question as base.
ENTRYPOINT ["iaiops-energy-mcp"]
