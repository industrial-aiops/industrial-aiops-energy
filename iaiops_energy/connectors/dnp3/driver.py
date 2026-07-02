"""DNP3 master adapter over ``pydnp3`` / opendnp3 (待核实, read-only).

opendnp3's master is callback-driven: a ``DNP3Manager`` owns a TCP channel, a
master station is added with a ``ISOEHandler`` that receives measurements, and an
integrity poll (Class 0/1/2/3) pulls the outstation's database. The exact pydnp3
binding surface is intricate and **UNVERIFIED** against a live outstation here
(preview), so this adapter is the single place the library-specific calls live —
isolated behind a tiny uniform interface (``enable`` / ``is_online`` /
``integrity_poll`` / ``shutdown``) that the ops and tests use. ``pydnp3`` is
imported LAZILY inside :func:`build_master_adapter` so this module imports cleanly
without the package.
"""

from __future__ import annotations

import threading
from typing import Any

# opendnp3 AddTCPClient's "local adapter" arg = which local interface the OUTBOUND
# client binds; "any" is the normal default for a client (this is not a server
# listener, so the B104 bind-all warning does not apply).
_ANY_LOCAL_ADAPTER = "0.0.0.0"  # nosec B104


def build_master_adapter(host: str, port: int, outstation: int, master: int) -> Any:
    """Build a DNP3 master adapter bound to ``host:port`` (待核实).

    Returns an object exposing the uniform read interface the ops rely on. The
    body wires opendnp3 via pydnp3; because that binding is unverified here, the
    SOEHandler / scan calls are best-effort and may need adjustment against the
    installed pydnp3 version (open an issue with your version if a symbol differs).
    """
    from pydnp3 import asiodnp3, asiopal, opendnp3, openpal  # noqa: F401

    return _Pydnp3MasterAdapter(
        asiodnp3=asiodnp3, opendnp3=opendnp3, asiopal=asiopal, openpal=openpal,
        host=host, port=port, outstation=outstation, master=master,
    )


# Map opendnp3 group numbers to a human measurement type (monitor direction).
_GROUP_TYPE = {
    1: "binary_input", 2: "binary_input_event", 3: "double_bit_binary",
    20: "counter", 21: "frozen_counter", 22: "counter_event",
    30: "analog_input", 32: "analog_input_event",
    40: "analog_output_status", 10: "binary_output_status",
    50: "time_and_interval", 110: "octet_string",
}

# opendnp3 delivers measurements to ISOEHandler.Process as typed collections whose
# pybind11 class is named ``ICollectionIndexed<Type>``. Map that (prefix stripped)
# to the DNP3 object group so a poll can label each point without a group byte.
_COLLECTION_GROUP = {
    "IndexedBinary": 1,
    "IndexedDoubleBitBinary": 3,
    "IndexedAnalog": 30,
    "IndexedCounter": 20,
    "IndexedFrozenCounter": 21,
    "IndexedBinaryOutputStatus": 10,
    "IndexedAnalogOutputStatus": 40,
    "IndexedTimeAndInterval": 50,
    "IndexedOctetString": 110,
}


def measurement_type(group: int) -> str:
    """Human measurement type for a DNP3 object group (used by the ops + tests)."""
    return _GROUP_TYPE.get(int(group), f"group_{int(group)}")


def _harvest_collection(values: Any, out: list[dict]) -> None:
    """Append every measurement in an opendnp3 ``ICollection`` to ``out``.

    opendnp3 hands the master a read-only typed collection per object group; its
    ``ForeachItem(callback)`` visits each ``Indexed<T>`` (``.index`` + ``.value``,
    where the inner measurement carries ``.value`` / ``.flags`` / ``.time``).
    """
    name = type(values).__name__.replace("ICollection", "")
    group = _COLLECTION_GROUP.get(name, 0)
    mtype = measurement_type(group)

    def _on_item(item: Any) -> None:
        meas = getattr(item, "value", None)
        out.append({
            "group": group,
            "type": mtype,
            "index": int(getattr(item, "index", 0)),
            "value": getattr(meas, "value", None),
            "quality": str(getattr(meas, "flags", "")),
            "timestamp": str(getattr(meas, "time", "")),
        })

    values.ForeachItem(_on_item)


def _settle(predicate, timeout_s: float, poll_s: float = 0.05) -> bool:
    """Bounded wait for an async scan to deliver points (never loops forever)."""
    import time

    deadline = time.monotonic() + max(0.0, timeout_s)
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(poll_s)
    return bool(predicate())


class _CollectingSOEHandler:
    """Point store shared between the SOE handler and :meth:`integrity_poll`.

    Holds the flat ``points`` list the ISOEHandler (see :meth:`_make_soe`) appends
    harvested measurements to and that the poll reads back. Kept as a plain object so
    the module stays importable / unit-testable without the ``pydnp3`` binding.
    """

    def __init__(self) -> None:
        self.points: list[dict] = []


class _Pydnp3MasterAdapter:
    """Uniform read adapter over an opendnp3 master (待核实).

    Only the four methods the ops use are exposed. Construction defers the actual
    channel/master wiring to :meth:`enable` so building the adapter never blocks.
    """

    def __init__(self, *, asiodnp3, opendnp3, asiopal, openpal,
                 host: str, port: int, outstation: int, master: int) -> None:
        self._asiodnp3 = asiodnp3
        self._opendnp3 = opendnp3
        self._asiopal = asiopal
        self._openpal = openpal
        self._host = host
        self._port = port
        self._outstation = outstation
        self._master = master
        self._manager = None
        self._channel = None
        self._dnpmaster = None
        # opendnp3's AddTCPClient / AddMaster bindings do NOT keep the Python
        # listener / SOE-handler alive, so we must hold references here or they are
        # garbage-collected and the reactor-thread callbacks abort the process.
        self._listener: Any = None
        self._soe: Any = None
        self._handler = _CollectingSOEHandler()
        self._enabled = False
        # Latest opendnp3 ChannelState delivered via OnStateChange (None until the
        # first callback arrives); drives is_online() for a live link reading.
        self._channel_state: Any = None

    def enable(self) -> None:
        """Open the channel + master and enable it (begins outstation link)."""
        o3, a3 = self._opendnp3, self._asiodnp3
        # A log handler is REQUIRED: opendnp3 logs through it as the stack runs, and a
        # DNP3Manager built without one dereferences a null handler and aborts on
        # Enable(). asiodnp3.ConsoleLogger is the library's stock handler; the channel
        # log filter below stays at NORMAL so this is not chatty.
        self._manager = a3.DNP3Manager(1, a3.ConsoleLogger().Create())
        self._listener = self._make_channel_listener()
        self._channel = self._manager.AddTCPClient(
            "iaiops", o3.levels.NORMAL, self._asiopal.ChannelRetry().Default(),
            self._host, _ANY_LOCAL_ADAPTER, self._port, self._listener,
        )
        stack = a3.MasterStackConfig()
        stack.link.LocalAddr = self._master
        stack.link.RemoteAddr = self._outstation
        self._soe = self._make_soe()
        self._dnpmaster = self._channel.AddMaster(
            "master", self._soe,
            self._asiodnp3.DefaultMasterApplication().Create(), stack,
        )
        self._dnpmaster.Enable()
        self._enabled = True

    def _make_soe(self) -> Any:
        """Return the ISOEHandler the master feeds; it harvests into our collector.

        opendnp3 requires an ``opendnp3.ISOEHandler`` whose ``Process(info, values)``
        is called (on the reactor thread) with each typed measurement collection; we
        subclass it and append harvested points to the SAME ``self._handler.points``
        list that :meth:`integrity_poll` reads. When the binding is absent (module
        imported without pydnp3 / unit mocks) we fall back to the plain collector so
        the module stays importable and mock-testable.
        """
        base = getattr(self._opendnp3, "ISOEHandler", None)
        if base is None:
            return self._handler
        points = self._handler.points

        class _SOEHandler(base):  # type: ignore[misc, valid-type]
            def Start(self) -> None:  # noqa: N802 — opendnp3 name
                pass

            def End(self) -> None:  # noqa: N802 — opendnp3 name
                pass

            def Process(self, info: Any, values: Any) -> None:  # noqa: N802
                _harvest_collection(values, points)

        return _SOEHandler()

    def _make_channel_listener(self) -> Any:
        """Build an opendnp3 ``IChannelListener`` that records live channel state.

        opendnp3 invokes ``OnStateChange(ChannelState)`` on the reactor thread as
        the TCP channel opens / closes; recording it lets :meth:`is_online` reflect
        the real link rather than merely that :meth:`enable` ran. 待核实: against the
        real pydnp3 binding the listener may need to subclass a specific C++ base —
        we subclass ``asiodnp3.IChannelListener`` when present and fall back to a
        plain object so the module stays importable / mock-testable without pydnp3.
        """
        base = getattr(self._asiodnp3, "IChannelListener", object)
        record = self._record_channel_state

        class _ChannelListener(base):  # type: ignore[misc, valid-type]
            def OnStateChange(self, state: Any) -> None:  # noqa: N802 — opendnp3 name
                record(state)

        return _ChannelListener()

    def _record_channel_state(self, state: Any) -> None:
        """Store the latest opendnp3 ChannelState (fed by the channel listener)."""
        self._channel_state = state

    def _channel_is_open(self) -> bool:
        """True when the recorded channel state is opendnp3 ``ChannelState.OPEN``."""
        open_state = getattr(getattr(self._opendnp3, "ChannelState", None), "OPEN", "OPEN")
        return self._channel_state == open_state

    def is_online(self) -> bool:
        """Report the live link state from opendnp3's channel callbacks.

        Once OnStateChange has delivered any ChannelState, reflect it (online ==
        channel OPEN). Before the first callback — or with a binding whose listener
        never fires — fall back to the enable() latch so behaviour never regresses
        below "enable() succeeded". 待核实: master link-layer status
        (IMasterApplication.OnStateChange / LinkStatus) is a deeper, unverified
        signal not yet wired; channel state is the verified one.
        """
        if self._channel_state is not None:
            return self._channel_is_open()
        return self._enabled

    def integrity_poll(self, settle_s: float = 2.0) -> list[dict]:
        """Run a Class 0/1/2/3 integrity scan and return the collected points.

        opendnp3 scans are asynchronous (the SOE handler is fed on the reactor
        thread), so after issuing the scan we wait — bounded by ``settle_s`` — for
        points to arrive rather than reading the empty list immediately.
        """
        if self._dnpmaster is None:
            return []
        self._handler.points.clear()
        # Integrity poll = a single Class 0/1/2/3 read. opendnp3's IMaster exposes
        # ``ScanClasses(field, config=default)`` for exactly this; ``ScanAllObjects``
        # is a DIFFERENT call (it takes a GroupVariationID, not a ClassField) and
        # must not be used here.
        scan = getattr(self._dnpmaster, "ScanClasses", None)
        if callable(scan):
            scan(self._opendnp3.ClassField.AllClasses())
            _settle(lambda: bool(self._handler.points), settle_s)
        return list(self._handler.points)

    def shutdown(self, timeout_s: float = 5.0) -> None:
        """Best-effort teardown that never blocks the caller.

        ``pydnp3``'s ``DNP3Manager.Shutdown()`` joins the opendnp3 reactor threads
        and, in the pinned 0.1.0 build, can block indefinitely; dropping the master
        / channel references first instead ABORTS (the C++ side still calls back into
        the Python listener). So we run ``Shutdown()`` on a daemon thread and wait a
        bounded time: the Python objects stay referenced (no crash) and the caller is
        never hung. A slow reactor thread is left to exit with the process. 待核实:
        a pydnp3 build that releases the GIL / joins cleanly would let this block
        normally; the bounded wait is the safe behaviour for the pinned release.
        """
        self._enabled = False
        self._channel_state = None
        manager = self._manager
        self._manager = None
        if manager is None:
            return

        def _do_shutdown() -> None:
            try:
                manager.Shutdown()
            except Exception:  # noqa: BLE001 — shutdown is best-effort
                pass

        worker = threading.Thread(
            target=_do_shutdown, name="dnp3-shutdown", daemon=True
        )
        worker.start()
        worker.join(max(0.0, timeout_s))


__all__ = ["build_master_adapter", "measurement_type"]
