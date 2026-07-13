"""IEC 61850 MMS client adapter over ``libiec61850`` (verified, read-only).

libiec61850's Python binding (SWIG, published on PyPI as ``pyiec61850``) exposes a
procedural ``IedConnection`` API: create → connect → browse the model (logical
devices → logical nodes → data objects/attributes) → read a data attribute by
object-reference + functional constraint (FC, e.g. MX for measurands, ST for
status).

The SWIG surface has two conventions this adapter normalizes:

  * Most calls return a 2-element ``[payload, IedClientError]`` — the payload is a
    ``LinkedList`` (browse) or an ``MmsValue`` (read); a *bare int* return is a
    standalone error code with no payload.
  * String results are wrapped in a ``LinkedList`` that must be walked with
    ``LinkedList_getNext``/``LinkedList_getData``/``toCharP`` (not Python-iterable).

All library calls are isolated behind a uniform interface
(``connect`` / ``close`` / ``get_logical_devices`` / ``get_data_directory`` /
``read``). The binding is imported LAZILY in :func:`build_mms_adapter`. The
client↔server MMS round-trip is verified against an in-process libiec61850 MMS
server (see ``tests/test_iec61850_live.py``).
"""

from __future__ import annotations

from typing import Any

# IEC 61850 functional constraints we surface for reads (monitor-relevant subset).
FUNCTIONAL_CONSTRAINTS = ("MX", "ST", "CF", "DC", "SP", "SG", "SE", "EX")

# A non-zero sentinel error code returned by :meth:`_safe` when a binding call
# raises (absent helper / wrong arity) so it unwraps to a skippable failure.
_CALL_FAILED = -1


class BrowseError(RuntimeError):
    """A model-browse call genuinely FAILED (vs. a legitimately empty node).

    Raised so a failed browse surfaces an error instead of an indistinguishable
    empty ``[]``. The session translates it to a teaching ``OTConnectionError``.
    """


def build_mms_adapter(host: str, port: int) -> Any:
    """Build an IEC 61850 MMS client adapter for ``host:port``.

    The binding is the libiec61850 SWIG wrapper, published on PyPI as ``pyiec61850``
    (NOT the unrelated ``iec61850`` async-OOP distribution).
    """
    import pyiec61850 as iec61850

    return _LibIec61850Adapter(iec61850, host, port)


class _LibIec61850Adapter:
    """Uniform read adapter over a libiec61850 ``IedConnection`` (verified).

    Only browse + read are exposed (read-only). Control blocks (Oper/SBO) are not
    wired. Methods degrade gracefully — a binding that lacks a helper returns an
    empty list/error dict rather than raising.
    """

    def __init__(self, lib: Any, host: str, port: int) -> None:
        self._lib = lib
        self._host = host
        self._port = port
        self._conn = None

    def connect(self, timeout_s: float | None = None) -> None:
        lib = self._lib
        self._conn = lib.IedConnection_create()
        # Bound the connect + every request BEFORE dialing: a dead IED otherwise
        # hangs the MMS round-trip on the OS default (~75s) or indefinitely, blocking
        # the MCP worker. Deriving both from the session timeout keeps this session in
        # step with the bounded iec104/dnp3 sessions.
        if timeout_s is not None and timeout_s > 0:
            self._apply_timeouts(timeout_s)
        # IedConnection_connect(con, host, port) — returns a bare IedClientError
        # scalar in this binding (0 == success). Some builds return a tuple; treat
        # a non-zero code in EITHER form as a failure so a bad connect raises the
        # teaching error instead of "succeeding" and confusing later reads.
        result = lib.IedConnection_connect(self._conn, self._host, self._port)
        _, code = self._unwrap(result)
        if isinstance(code, int) and code != 0:
            raise ConnectionError(f"IedConnection_connect error={code}")

    def _apply_timeouts(self, timeout_s: float) -> None:
        """Set the IedConnection connect + request timeouts (milliseconds).

        Best-effort: a binding lacking a setter cannot be bounded here (待核实), but
        the common libiec61850 SWIG surface exposes both. Never raises — a missing
        setter must not defeat a connect the binding could still make.
        """
        lib = self._lib
        ms = int(max(1.0, timeout_s * 1000.0))
        for name in ("IedConnection_setConnectTimeout", "IedConnection_setRequestTimeout"):
            fn = getattr(lib, name, None)
            if callable(fn):
                try:
                    fn(self._conn, ms)
                except Exception:  # noqa: BLE001 — best-effort timeout setter
                    pass

    def close(self) -> None:
        lib, con = self._lib, self._conn
        if con is None:
            return
        for name in ("IedConnection_close", "IedConnection_destroy"):
            fn = getattr(lib, name, None)
            if callable(fn):
                try:
                    fn(con)
                except Exception:  # noqa: BLE001 — teardown is best-effort
                    pass

    def get_logical_devices(self) -> list[str]:
        """List the IED's logical devices.

        Distinguishes a genuinely empty model (returns ``[]``) from a *failed* browse
        (raises): a swallowed failure returning ``[]`` would be indistinguishable from
        an empty device and violate the iron rule (a failed read must error). The
        raised error is translated to an ``OTConnectionError`` by the session.
        """
        fn = getattr(self._lib, "IedConnection_getLogicalDeviceList", None)
        if not callable(fn):
            raise BrowseError("binding lacks IedConnection_getLogicalDeviceList")
        payload, err = self._unwrap(self._safe(fn, self._conn))
        if err not in (0, None):
            raise BrowseError(f"getLogicalDeviceList failed (IedClientError={err})")
        if payload is None:
            return []  # a successful call with no payload → legitimately empty
        names = self._linkedlist_to_str(payload)
        self._free_list(payload)
        return names

    def get_data_directory(self, reference: str) -> list[str]:
        """Browse children of a model reference (LD, LN, or DO).

        The correct libiec61850 call depends on the reference level: an LD is
        browsed with ``getLogicalDeviceDirectory`` (→ logical nodes), an LN with
        ``getLogicalNodeDirectory`` (→ data objects), a DO with ``getDataDirectory``
        (→ data attributes). We try them in that order and take the first that
        returns success with a non-empty payload.
        """
        acsi_do = getattr(self._lib, "ACSI_CLASS_DATA_OBJECT", None)
        attempts: tuple[tuple[str, tuple[Any, ...]], ...] = (
            ("IedConnection_getLogicalDeviceDirectory", (reference,)),
            ("IedConnection_getLogicalNodeDirectory", (reference, acsi_do)),
            ("IedConnection_getDataDirectory", (reference,)),
        )
        saw_success = False
        for name, extra in attempts:
            fn = getattr(self._lib, name, None)
            if not callable(fn):
                continue
            payload, err = self._unwrap(self._safe(fn, self._conn, *extra))
            if err not in (0, None):
                continue  # wrong browse level for this reference — try the next
            saw_success = True
            if payload is not None:
                names = self._linkedlist_to_str(payload)
                self._free_list(payload)
                if names:
                    return names
            # success but empty payload at this level → keep trying other levels
        if not saw_success:
            # Every applicable browse call failed (error code / absent) — surface it
            # rather than fabricate a successful-but-empty node (iron rule).
            raise BrowseError(f"browse of '{reference}' failed at every ACSI level")
        return []  # a level succeeded with no children → legitimately empty node

    def read(self, reference: str, fc: str) -> dict:
        """Read one data attribute by object-reference + functional constraint."""
        lib = self._lib
        fc_val = self._fc_value(fc)
        reader = getattr(lib, "IedConnection_readObject", None)
        if not callable(reader):
            return {"reference": reference, "fc": fc, "error": "binding lacks readObject"}
        payload, err = self._unwrap(self._safe(reader, self._conn, reference, fc_val))
        if err not in (0, None):
            return {
                "reference": reference,
                "fc": fc,
                "error": f"read failed (IedClientError={err})",
            }
        if payload is None:
            return {
                "reference": reference,
                "fc": fc,
                "error": "no value returned (object not found / read failed)",
            }
        # A successful IedClientError (0) can still carry an MMS_DATA_ACCESS_ERROR
        # MmsValue (e.g. unknown object / wrong FC). Decoding that with a scalar
        # accessor silently yields 0.0 — so detect it and surface a real error.
        access_error = self._access_error(payload)
        if access_error is not None:
            self._free_mms(payload)
            return {
                "reference": reference,
                "fc": fc,
                "error": f"data access error ({access_error})",
            }
        value = self._decode_mms(payload)
        self._free_mms(payload)
        return {"reference": reference, "fc": fc, "value": value}

    # ─── helpers (binding-tolerant) ──────────────────────────────────────────

    def _safe(self, fn: Any, *args: Any) -> Any:
        """Call ``fn(*args)``, returning a skippable error code if it raises."""
        try:
            return fn(*args)
        except Exception:  # noqa: BLE001 — absent/mis-arity helper → error code
            return _CALL_FAILED

    @staticmethod
    def _unwrap(result: Any) -> tuple[Any, Any]:
        """Split a libiec61850 SWIG return into ``(payload, error_code)``.

        Most calls return ``[payload, IedClientError]``; a bare int is a standalone
        error code with no payload; anything else is treated as a bare payload.
        """
        if isinstance(result, (list, tuple)):
            if len(result) >= 2:
                return result[0], result[-1]
            if len(result) == 1:
                return result[0], 0
            return None, 0
        if isinstance(result, int):
            return None, result
        return result, 0

    def _linkedlist_to_str(self, head: Any) -> list[str]:
        """Walk a libiec61850 ``LinkedList`` of C strings into a list of ``str``."""
        lib = self._lib
        get_next = getattr(lib, "LinkedList_getNext", None)
        get_data = getattr(lib, "LinkedList_getData", None)
        if not (callable(get_next) and callable(get_data)):
            return self._to_str_list(head)  # non-libiec61850 shim fallback
        to_char = getattr(lib, "toCharP", None)
        out: list[str] = []
        try:
            element = get_next(head)
            while element:
                data = get_data(element)
                out.append(to_char(data) if callable(to_char) else str(data))
                element = get_next(element)
        except Exception:  # noqa: BLE001 — malformed list → what we have so far
            pass
        return [str(v) for v in out]

    def _free_list(self, head: Any) -> None:
        fn = getattr(self._lib, "LinkedList_destroy", None)
        if callable(fn):
            try:
                fn(head)
            except Exception:  # noqa: BLE001 — free is best-effort
                pass

    def _free_mms(self, mms_value: Any) -> None:
        fn = getattr(self._lib, "MmsValue_delete", None)  # free the C MmsValue
        if callable(fn):
            try:
                fn(mms_value)
            except Exception:  # noqa: BLE001 — free is best-effort
                pass

    def _access_error(self, mms_value: Any) -> Any:
        """Return the data-access-error name if ``mms_value`` is one, else None."""
        lib = self._lib
        get_type = getattr(lib, "MmsValue_getType", None)
        access_error_type = getattr(lib, "MMS_DATA_ACCESS_ERROR", object())
        if not callable(get_type):
            return None
        try:
            if get_type(mms_value) != access_error_type:
                return None
        except Exception:  # noqa: BLE001 — can't classify → not an access error
            return None
        detail = getattr(lib, "MmsValue_getDataAccessError", None)
        if callable(detail):
            try:
                return detail(mms_value)
            except Exception:  # noqa: BLE001
                pass
        return "MMS_DATA_ACCESS_ERROR"

    def _fc_value(self, fc: str) -> Any:
        """Resolve a functional-constraint string to the binding's FC enum value."""
        fc = (fc or "MX").upper()
        getter = getattr(self._lib, "FunctionalConstraint_fromString", None)
        if callable(getter):
            try:
                return getter(fc)
            except Exception:  # noqa: BLE001
                pass
        return getattr(self._lib, f"IEC61850_FC_{fc}", fc)

    def _decode_mms(self, mms_value: Any) -> Any:
        """Decode an ``MmsValue`` to a Python scalar/string using its MMS type.

        Critically, a numeric accessor is used ONLY when ``MmsValue_getType`` confirms
        a numeric type. The old fallback tried ``MmsValue_toFloat`` first, which
        libiec61850 returns ``0.0`` for a NON-float value — so a bitstring / quality /
        timestamp silently read as ``value: 0.0`` (a fabricated reading). For a type
        with no mapped accessor we return an opaque string encoding, never a bare 0.0.
        """
        lib = self._lib
        get_type = getattr(lib, "MmsValue_getType", None)
        if callable(get_type):
            decoder = self._typed_decoder(get_type, mms_value)
            if decoder is not None:
                try:
                    return decoder(mms_value)
                except Exception:  # noqa: BLE001 — fall through to opaque encoding
                    pass
            # Type known but unmapped (bitstring / quality / timestamp / …), or the
            # matched accessor raised: DO NOT guess with toFloat (fabricates 0.0).
            return self._opaque_mms(mms_value)
        # No getType on this binding: we cannot confirm a numeric type, so prefer
        # string/boolean accessors and NEVER toFloat (which would fabricate 0.0).
        for name in ("MmsValue_toString", "MmsValue_getBoolean"):
            fn = getattr(lib, name, None)
            if callable(fn):
                try:
                    return fn(mms_value)
                except Exception:  # noqa: BLE001 — wrong accessor for this type
                    continue
        return self._opaque_mms(mms_value)

    def _opaque_mms(self, mms_value: Any) -> Any:
        """Return a non-fabricating opaque encoding for an unmapped ``MmsValue``.

        Tries the string accessor (meaningful for many composite types); otherwise a
        type-tagged marker so the caller sees *what* it was, not a misleading scalar.
        """
        lib = self._lib
        to_string = getattr(lib, "MmsValue_toString", None)
        if callable(to_string):
            try:
                text = to_string(mms_value)
                if text not in (None, ""):
                    return str(text)
            except Exception:  # noqa: BLE001 — not a string-representable value
                pass
        get_type = getattr(lib, "MmsValue_getType", None)
        if callable(get_type):
            try:
                return f"<unmapped MmsValue type={get_type(mms_value)}>"
            except Exception:  # noqa: BLE001
                pass
        return str(mms_value)

    def _typed_decoder(self, get_type: Any, mms_value: Any) -> Any:
        """Pick the MmsValue accessor matching the value's MMS type (or None)."""
        lib = self._lib
        try:
            mms_type = get_type(mms_value)
        except Exception:  # noqa: BLE001
            return None
        type_to_accessor = {
            getattr(lib, "MMS_FLOAT", object()): "MmsValue_toFloat",
            getattr(lib, "MMS_INTEGER", object()): "MmsValue_toInt64",
            getattr(lib, "MMS_UNSIGNED", object()): "MmsValue_toUint32",
            getattr(lib, "MMS_BOOLEAN", object()): "MmsValue_getBoolean",
            getattr(lib, "MMS_VISIBLE_STRING", object()): "MmsValue_toString",
            getattr(lib, "MMS_STRING", object()): "MmsValue_toString",
        }
        accessor = type_to_accessor.get(mms_type)
        fn = getattr(lib, accessor, None) if accessor else None
        return fn if callable(fn) else None

    @staticmethod
    def _to_str_list(value: Any) -> list[str]:
        """Coerce a (possibly linked-list) binding result into a list of str."""
        if value in (None, ""):
            return []
        if isinstance(value, (list, tuple)):
            return [str(v) for v in value]
        try:
            return [str(v) for v in value]  # iterable LinkedList shim
        except TypeError:
            return [str(value)]


__all__ = ["build_mms_adapter", "FUNCTIONAL_CONSTRAINTS", "BrowseError"]
