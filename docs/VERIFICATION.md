# Compatibility verification

## 2026-11-14 — iaiops 0.34.0

Energy package 0.2.0 on macOS, Python 3.12, against the published iaiops 0.34.0:

- `pytest -q -rs`: 99 passed, 3 skipped.
- Ruff check and format check: passed (40 files formatted).
- Bandit Medium+: zero findings.
- Development lock updated from iaiops 0.33.0 to 0.34.0.

The skipped tests require pydnp3, c104 and pyiec61850; native protocol libraries
were not installed in this Mac environment. This run verifies unit/API contracts,
not native-library interoperability or physical RTU/IED behavior. The existing
Linux CI performs the three library loopback tests separately. No real hardware
validation or new Energy release is claimed.
