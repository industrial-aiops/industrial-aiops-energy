"""DNP3 ops tests against a MOCKED master adapter.

opendnp3 is callback-based and unverified here, so ``_build_dnp3_client`` is
monkeypatched to return a fake adapter exposing the uniform interface
(enable/is_online/integrity_poll/shutdown) the ops rely on — exercising link
status and the integrity-poll grouping without a live outstation. Also covers the
driver's group→type mapping.
"""

from __future__ import annotations

import types

import pytest

import iaiops_energy.runtime.sessions as conn
from iaiops_energy.connectors.dnp3 import ops
from iaiops_energy.connectors.dnp3.driver import _Pydnp3MasterAdapter, measurement_type
from iaiops_energy.runtime.targets import EnergyTarget as TargetConfig


class _FakeAdapter:
    def __init__(self, points, online=True):
        self._points = points
        self._online = online
        self.enabled = False
        self.shut = False

    def enable(self):
        self.enabled = True

    def is_online(self):
        return self._online

    def integrity_poll(self):
        return list(self._points)

    def shutdown(self):
        self.shut = True


@pytest.fixture
def outstation(monkeypatch):
    points = [
        {
            "group": 1,
            "type": "binary_input",
            "index": 0,
            "value": True,
            "quality": "ONLINE",
            "timestamp": "",
        },
        {
            "group": 30,
            "type": "analog_input",
            "index": 0,
            "value": 120.5,
            "quality": "ONLINE",
            "timestamp": "",
        },
        {
            "group": 30,
            "type": "analog_input",
            "index": 1,
            "value": 60.0,
            "quality": "ONLINE",
            "timestamp": "",
        },
        {
            "group": 20,
            "type": "counter",
            "index": 0,
            "value": 9000,
            "quality": "ONLINE",
            "timestamp": "",
        },
    ]
    adapter = _FakeAdapter(points)
    monkeypatch.setattr(conn, "_build_dnp3_client", lambda target: adapter)
    target = TargetConfig(
        name="rtu2", protocol="dnp3", host="10.0.0.6", unit_id=4, master_address=1
    )
    return target, adapter


@pytest.mark.unit
def test_link_status(outstation):
    target, _ = outstation
    out = ops.dnp3_link_status(target)
    assert out["online"] is True
    assert out["outstation_address"] == 4
    assert out["master_address"] == 1


@pytest.mark.unit
def test_integrity_poll_groups_by_type(outstation):
    target, _ = outstation
    out = ops.dnp3_integrity_poll(target)
    assert out["point_count"] == 4
    assert out["by_type"]["analog_input"] == 2
    assert out["by_type"]["binary_input"] == 1
    assert out["by_type"]["counter"] == 1
    analog = [p for p in out["points"] if p["type"] == "analog_input"]
    assert analog[0]["value"] == 120.5


@pytest.mark.unit
def test_offline_outstation_raises(monkeypatch):
    adapter = _FakeAdapter([], online=False)
    monkeypatch.setattr(conn, "_build_dnp3_client", lambda target: adapter)
    monkeypatch.setattr(conn, "_wait_until", lambda pred, t, poll_s=0.05: bool(pred()))
    target = TargetConfig(name="rtu2", protocol="dnp3", host="10.0.0.6")
    with pytest.raises(conn.OTConnectionError, match="did not come online"):
        ops.dnp3_link_status(target)


@pytest.mark.unit
def test_shutdown_called(outstation):
    target, adapter = outstation
    ops.dnp3_integrity_poll(target)
    assert adapter.shut is True


@pytest.mark.unit
def test_measurement_type_mapping():
    assert measurement_type(1) == "binary_input"
    assert measurement_type(30) == "analog_input"
    assert measurement_type(20) == "counter"
    assert measurement_type(999).startswith("group_")


@pytest.mark.unit
def test_wrong_protocol_guarded():
    target = TargetConfig(name="x", protocol="modbus", host="1.2.3.4")
    with pytest.raises(conn.OTConnectionError, match="not dnp3"):
        with conn.dnp3_session(target):
            pass


def _adapter_with_fake_opendnp3():
    """Build the REAL adapter with fake opendnp3 modules (no pydnp3 needed)."""
    opendnp3 = types.SimpleNamespace(
        ChannelState=types.SimpleNamespace(OPEN="OPEN", CLOSED="CLOSED"),
    )
    return _Pydnp3MasterAdapter(
        asiodnp3=types.SimpleNamespace(),
        opendnp3=opendnp3,
        asiopal=types.SimpleNamespace(),
        openpal=types.SimpleNamespace(),
        host="10.0.0.6",
        port=20000,
        outstation=4,
        master=1,
    ), opendnp3


@pytest.mark.unit
def test_is_online_reflects_channel_state_change():
    """is_online() tracks live opendnp3 channel state, not just enable()."""
    adapter, o3 = _adapter_with_fake_opendnp3()
    # No callback yet, not enabled → offline (the enable() latch is False).
    assert adapter.is_online() is False
    # opendnp3 reports the channel OPEN → is_online flips True.
    adapter._record_channel_state(o3.ChannelState.OPEN)
    assert adapter.is_online() is True
    # Channel drops (CLOSED) → is_online reflects it immediately.
    adapter._record_channel_state(o3.ChannelState.CLOSED)
    assert adapter.is_online() is False


@pytest.mark.unit
def test_integrity_poll_waits_for_all_fragmented_groups():
    """opendnp3 delivers each object group in a SEPARATE reactor callback; the poll
    must wait for delivery to settle, not return on the first point (partial DB)."""
    import threading
    import time

    adapter, o3 = _adapter_with_fake_opendnp3()
    o3.ClassField = types.SimpleNamespace(AllClasses=lambda: "all")

    def _deliver() -> None:
        for grp, mtype in ((1, "binary_input"), (30, "analog_input"), (20, "counter")):
            time.sleep(0.05)
            adapter._handler.points.append(
                {
                    "group": grp,
                    "type": mtype,
                    "index": 0,
                    "value": 1,
                    "quality": "",
                    "timestamp": "",
                }
            )

    class _FakeMaster:
        def ScanClasses(self, field):  # noqa: N802 — opendnp3 name
            threading.Thread(target=_deliver, daemon=True).start()

    adapter._dnpmaster = _FakeMaster()
    points = adapter.integrity_poll(settle_s=3.0)
    # All three groups present — NOT just the first fragment.
    assert {p["type"] for p in points} == {"binary_input", "analog_input", "counter"}
    assert len(points) == 3


@pytest.mark.unit
def test_harvest_unknown_collection_class_is_flagged_not_mislabeled():
    """An unrecognized pybind11 collection class must NOT collapse to group_0."""
    from iaiops_energy.connectors.dnp3.driver import _harvest_collection

    class ICollectionFooBar:
        def ForeachItem(self, cb):  # noqa: N802 — opendnp3 name
            cb(
                types.SimpleNamespace(
                    index=0, value=types.SimpleNamespace(value=1, flags="", time="")
                )
            )

    out: list[dict] = []
    _harvest_collection(ICollectionFooBar(), out)
    assert out[0]["group"] is None
    assert out[0]["type"].startswith("unknown_collection:")


@pytest.mark.unit
def test_harvest_known_collection_maps_group_and_value():
    from iaiops_energy.connectors.dnp3.driver import _harvest_collection

    class ICollectionIndexedAnalog:
        def ForeachItem(self, cb):  # noqa: N802 — opendnp3 name
            cb(
                types.SimpleNamespace(
                    index=2, value=types.SimpleNamespace(value=120.5, flags="ONLINE", time="")
                )
            )

    out: list[dict] = []
    _harvest_collection(ICollectionIndexedAnalog(), out)
    assert out[0]["group"] == 30
    assert out[0]["type"] == "analog_input"
    assert out[0]["index"] == 2
    assert out[0]["value"] == 120.5


@pytest.mark.unit
def test_log_handler_never_writes_to_stdout(capsys):
    """The opendnp3 log handler must route to logging (stderr), never stdout —
    stdout under an stdio MCP transport corrupts the JSON-RPC stream."""
    adapter, _ = _adapter_with_fake_opendnp3()
    adapter._openpal = types.SimpleNamespace(ILogHandler=object)
    handler = adapter._make_log_handler()
    handler.Log(types.SimpleNamespace(message="opendnp3 stack log line"))
    captured = capsys.readouterr()
    assert captured.out == ""


@pytest.mark.unit
def test_channel_listener_forwards_state_to_is_online():
    """The IChannelListener built for opendnp3 feeds OnStateChange into is_online()."""
    adapter, o3 = _adapter_with_fake_opendnp3()
    listener = adapter._make_channel_listener()
    listener.OnStateChange(o3.ChannelState.OPEN)
    assert adapter.is_online() is True


@pytest.mark.unit
def test_is_online_offline_until_channel_open_even_when_enabled():
    """The enable() latch must NOT report online before OnStateChange fires.

    enable() returns synchronously while the TCP channel is still opening on the
    reactor thread; trusting it would let the readiness wait pass and report an
    offline outstation as online (iron rule). Online requires ChannelState.OPEN.
    """
    adapter, _ = _adapter_with_fake_opendnp3()
    assert adapter.is_online() is False
    adapter._enabled = True  # simulate enable() having run, no callback yet
    assert adapter.is_online() is False  # still offline — no OPEN callback yet


@pytest.mark.unit
def test_listener_never_reaching_open_is_reported_offline_after_wait():
    """An outstation whose listener never reaches OPEN is offline after the wait.

    Mirrors dnp3_session's readiness wait: with a listener that only ever delivers
    CLOSED (or nothing), _wait_until genuinely times out and reports offline rather
    than passing on the enable() latch.
    """
    from iaiops_energy.runtime.sessions import _wait_until

    adapter, o3 = _adapter_with_fake_opendnp3()
    adapter._enabled = True
    adapter._record_channel_state(o3.ChannelState.CLOSED)  # never OPEN
    assert _wait_until(adapter.is_online, 0.2) is False
