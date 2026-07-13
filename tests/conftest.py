"""Shared test fixtures — IAIOPS_HOME isolation (ported from the base repo).

The energy edition reuses the base ``iaiops`` governance harness: every
``@governed_tool`` call writes to the tamper-evident audit chain and the policy
/ budget / pattern / undo stores under ``IAIOPS_HOME`` (default ``~/.iaiops``).
Without isolation, tests that exercise governed tools (e.g. ``test_substation``,
``test_protocol_consistency`` which invokes every tool) pollute the developer's
REAL harness state and share process-global singletons across tests
(order-dependent budgets, cross-test audit rows). The autouse fixture below
gives every test a fresh throwaway home and fresh singletons.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from iaiops.core.governance.audit import reset_engine
from iaiops.core.governance.budget import reset_budget
from iaiops.core.governance.patterns import reset_pattern_engine
from iaiops.core.governance.policy import reset_policy_engine
from iaiops.core.governance.undo import reset_undo_store


def _reset_governance_singletons() -> None:
    """Drop every process-global governance singleton (rebuilt lazily on use)."""
    reset_engine()
    reset_policy_engine()
    reset_budget()
    reset_pattern_engine()
    reset_undo_store()


@pytest.fixture(autouse=True)
def isolated_iaiops_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point IAIOPS_HOME at a per-test tmp dir and reset governance singletons.

    This is a *default*: a test that sets its own ``IAIOPS_HOME`` and calls the
    reset functions runs after this fixture and simply wins — the two compose.
    The legacy ``OT_AIOPS_HOME`` fallback is cleared so a developer's shell
    environment can never redirect a test back to real state.
    """
    monkeypatch.setenv("IAIOPS_HOME", str(tmp_path))
    monkeypatch.delenv("OT_AIOPS_HOME", raising=False)
    _reset_governance_singletons()
    yield tmp_path
    _reset_governance_singletons()
