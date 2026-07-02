"""In-process libiec61850 MMS server for the IEC-61850 live integration test.

Builds a MINIMAL dynamic model with pyiec61850's server API and starts a real MMS
server on ``127.0.0.1:<port>`` so the energy connector's client path can be driven
against genuine MMS traffic (browse + read), with no physical IED.

Model shape (kept tiny — SWIG model-building is fiddly):

    IedModel("ied1")
      └─ LogicalDevice("SENSORS")          # MMS domain → "ied1SENSORS"
           ├─ LogicalNode("LLN0")
           └─ LogicalNode("MMXU1")
                └─ CDC_MV DataObject("TotW")   # mag.f seeded to a known float

The full object reference a client reads is ``ied1SENSORS/MMXU1.TotW.mag.f`` (FC MX).

Import-safe: :func:`server_api_available` reports whether the wheel actually ships
the server API so callers can skip cleanly.
"""

from __future__ import annotations

import socket
from typing import Any

# Known-good seed value the live test asserts round-trips over real MMS.
SEED_TOTW: float = 4321.5

# Model coordinates the live test asserts against.
MODEL_NAME = "ied1"
LD_NAME = "SENSORS"
LOGICAL_DEVICE = f"{MODEL_NAME}{LD_NAME}"  # MMS domain = model name + LD name
LN_NAME = "MMXU1"
TOTW_REFERENCE = f"{LOGICAL_DEVICE}/{LN_NAME}.TotW.mag.f"


def server_api_available() -> bool:
    """True only if pyiec61850 is importable AND ships the server-side API."""
    try:
        import pyiec61850 as m  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — any import failure means "unavailable"
        return False
    required = (
        "IedServer_create", "IedServer_start", "IedModel_create",
        "LogicalDevice_create", "LogicalNode_create", "CDC_MV_create",
        "IedServer_updateFloatAttributeValue", "toModelNode", "toDataAttribute",
        "ModelNode_getChild",
    )
    return all(hasattr(m, name) for name in required)


def free_port() -> int:
    """Reserve and return an ephemeral loopback TCP port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def start_server(port: int) -> tuple[Any, Any]:
    """Build the minimal model, seed ``TotW.mag.f``, start MMS on ``port``.

    Returns ``(server, model)`` so the caller can keep both alive and later stop /
    destroy them. Raises if the server API is unavailable (guard with
    :func:`server_api_available` first).
    """
    import pyiec61850 as m  # noqa: PLC0415

    model = m.IedModel_create(MODEL_NAME)
    logical_device = m.LogicalDevice_create(LD_NAME, model)
    m.LogicalNode_create("LLN0", logical_device)
    mmxu1 = m.LogicalNode_create(LN_NAME, logical_device)
    # CDC_MV_create(name, ModelNode* parent, options, isIntegerNotFloat)
    tot_w = m.CDC_MV_create("TotW", m.toModelNode(mmxu1), 0, False)

    server = m.IedServer_create(model)
    m.IedServer_start(server, port)

    mag_f = m.toDataAttribute(m.ModelNode_getChild(m.toModelNode(tot_w), "mag.f"))
    if hasattr(m, "IedServer_lockDataModel"):
        m.IedServer_lockDataModel(server)
    m.IedServer_updateFloatAttributeValue(server, mag_f, SEED_TOTW)
    if hasattr(m, "IedServer_unlockDataModel"):
        m.IedServer_unlockDataModel(server)
    return server, model


def stop_server(server: Any, model: Any) -> None:
    """Best-effort stop + free of the server and its model."""
    import pyiec61850 as m  # noqa: PLC0415

    for fn_name, arg in (("IedServer_stop", server), ("IedServer_destroy", server),
                         ("IedModel_destroy", model)):
        fn = getattr(m, fn_name, None)
        if callable(fn) and arg is not None:
            try:
                fn(arg)
            except Exception:  # noqa: BLE001 — teardown is best-effort
                pass
