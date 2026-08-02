"""industrial-aiops-energy — Energy edition connectors for Industrial-AIOps.

Importing this package registers the three energy protocols (IEC-104 / DNP3 /
IEC-61850) with the shared base config so ``TargetConfig`` validation accepts
them. The base package is protocol-neutral and ships without energy protocols;
each edition extends the supported set at import time (a plugin-registration
pattern — a NEW tuple/dict is bound, the base objects are never mutated in place).
"""

from __future__ import annotations

# Derived from the installed package metadata, like the base package does —
# pyproject.toml is the single source of truth. The hard-coded string this
# replaced said 0.1.3 while the package was on 0.1.11: eight releases of drift,
# reported to anything that read it.
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from iaiops.core.runtime import config as _config

try:
    __version__ = _pkg_version("iaiops-energy")
except PackageNotFoundError:  # a source tree that was never installed
    __version__ = "0.0.0+unknown"

# Energy protocols this edition adds to the shared base, with their default
# TCP/UDP ports (IEC-104 = 2404, DNP3 = 20000, IEC-61850 MMS = 102).
_ENERGY_PROTOCOLS: tuple[str, ...] = ("iec104", "dnp3", "iec61850")
_ENERGY_DEFAULT_PORTS: dict[str, int] = {"iec104": 2404, "dnp3": 20000, "iec61850": 102}


def _register_protocols() -> None:
    """Extend the base config's supported protocols + default ports (idempotent).

    Rebinds ``SUPPORTED_PROTOCOLS`` / ``_DEFAULT_PORTS`` to new objects rather than
    mutating them, so re-import is safe and the base package stays immutable.
    """
    missing = tuple(p for p in _ENERGY_PROTOCOLS if p not in _config.SUPPORTED_PROTOCOLS)
    if missing:
        _config.SUPPORTED_PROTOCOLS = _config.SUPPORTED_PROTOCOLS + missing
    if not _ENERGY_DEFAULT_PORTS.items() <= _config._DEFAULT_PORTS.items():
        _config._DEFAULT_PORTS = {**_config._DEFAULT_PORTS, **_ENERGY_DEFAULT_PORTS}


_register_protocols()

__all__ = ["__version__"]
