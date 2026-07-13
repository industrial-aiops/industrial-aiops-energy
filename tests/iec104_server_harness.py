"""In-process ``c104`` IEC 60870-5-104 server for the IEC-104 live integration test.

Stands up a real ``c104.Server`` (iec104-python) on ``127.0.0.1:<port>`` with one
station (a known ASDU common address) carrying two seeded monitored points:

    Station(common_address=47)
      ├─ M_ME_NC_1 @ IOA 1001   # measured value, short float → 50.0
      └─ M_SP_NA_1 @ IOA 1002   # single point (遥信)          → True

so the energy connector's client path (link status → general interrogation →
single-point read) can be driven against genuine IEC-104 traffic over TCP, with no
physical RTU. Monitor direction only — the server declares NO control points, and
:func:`start_server` records the ASDU type identifiers it receives so the live test
can prove no control command (C_SC / C_DC / C_SE …) was ever issued.

Import-safe: :func:`server_available` reports whether ``c104`` is importable and
ships the server API so callers can skip cleanly.
"""

from __future__ import annotations

import socket
from typing import Any

# --- Model coordinates the live test asserts against (all immutable) --------------
COMMON_ADDRESS = 47  # station ASDU common address

SEED_MEASURED_IOA = 1001  # M_ME_NC_1 (measured short float)
SEED_MEASURED_VALUE = 50.0

SEED_SINGLE_IOA = 1002  # M_SP_NA_1 (single point / 遥信)
SEED_SINGLE_VALUE = True

# IEC 60870-5-101/104 control-direction TypeIDs. If the server ever RECEIVES one of
# these, the connector broke its monitor-only contract. C_IC (100, general
# interrogation) is deliberately NOT here — it is the read mechanism, not a command.
CONTROL_TYPE_IDS: frozenset[int] = frozenset(
    {
        45,  # C_SC_NA_1  single command
        46,  # C_DC_NA_1  double command
        47,  # C_RC_NA_1  regulating step command
        48,  # C_SE_NA_1  set-point, normalised
        49,  # C_SE_NB_1  set-point, scaled
        50,  # C_SE_NC_1  set-point, short float
        51,  # C_BO_NA_1  bitstring 32-bit command
        58,  # C_SC_TA_1  single command w/ time
        59,  # C_DC_TA_1  double command w/ time
        60,  # C_RC_TA_1  regulating step w/ time
        61,  # C_SE_TA_1  set-point (norm) w/ time
        62,  # C_SE_TB_1  set-point (scaled) w/ time
        63,  # C_SE_TC_1  set-point (float) w/ time
        64,  # C_BO_TA_1  bitstring command w/ time
    }
)


def server_available() -> bool:
    """True only if ``c104`` is importable AND ships the server + seed point types."""
    try:
        import c104  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — any import failure means "unavailable"
        return False
    if not all(hasattr(c104, name) for name in ("Server", "Client", "Type", "Init")):
        return False
    return all(hasattr(c104.Type, name) for name in ("M_ME_NC_1", "M_SP_NA_1"))


def free_port() -> int:
    """Reserve and return an ephemeral loopback TCP port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def incoming_type_id(apdu: bytes) -> int | None:
    """Extract the ASDU TypeID from a received IEC-104 APDU, or None.

    APCI layout: ``0x68`` start, 1 length octet, 4 control-field octets, then the
    ASDU (TypeID is its first octet). Only I-format frames (control octet 1, bit 0
    == 0) carry an ASDU; S/U-format frames do not.
    """
    if len(apdu) < 7 or apdu[0] != 0x68:
        return None
    if apdu[2] & 0x01:  # S- or U-format APCI — no ASDU
        return None
    return apdu[6]


def start_server(port: int) -> tuple[Any, list[int]]:
    """Build the seeded model and start a real c104 server on ``port``.

    Returns ``(server, received_type_ids)`` where ``received_type_ids`` is a live
    list the server appends every incoming ASDU TypeID to (for the monitor-only
    assertion). Guard with :func:`server_available` first.
    """
    import c104  # noqa: PLC0415

    server = c104.Server(ip="127.0.0.1", port=port)
    station = server.add_station(common_address=COMMON_ADDRESS)

    measured = station.add_point(io_address=SEED_MEASURED_IOA, type=c104.Type.M_ME_NC_1)
    measured.value = SEED_MEASURED_VALUE
    single = station.add_point(io_address=SEED_SINGLE_IOA, type=c104.Type.M_SP_NA_1)
    single.value = SEED_SINGLE_VALUE

    received_type_ids: list[int] = []

    def _record_incoming(server: Any, data: bytes) -> None:  # c104 on_receive_raw sig
        type_id = incoming_type_id(bytes(data))
        if type_id is not None:
            received_type_ids.append(type_id)

    server.on_receive_raw(callable=_record_incoming)
    server.start()
    return server, received_type_ids


def stop_server(server: Any) -> None:
    """Best-effort stop of the c104 server."""
    stop = getattr(server, "stop", None)
    if callable(stop):
        try:
            stop()
        except Exception:  # noqa: BLE001 — teardown is best-effort
            pass
