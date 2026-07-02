"""Energy-edition connection target with protocol-specific addressing.

The shared base :class:`iaiops.core.runtime.config.TargetConfig` is
protocol-neutral. Energy telecontrol protocols carry addressing the base does not
model:

  * IEC 60870-5-104 — an ASDU **common address** selecting the station.
  * DNP3 (IEEE 1815) — a **master (source) link address** alongside the
    outstation address (the base ``unit_id``).

:class:`EnergyTarget` extends the base with those two immutable fields. The energy
ops read them defensively via ``getattr`` (so a plain base ``TargetConfig`` still
works, defaulting them), and this type is what a caller constructs when the extra
addressing matters. Importing this module ensures the energy protocols are
registered with the base config (via the package ``__init__``).
"""

from __future__ import annotations

from dataclasses import dataclass

from iaiops.core.runtime.config import TargetConfig

import iaiops_energy as _energy  # noqa: F401 — ensures protocol registration ran


@dataclass(frozen=True)
class EnergyTarget(TargetConfig):
    """A base ``TargetConfig`` plus energy telecontrol addressing.

    ``common_address`` is the IEC-104 ASDU CA (0 = unset → first station);
    ``master_address`` is the DNP3 master/source link address (default 1).
    """

    common_address: int = 0
    master_address: int = 1
