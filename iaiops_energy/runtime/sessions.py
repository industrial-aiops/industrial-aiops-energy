"""Energy-edition connection session builders.

Moved from ``iaiops.core.runtime.connection`` for the industrial-aiops-energy
spin-out. Read-only monitoring; protocol libs (c104 / pydnp3 / pyiec61850) are
imported LAZILY so the package installs without them; failures degrade to a
teaching ``OTConnectionError``. 待核实 against a live RTU / IED.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from iaiops.core.runtime.config import TargetConfig
from iaiops.core.runtime.connection import OTConnectionError


def _build_iec104_client(target: TargetConfig) -> Any:
    """Construct (not start) an IEC 60870-5-104 client + connection (待核实).

    Expected ``c104`` surface (iec104-python): ``c104.Client()`` →
    ``client.add_connection(ip, port, init=c104.Init.INTERROGATION)`` → after
    ``client.start()`` the connection auto-runs a general interrogation and its
    stations' points populate. Module-level so tests monkeypatch it.
    """
    try:
        import c104
    except ImportError as exc:  # pragma: no cover — only without c104
        raise OTConnectionError(
            "The 'c104' package is not installed. IEC 60870-5-104 is an OPTIONAL "
            "extra: 'pip install iaiops-energy[iec104]'.",
            endpoint=target.name,
            protocol="iec104",
        ) from exc
    if not target.host:
        raise OTConnectionError(
            f"IEC-104 endpoint '{target.name}' has no host. Add 'host: <ip>' (and "
            f"'common_address:' for the ASDU CA) to its config entry.",
            endpoint=target.name,
            protocol="iec104",
        )
    client = c104.Client()
    _register_iec104_discovery(client)
    init = getattr(getattr(c104, "Init", None), "INTERROGATION", None)
    conn = client.add_connection(ip=target.host, port=target.port or 2404, init=init)
    return client, conn


def _register_iec104_discovery(client: Any) -> None:
    """Auto-add unknown stations/points the RTU reports, so a general interrogation
    populates the client model (the documented ``c104`` discovery pattern).

    Monitor direction only — this mirrors the RTU's *monitored* points; no control
    point is ever created client-side. Best-effort: a binding that lacks these
    handlers (or an older API) simply skips registration.
    """
    on_new_station = getattr(client, "on_new_station", None)
    on_new_point = getattr(client, "on_new_point", None)

    # c104 strictly validates each callback by its real annotations. This module uses
    # `from __future__ import annotations` (annotations become strings), so after
    # defining each handler we set the exact expected signature as real c104 types.
    import c104  # noqa: PLC0415 — only reached when the client is a real c104 client

    if callable(on_new_station):

        def _add_station(client, connection, common_address):
            connection.add_station(common_address=common_address)

        _add_station.__annotations__ = {
            "client": c104.Client, "connection": c104.Connection,
            "common_address": int, "return": None,
        }
        on_new_station(callable=_add_station)

    if callable(on_new_point):

        def _add_point(client, station, io_address, point_type):
            station.add_point(io_address=io_address, type=point_type)

        _add_point.__annotations__ = {
            "client": c104.Client, "station": c104.Station,
            "io_address": int, "point_type": c104.Type, "return": None,
        }
        on_new_point(callable=_add_point)


@contextmanager
def iec104_session(target: TargetConfig, *, timeout_s: float = 10.0) -> Iterator[Any]:
    """Start an IEC-104 client, wait until connected, yield (client, conn), stop."""
    if target.protocol != "iec104":
        raise OTConnectionError(
            f"Endpoint '{target.name}' is protocol '{target.protocol}', not iec104.",
            endpoint=target.name, protocol=target.protocol,
        )
    # Build INSIDE the try so a 待核实 library/I-O failure in add_connection is
    # translated (not a raw traceback) and the client is always stopped.
    client = None
    try:
        client, conn = _build_iec104_client(target)
        client.start()
        if not _wait_until(lambda: bool(getattr(conn, "is_connected", False)), timeout_s):
            raise OTConnectionError(
                f"IEC-104 '{target.name}' ({target.host}:{target.port or 2404}) did not "
                f"connect within {timeout_s}s (RTU offline / wrong CA / firewall).",
                endpoint=target.host, protocol="iec104",
            )
        yield client, conn
    except OTConnectionError:
        raise
    except Exception as exc:  # noqa: BLE001 — translate any failure
        raise _translate_energy(exc, target, "iec104", target.port or 2404) from exc
    finally:
        if client is not None:
            try:
                client.stop()
            except Exception:  # noqa: BLE001 — stop must not mask the real error
                pass


def _build_dnp3_client(target: TargetConfig) -> Any:
    """Construct a DNP3 master adapter for ``target`` (待核实).

    DNP3 (pydnp3/opendnp3) is callback-based: a master is added to a TCP channel
    with a SOEHandler that collects measurements on an integrity poll. The exact
    binding is intricate and UNVERIFIED here; we expect a small adapter exposing
    ``integrity_poll() -> list[point]`` and ``is_online() -> bool``. Module-level
    so tests monkeypatch it with a fake adapter.
    """
    try:
        import pydnp3  # noqa: F401
    except ImportError as exc:  # pragma: no cover — only without pydnp3
        raise OTConnectionError(
            "The 'pydnp3' package is not installed. DNP3 is an OPTIONAL extra: "
            "'pip install iaiops-energy[dnp3]'.",
            endpoint=target.name, protocol="dnp3",
        ) from exc
    if not target.host:
        raise OTConnectionError(
            f"DNP3 endpoint '{target.name}' has no host. Add 'host: <ip>' (and "
            f"'unit_id:' = outstation address, 'master_address:') to its config.",
            endpoint=target.name, protocol="dnp3",
        )
    from iaiops_energy.connectors.dnp3.driver import build_master_adapter

    return build_master_adapter(
        host=target.host, port=target.port or 20000,
        outstation=target.unit_id, master=getattr(target, "master_address", 0) or 1,
    )


@contextmanager
def dnp3_session(target: TargetConfig, *, timeout_s: float = 10.0) -> Iterator[Any]:
    """Bring a DNP3 master online, yield the adapter, always shut it down."""
    if target.protocol != "dnp3":
        raise OTConnectionError(
            f"Endpoint '{target.name}' is protocol '{target.protocol}', not dnp3.",
            endpoint=target.name, protocol=target.protocol,
        )
    adapter = _build_dnp3_client(target)
    try:
        adapter.enable()
        if not _wait_until(lambda: bool(adapter.is_online()), timeout_s):
            raise OTConnectionError(
                f"DNP3 '{target.name}' ({target.host}:{target.port or 20000}) did not "
                f"come online within {timeout_s}s (outstation offline / wrong addr).",
                endpoint=target.host, protocol="dnp3",
            )
        yield adapter
    except OTConnectionError:
        raise
    except Exception as exc:  # noqa: BLE001 — translate any failure
        raise _translate_energy(exc, target, "dnp3", target.port or 20000) from exc
    finally:
        try:
            adapter.shutdown()
        except Exception:  # noqa: BLE001 — shutdown must not mask the real error
            pass


def _build_iec61850_client(target: TargetConfig) -> Any:
    """Construct (not connect) an IEC 61850 MMS client for ``target`` (待核实).

    Expected ``iec61850`` (libiec61850 SWIG) surface: an ``IedConnection`` created
    and connected to ``host:port`` (MMS over ISO-on-TCP, port 102). We wrap the
    raw connection in a small adapter exposing ``get_logical_devices()``,
    ``get_data_directory(ld)`` and ``read(ref, fc)``. Module-level so tests
    monkeypatch it with a fake adapter.
    """
    try:
        import pyiec61850  # noqa: F401 — libiec61850 SWIG binding (NOT 'iec61850')
    except ImportError as exc:  # pragma: no cover — only without the binding
        raise OTConnectionError(
            "The 'pyiec61850' (libiec61850 SWIG) binding is not installed. IEC 61850 "
            "is an OPTIONAL extra: 'pip install iaiops-energy[iec61850]' (linux-only "
            "wheel).",
            endpoint=target.name, protocol="iec61850",
        ) from exc
    if not target.host:
        raise OTConnectionError(
            f"IEC-61850 endpoint '{target.name}' has no host. Add 'host: <ip>' (MMS "
            f"port defaults to 102) to its config entry.",
            endpoint=target.name, protocol="iec61850",
        )
    from iaiops_energy.connectors.iec61850.driver import build_mms_adapter

    return build_mms_adapter(host=target.host, port=target.port or 102)


@contextmanager
def iec61850_session(target: TargetConfig, *, timeout_s: float = 10.0) -> Iterator[Any]:
    """Connect an IEC 61850 MMS client, yield the adapter, always close.

    ``timeout_s`` bounds the MMS connect + every request (passed through to the
    adapter's IedConnection timeouts) so a dead IED cannot hang the worker on the OS
    default (~75s) — matching the bounded iec104/dnp3 sessions.
    """
    if target.protocol != "iec61850":
        raise OTConnectionError(
            f"Endpoint '{target.name}' is protocol '{target.protocol}', not iec61850.",
            endpoint=target.name, protocol=target.protocol,
        )
    adapter = _build_iec61850_client(target)
    try:
        adapter.connect(timeout_s)
        yield adapter
    except OTConnectionError:
        raise
    except Exception as exc:  # noqa: BLE001 — translate any failure
        raise _translate_energy(exc, target, "iec61850", target.port or 102) from exc
    finally:
        try:
            adapter.close()
        except Exception:  # noqa: BLE001 — close must not mask the real error
            pass


def _wait_until(predicate, timeout_s: float, poll_s: float = 0.05) -> bool:
    """Poll ``predicate`` until True or ``timeout_s`` elapses (bounded, never loops forever)."""
    import time

    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() < deadline:
        try:
            if predicate():
                return True
        except Exception:  # noqa: BLE001 — a not-ready probe is just False
            pass
        time.sleep(poll_s)
    try:
        return bool(predicate())
    except Exception:  # noqa: BLE001
        return False


def _translate_energy(
    exc: Exception, target: TargetConfig, protocol: str, port: int
) -> OTConnectionError:
    """Map an energy-protocol library/OS exception to a teaching error."""
    detail = str(exc).strip()[:200]
    where = f"{target.host}:{port}"
    return OTConnectionError(
        f"{protocol.upper()} operation on '{target.name}' ({where}) failed: {detail}. "
        f"Check host/port/addressing and that the device is reachable. Preview — "
        f"validate against a real RTU/IED or a protocol simulator.",
        endpoint=where, protocol=protocol,
    )
