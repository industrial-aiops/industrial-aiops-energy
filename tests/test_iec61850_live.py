"""IEC 61850 LIVE integration test — the real connector client vs a real MMS server.

Category-B verification: stands up an in-process **libiec61850 MMS server** (built
with pyiec61850's server API — see ``tests/iec61850_server_harness.py``) seeded with
a known measurand, then drives the energy connector's public ops
(``iec61850_device_directory`` → browse → ``iec61850_read``) against it over real
MMS (ISO-on-TCP) and asserts the model and the seeded value round-trip.

Read-only / monitor direction only — no control (Oper / SBO) is issued.

Why a child process: the libiec61850 server + client both hold native threads and
C model memory in one interpreter; running the round-trip in a short-lived child
that ``os._exit``s after asserting exercises the genuine connector code while
side-stepping any interpreter-teardown ordering issues. The whole module SKIPS
cleanly when ``pyiec61850`` (or its server API) is unavailable, so the default host
suite is unaffected. ``pyiec61850`` ships a manylinux wheel only, so this runs where
that binding is installed (a Linux container in CI).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pyiec61850")  # skip the module when the binding is unavailable

from tests.iec61850_server_harness import server_api_available  # noqa: E402

pytestmark = pytest.mark.skipif(
    not server_api_available(),
    reason="pyiec61850 server API (IedServer_create/...) unavailable",
)

# Child script: start a real MMS server, then verify the connector's read path
# against it. Exits 0 and prints LIVE_OK only when the model + seeded value
# round-trip. Kept as a string so the parent runs it in a fresh interpreter.
_CHILD_SCRIPT = r'''
import os, sys

from tests.iec61850_server_harness import (
    LOGICAL_DEVICE, LN_NAME, SEED_TOTW, TOTW_REFERENCE,
    free_port, start_server, stop_server,
)
from iaiops_energy.connectors.iec61850 import ops
from iaiops_energy.runtime.targets import EnergyTarget


def main():
    port = free_port()
    server, model = start_server(port)
    try:
        target = EnergyTarget(name="live-ied", protocol="iec61850",
                              host="127.0.0.1", port=port)

        # 1) device directory over real MMS lists the logical device.
        directory = ops.iec61850_device_directory(target)
        lds = [d["logical_device"] for d in directory["logical_devices"]]
        assert LOGICAL_DEVICE in lds, directory

        # 2) directory with children maps the LD's logical nodes.
        with_children = ops.iec61850_device_directory(target, include_children=True)
        row = next(d for d in with_children["logical_devices"]
                   if d["logical_device"] == LOGICAL_DEVICE)
        assert LN_NAME in row["children"], with_children
        assert "LLN0" in row["children"], with_children

        # 3) browse the logical node -> its data objects.
        browse = ops.iec61850_browse(target, f"{LOGICAL_DEVICE}/{LN_NAME}")
        assert "TotW" in browse["children"], browse

        # 4) read the seeded measurand over real MMS.
        read = ops.iec61850_read(target, TOTW_REFERENCE, "MX")
        assert read["error"] == "", read
        assert read["value"] == SEED_TOTW, read
        assert read["fc"] == "MX", read

        # 5) a bad reference reports an error (not a fabricated value).
        missing = ops.iec61850_read(target, f"{LOGICAL_DEVICE}/{LN_NAME}.Nope.mag.f", "MX")
        assert missing["error"], missing
    finally:
        stop_server(server, model)

    print("LIVE_OK", flush=True)
    sys.stdout.flush()
    os._exit(0)


main()
'''


@pytest.mark.integration
def test_iec61850_live_round_trip(tmp_path: Path) -> None:
    """The real connector client browses + reads a real libiec61850 MMS server."""
    script = tmp_path / "iec61850_live_child.py"
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
        f"live IEC-61850 round-trip failed (rc={result.returncode})\n"
        f"STDOUT:\n{result.stdout[-2000:]}\nSTDERR:\n{result.stderr[-2000:]}"
    )
    assert result.returncode == 0, result.stderr[-2000:]
