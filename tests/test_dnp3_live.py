"""DNP3 LIVE integration test — the real connector master vs a real opendnp3 outstation.

Category-B verification: stands up an in-process ``asiodnp3`` TCP-server outstation
seeded with known binary / analog / counter points, then drives the energy
connector's public ops (``dnp3_link_status`` → ``is_online`` via the OnStateChange
wiring, and ``dnp3_integrity_poll`` → a real Class 0/1/2/3 scan) against it and
asserts the seeded database comes back grouped by measurement type.

Read-only / monitor direction only — no control (CROB / analog output) is issued.

Why a child process: ``pydnp3`` 0.1.0's ``DNP3Manager.Shutdown()`` cannot tear down
cleanly inside a long-lived interpreter (it blocks, and freeing the stack's Python
callbacks first aborts). The connector's ``shutdown()`` bounds that so a *caller*
never hangs, but the reactor thread it leaves behind can crash the interpreter at a
later GC. Running the real round-trip in a short-lived child that ``os._exit``s after
asserting exercises the genuine connector code while side-stepping that upstream
teardown defect. The whole module SKIPS cleanly when ``pydnp3`` is absent, so the
default host suite is unaffected. ``pydnp3`` has no wheel and needs a native opendnp3
build, so this only runs where that binding is installed (a Linux container in CI).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pydnp3")  # skip the whole module when the binding is unavailable

# Child script: seed a real outstation, then verify the connector's read path against
# it. Exits 0 and prints LIVE_OK only when every seeded point round-trips. Kept as a
# string so the parent can run it in a fresh interpreter.
_CHILD_SCRIPT = r'''
import os, socket, sys

from pydnp3 import asiodnp3, asiopal, opendnp3, openpal

from iaiops_energy.connectors.dnp3 import ops
from iaiops_energy.runtime.targets import EnergyTarget

OUTSTATION_ADDR, MASTER_ADDR = 10, 1


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def start_outstation(port):
    cfg = asiodnp3.OutstationStackConfig(opendnp3.DatabaseSizes.AllTypes(10))
    cfg.outstation.eventBufferConfig = opendnp3.EventBufferConfig().AllTypes(10)
    cfg.outstation.params.allowUnsolicited = False
    cfg.link.LocalAddr = OUTSTATION_ADDR
    cfg.link.RemoteAddr = MASTER_ADDR
    cfg.link.KeepAliveTimeout = openpal.TimeDuration().Max()
    db = cfg.dbConfig
    db.binary[0].clazz = opendnp3.PointClass.Class1
    db.binary[0].svariation = opendnp3.StaticBinaryVariation.Group1Var2
    db.analog[0].clazz = opendnp3.PointClass.Class1
    db.analog[1].clazz = opendnp3.PointClass.Class1
    db.counter[0].clazz = opendnp3.PointClass.Class1
    db.counter[0].svariation = opendnp3.StaticCounterVariation.Group20Var1
    mgr = asiodnp3.DNP3Manager(1, asiodnp3.ConsoleLogger().Create())
    ch = mgr.AddTCPServer("os", opendnp3.levels.NORMAL,
                          asiopal.ChannelRetry().Default(), "127.0.0.1", port,
                          asiodnp3.PrintingChannelListener().Create())
    outst = ch.AddOutstation("os", opendnp3.SuccessCommandHandler().Create(),
                             opendnp3.DefaultOutstationApplication().Create(), cfg)
    outst.Enable()
    b = asiodnp3.UpdateBuilder()
    b.Update(opendnp3.Binary(True), 0)
    b.Update(opendnp3.Analog(120.0), 0)
    b.Update(opendnp3.Analog(60.0), 1)
    b.Update(opendnp3.Counter(9000), 0)
    outst.Apply(b.Build())
    return mgr  # keep alive


def main():
    port = free_port()
    _keep = start_outstation(port)  # noqa: F841 — hold the outstation for the run
    target = EnergyTarget(name="live-rtu", protocol="dnp3", host="127.0.0.1",
                          port=port, unit_id=OUTSTATION_ADDR, master_address=MASTER_ADDR)

    status = ops.dnp3_link_status(target)
    assert status["online"] is True, status
    assert status["outstation_address"] == OUTSTATION_ADDR

    poll = ops.dnp3_integrity_poll(target)
    by_type = poll["by_type"]
    assert by_type.get("analog_input", 0) >= 2, poll
    assert by_type.get("binary_input", 0) >= 1, poll
    assert by_type.get("counter", 0) >= 1, poll
    by_key = {(p["type"], p["index"]): p["value"] for p in poll["points"]}
    assert by_key[("analog_input", 0)] == 120.0, by_key
    assert by_key[("analog_input", 1)] == 60.0, by_key
    assert by_key[("binary_input", 0)] in (True, 1), by_key
    assert by_key[("counter", 0)] == 9000, by_key

    print("LIVE_OK", flush=True)
    sys.stdout.flush()
    os._exit(0)  # skip pydnp3's blocking/aborting interpreter teardown


main()
'''


@pytest.mark.integration
def test_dnp3_live_round_trip(tmp_path: Path) -> None:
    """The real connector master links to a real outstation and reads its database."""
    script = tmp_path / "dnp3_live_child.py"
    script.write_text(_CHILD_SCRIPT)
    result = subprocess.run(  # noqa: S603 — fixed interpreter + our own script
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert "LIVE_OK" in result.stdout, (
        f"live DNP3 round-trip failed (rc={result.returncode})\n"
        f"STDOUT:\n{result.stdout[-2000:]}\nSTDERR:\n{result.stderr[-2000:]}"
    )
    assert result.returncode == 0, result.stderr[-2000:]
