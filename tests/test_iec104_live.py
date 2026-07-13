"""IEC 60870-5-104 LIVE integration test — the real connector client vs a real c104 server.

Category-B verification: stands up an in-process ``c104`` IEC-104 server (see
``tests/iec104_server_harness.py``) seeded with a measured value (M_ME_NC_1) and a
single point (M_SP_NA_1) on a known ASDU common address, then drives the energy
connector's public ops (``iec104_connection_info`` → ``iec104_interrogate`` →
``iec104_read_point``) against it over real IEC-104 (TCP/2404 profile) and asserts
the seeded points round-trip with correct values/quality.

Read-only / monitor direction only — the connector issues a general interrogation
(C_IC / Class 0, the read mechanism) and reads; the server declares no control
points and records every ASDU TypeID it receives, so the test asserts NO control
command (C_SC / C_DC / C_SE …) was ever issued.

Why a child process: like the DNP3 / IEC-61850 live tests, the c104 client and
server both hold native background threads in one interpreter; running the
round-trip in a short-lived child that ``os._exit``s after asserting exercises the
genuine connector code while side-stepping any interpreter-teardown ordering. The
whole module SKIPS cleanly when ``c104`` (or its server API) is unavailable, so the
default host suite is unaffected — ``c104`` ships no wheel for every platform and
builds a native ext, so this runs where that binding is installed (a Linux
container in CI).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("c104")  # skip the module when the binding is unavailable

from tests.iec104_server_harness import server_available  # noqa: E402

pytestmark = pytest.mark.skipif(
    not server_available(),
    reason="c104 server API (Server/Client/Type.M_ME_NC_1/...) unavailable",
)

# Child script: seed a real c104 server, then verify the connector's read path
# against it. Exits 0 and prints LIVE_OK only when every seeded point round-trips
# AND no control ASDU was received. Kept as a string so the parent runs it fresh.
_CHILD_SCRIPT = r"""
import os, sys

from tests.iec104_server_harness import (
    COMMON_ADDRESS, CONTROL_TYPE_IDS, SEED_MEASURED_IOA, SEED_MEASURED_VALUE,
    SEED_SINGLE_IOA, free_port, start_server, stop_server,
)
from iaiops_energy.connectors.iec104 import ops
from iaiops_energy.runtime.targets import EnergyTarget


def main():
    port = free_port()
    server, received_type_ids = start_server(port)
    try:
        target = EnergyTarget(name="live-rtu", protocol="iec104", host="127.0.0.1",
                              port=port, common_address=COMMON_ADDRESS)

        # 1) link status: connected + the seeded station's CA discovered.
        info = ops.iec104_connection_info(target)
        assert info["connected"] is True, info
        assert info["configured_common_address"] == COMMON_ADDRESS, info
        assert COMMON_ADDRESS in info["common_addresses"], info

        # 2) general interrogation returns the two seeded monitored points.
        poll = ops.iec104_interrogate(target)
        assert poll.get("common_address") == COMMON_ADDRESS, poll
        assert poll.get("point_count", 0) >= 2, poll
        by_ioa = {p["io_address"]: p for p in poll["points"]}
        measured = by_ioa[SEED_MEASURED_IOA]
        assert abs(float(measured["value"]) - SEED_MEASURED_VALUE) < 1e-3, poll
        assert measured["type"] == "M_ME_NC_1", poll
        assert measured["quality"], poll  # quality surfaced, not blank
        single = by_ioa[SEED_SINGLE_IOA]
        assert single["value"] in (True, 1, 1.0), poll
        assert single["type"] == "M_SP_NA_1", poll

        # 3) single-point read of the seeded measurand.
        read = ops.iec104_read_point(target, SEED_MEASURED_IOA)
        assert read["found"] is True, read
        assert abs(float(read["value"]) - SEED_MEASURED_VALUE) < 1e-3, read

        # 4) a bad/absent IOA surfaces found=False with NO fabricated value.
        missing = ops.iec104_read_point(target, 999999)
        assert missing["found"] is False, missing
        assert "value" not in missing, missing

        # 5) monitor-only: no control-direction ASDU was ever received.
        control_seen = sorted(set(received_type_ids) & CONTROL_TYPE_IDS)
        assert not control_seen, f"control ASDU(s) issued: {control_seen}"
    finally:
        stop_server(server)

    print("LIVE_OK", flush=True)
    sys.stdout.flush()
    os._exit(0)


main()
"""


@pytest.mark.integration
def test_iec104_live_round_trip(tmp_path: Path) -> None:
    """The real connector client interrogates + reads a real in-process c104 server."""
    script = tmp_path / "iec104_live_child.py"
    script.write_text(_CHILD_SCRIPT)
    repo_root = Path(__file__).resolve().parent.parent
    result = subprocess.run(  # noqa: S603 — fixed interpreter + our own script
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(repo_root),  # so `import tests.*` and the connector resolve
    )
    assert "LIVE_OK" in result.stdout, (
        f"live IEC-104 round-trip failed (rc={result.returncode})\n"
        f"STDOUT:\n{result.stdout[-2000:]}\nSTDERR:\n{result.stderr[-2000:]}"
    )
    assert result.returncode == 0, result.stderr[-2000:]
