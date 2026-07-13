"""IEC 61850 MMS ops tests against a MOCKED libiec61850 adapter.

The libiec61850 binding is unverified here, so ``_build_iec61850_client`` is
monkeypatched to return a fake adapter exposing the uniform interface
(connect/close/get_logical_devices/get_data_directory/read) — exercising the
device directory, browse, and attribute read without a live IED.
"""

from __future__ import annotations

import types

import pytest

import iaiops_energy.runtime.sessions as conn
from iaiops_energy.connectors.iec61850 import ops
from iaiops_energy.connectors.iec61850.driver import BrowseError, _LibIec61850Adapter
from iaiops_energy.runtime.targets import EnergyTarget as TargetConfig

SN = types.SimpleNamespace


def _adapter(lib: object) -> _LibIec61850Adapter:
    """A real driver adapter over a fake ``lib`` namespace (no pyiec61850 needed)."""
    adapter = _LibIec61850Adapter(lib, "10.0.0.7", 102)
    adapter._conn = "CONN"
    return adapter


class _FakeAdapter:
    def __init__(self):
        self.connected = False
        self.closed = False
        self._model = {
            "": ["IED1LD0", "IED1MEAS"],
            "IED1LD0": ["LLN0", "MMXU1"],
            "IED1MEAS": ["MMXU1"],
        }
        self._values = {("IED1MMXU1.TotW.mag.f", "MX"): 1234.5}

    def connect(self, timeout_s=None):
        self.connected = True
        self.connect_timeout_s = timeout_s

    def close(self):
        self.closed = True

    def get_logical_devices(self):
        return self._model[""]

    def get_data_directory(self, reference):
        return self._model.get(reference, [])

    def read(self, reference, fc):
        if (reference, fc) in self._values:
            return {"reference": reference, "fc": fc, "value": self._values[(reference, fc)]}
        return {"reference": reference, "fc": fc, "error": "no such object"}


@pytest.fixture
def ied(monkeypatch):
    adapter = _FakeAdapter()
    monkeypatch.setattr(conn, "_build_iec61850_client", lambda target: adapter)
    return TargetConfig(name="ied1", protocol="iec61850", host="10.0.0.7"), adapter


@pytest.mark.unit
def test_device_directory(ied):
    target, _ = ied
    out = ops.iec61850_device_directory(target)
    assert out["logical_device_count"] == 2
    assert out["logical_devices"][0]["logical_device"] == "IED1LD0"


@pytest.mark.unit
def test_device_directory_with_children(ied):
    target, _ = ied
    out = ops.iec61850_device_directory(target, include_children=True)
    ld0 = next(d for d in out["logical_devices"] if d["logical_device"] == "IED1LD0")
    assert ld0["child_count"] == 2
    assert "MMXU1" in ld0["children"]


@pytest.mark.unit
def test_browse(ied):
    target, _ = ied
    out = ops.iec61850_browse(target, "IED1LD0")
    assert out["child_count"] == 2
    assert "LLN0" in out["children"]


@pytest.mark.unit
def test_browse_requires_reference(ied):
    target, _ = ied
    assert "error" in ops.iec61850_browse(target, "")


@pytest.mark.unit
def test_read_value(ied):
    target, _ = ied
    out = ops.iec61850_read(target, "IED1MMXU1.TotW.mag.f", "MX")
    assert out["value"] == 1234.5
    assert out["fc"] == "MX"
    assert out["error"] == ""


@pytest.mark.unit
def test_read_missing_object_reports_error(ied):
    target, _ = ied
    out = ops.iec61850_read(target, "IED1.Nope", "MX")
    assert out["error"]


@pytest.mark.unit
def test_close_called(ied):
    target, adapter = ied
    ops.iec61850_device_directory(target)
    assert adapter.closed is True


@pytest.mark.unit
def test_wrong_protocol_guarded():
    target = TargetConfig(name="x", protocol="modbus", host="1.2.3.4")
    with pytest.raises(conn.OTConnectionError, match="not iec61850"):
        with conn.iec61850_session(target):
            pass


@pytest.mark.unit
def test_browse_failure_surfaces_error_not_empty(monkeypatch):
    """A FAILED browse must raise (→ OTConnectionError), not fabricate child_count 0."""

    class _Failing(_FakeAdapter):
        def get_logical_devices(self):
            raise BrowseError("browse blew up")

    monkeypatch.setattr(conn, "_build_iec61850_client", lambda target: _Failing())
    target = TargetConfig(name="ied1", protocol="iec61850", host="10.0.0.7")
    with pytest.raises(conn.OTConnectionError):
        ops.iec61850_device_directory(target)


# ─── driver decode-helper unit tests (fake `lib` namespace, no pyiec61850) ──────


@pytest.mark.unit
def test_unwrap_shapes():
    unwrap = _LibIec61850Adapter._unwrap
    payload = object()
    assert unwrap([["a", "b"], 0]) == (["a", "b"], 0)
    assert unwrap((payload, 7)) == (payload, 7)
    assert unwrap([payload]) == (payload, 0)
    assert unwrap([]) == (None, 0)
    assert unwrap(5) == (None, 5)
    assert unwrap("bare") == ("bare", 0)


@pytest.mark.unit
def test_get_logical_devices_empty_vs_failure():
    # Success + payload → names.
    ok = _adapter(SN(IedConnection_getLogicalDeviceList=lambda c: [["LD0", "LD1"], 0]))
    assert ok.get_logical_devices() == ["LD0", "LD1"]
    # Success + no payload → legitimately empty [].
    empty = _adapter(SN(IedConnection_getLogicalDeviceList=lambda c: [None, 0]))
    assert empty.get_logical_devices() == []
    # Error code → raise (never a silent []).
    failing = _adapter(SN(IedConnection_getLogicalDeviceList=lambda c: 5))
    with pytest.raises(BrowseError):
        failing.get_logical_devices()
    # Binding lacks the call → raise.
    with pytest.raises(BrowseError):
        _adapter(SN()).get_logical_devices()


@pytest.mark.unit
def test_get_data_directory_empty_vs_failure():
    # A level succeeds with names → those names.
    ok = _adapter(SN(IedConnection_getLogicalDeviceDirectory=lambda c, ref: [["LLN0", "MMXU1"], 0]))
    assert ok.get_data_directory("IED1LD0") == ["LLN0", "MMXU1"]
    # A level succeeds but empty → legitimately empty [].
    empty = _adapter(SN(IedConnection_getLogicalDeviceDirectory=lambda c, ref: [None, 0]))
    assert empty.get_data_directory("IED1LD0") == []
    # Every applicable level fails → raise.
    failing = _adapter(
        SN(
            IedConnection_getLogicalDeviceDirectory=lambda c, ref: 3,
            IedConnection_getLogicalNodeDirectory=lambda c, ref, acsi: 3,
            IedConnection_getDataDirectory=lambda c, ref: 3,
        )
    )
    with pytest.raises(BrowseError):
        failing.get_data_directory("IED1LD0")


@pytest.mark.unit
def test_decode_mms_never_fabricates_zero_for_unmapped_type():
    """An unmapped MMS type must NOT read as 0.0 via a blind toFloat."""
    unmapped = object()
    lib = SN(
        MmsValue_getType=lambda v: unmapped,
        MmsValue_toFloat=lambda v: 0.0,  # would fabricate 0.0 if used
        MmsValue_toString=lambda v: "0101",  # opaque encoding instead
    )
    result = _adapter(lib)._decode_mms(object())
    assert result != 0.0
    assert result == "0101"


@pytest.mark.unit
def test_decode_mms_uses_numeric_accessor_only_for_numeric_type():
    float_t = object()
    lib = SN(
        MmsValue_getType=lambda v: float_t,
        MMS_FLOAT=float_t,
        MmsValue_toFloat=lambda v: 42.5,
    )
    assert _adapter(lib)._decode_mms(object()) == 42.5


@pytest.mark.unit
def test_decode_mms_opaque_marker_when_no_string_accessor():
    unmapped = object()
    lib = SN(MmsValue_getType=lambda v: unmapped)  # no toString, no accessor
    result = _adapter(lib)._decode_mms(object())
    assert isinstance(result, str)
    assert result.startswith("<unmapped MmsValue")
    assert result != "0.0"


@pytest.mark.unit
def test_access_error_detected_and_absent():
    ae = object()
    detected = _adapter(
        SN(
            MmsValue_getType=lambda v: ae,
            MMS_DATA_ACCESS_ERROR=ae,
            MmsValue_getDataAccessError=lambda v: "OBJECT_UNDEFINED",
        )
    )
    assert detected._access_error(object()) == "OBJECT_UNDEFINED"
    absent = _adapter(SN(MmsValue_getType=lambda v: object(), MMS_DATA_ACCESS_ERROR=object()))
    assert absent._access_error(object()) is None


@pytest.mark.unit
def test_connect_applies_bounded_timeouts():
    calls: dict[str, tuple] = {}
    lib = SN(
        IedConnection_create=lambda: "CONN",
        IedConnection_setConnectTimeout=lambda c, ms: calls.__setitem__("connect", (c, ms)),
        IedConnection_setRequestTimeout=lambda c, ms: calls.__setitem__("request", (c, ms)),
        IedConnection_connect=lambda c, host, port: 0,
    )
    _LibIec61850Adapter(lib, "10.0.0.7", 102).connect(2.0)
    assert calls["connect"] == ("CONN", 2000)
    assert calls["request"] == ("CONN", 2000)


@pytest.mark.unit
def test_connect_nonzero_code_raises():
    lib = SN(
        IedConnection_create=lambda: "CONN",
        IedConnection_connect=lambda c, host, port: 1,  # e.g. IED_ERROR_TIMEOUT
    )
    with pytest.raises(ConnectionError):
        _LibIec61850Adapter(lib, "10.0.0.7", 102).connect(1.0)
