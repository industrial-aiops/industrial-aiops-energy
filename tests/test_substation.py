"""Substation SOE protection-trip analysis — pure-function + governed-tool tests.

Covers the four coordination verdicts (selective / backup / breaker-failure /
insufficient), unparseable-timestamp handling, free-text label inference, and
the MCP tool's governance markers. No live protocol I/O is exercised — the
analysis is pure, so these run without any optional protocol extra.
"""

from __future__ import annotations

import pytest

from iaiops_energy.analysis import substation
from iaiops_energy.mcp.tools.substation_tools import substation_event_analysis as tool

pytestmark = pytest.mark.unit


def _ev(ref: str, type_: str, ts: str, **extra: object) -> dict:
    return {"ref": ref, "type": type_, "timestamp": ts, **extra}


@pytest.mark.unit
def test_selective_trip_single_breaker() -> None:
    """One trip cleared by exactly one prompt breaker open → selective."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_trip", "2026-07-12T10:00:00Z"),
            _ev("R1", "breaker_open", "2026-07-12T10:00:00.080Z"),
        ]
    )
    assert result["verdict"] == "selective_trip"
    assert result["coordination"]["status"] == "selective"
    assert result["breaker_open_count"] == 1
    assert result["first_protection"] == {"ref": "R1", "ts": "2026-07-12T10:00:00"}
    assert result["affected_refs"] == ["R1"]


@pytest.mark.unit
def test_backup_operation_multiple_breakers() -> None:
    """More than one breaker opening → non-selective backup operation."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_trip", "2026-07-12T10:00:00Z"),
            _ev("R1", "breaker_open", "2026-07-12T10:00:00.050Z"),
            _ev("R2", "breaker_open", "2026-07-12T10:00:00.100Z"),
        ]
    )
    assert result["verdict"] == "backup_operation"
    assert result["breaker_open_count"] == 2
    assert result["coordination"]["status"] == "non_selective"


@pytest.mark.unit
def test_backup_operation_delayed_same_breaker() -> None:
    """The tripped breaker opening only after the backup margin → backup."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_trip", "2026-07-12T10:00:00Z"),
            _ev("R1", "breaker_open", "2026-07-12T10:00:00.700Z"),
        ],
        backup_margin_s=0.5,
    )
    assert result["verdict"] == "backup_operation"
    assert result["breaker_open_count"] == 1


@pytest.mark.unit
def test_breaker_failure_local_silent_then_remote_open() -> None:
    """Trip with no local breaker open, then a remote breaker open → 50BF."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_trip", "2026-07-12T10:00:00Z"),
            _ev("BK2", "breaker_open", "2026-07-12T10:00:00.300Z"),
        ]
    )
    assert result["verdict"] == "breaker_failure"
    assert result["coordination"]["status"] == "breaker_failure"
    assert "BK2" in result["coordination"]["detail"]


@pytest.mark.unit
def test_insufficient_empty_events() -> None:
    result = substation.substation_event_analysis([])
    assert result["verdict"] == "insufficient"
    assert result["events_analyzed"] == 0
    assert result["first_protection"] is None
    assert result["first_breaker_open"] is None


@pytest.mark.unit
def test_insufficient_no_protection_no_breaker() -> None:
    """A lone bus-undervoltage (no protection, no open) → insufficient."""
    result = substation.substation_event_analysis(
        [_ev("BUS1", "bus_undervoltage", "2026-07-12T10:00:00Z")]
    )
    assert result["verdict"] == "insufficient"
    assert result["events_analyzed"] == 1
    assert result["affected_refs"] == ["BUS1"]


@pytest.mark.unit
def test_unparseable_timestamps_counted_as_ignored() -> None:
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_trip", "2026-07-12T10:00:00Z"),
            _ev("R1", "breaker_open", "not-a-timestamp"),
            _ev("R2", "breaker_open", ""),
            {"ref": "R3", "type": "breaker_open"},  # missing timestamp
        ]
    )
    assert result["ignored"] == 3
    assert result["events_analyzed"] == 1


@pytest.mark.unit
def test_label_keyword_inference_when_type_absent() -> None:
    """A free-text label drives classification when ``type`` is missing."""
    result = substation.substation_event_analysis(
        [
            {"ref": "R1", "label": "Feeder 51 relay TRIP", "timestamp": "2026-07-12T10:00:00Z"},
            {"ref": "R1", "label": "Breaker 52 OPEN", "timestamp": "2026-07-12T10:00:00.06Z"},
        ]
    )
    assert result["verdict"] == "selective_trip"
    assert result["timeline"][0]["type"] == "protection_trip"
    assert result["timeline"][1]["type"] == "breaker_open"


@pytest.mark.unit
def test_lone_breaker_open_without_protection_is_not_selective() -> None:
    """One breaker open but NO protection pickup/trip → never 'selective_trip'."""
    result = substation.substation_event_analysis(
        [_ev("BK1", "breaker_open", "2026-07-12T10:00:00Z")]
    )
    assert result["verdict"] == "breaker_operation_no_protection"
    assert result["coordination"]["status"] == "no_protection_record"
    assert result["breaker_open_count"] == 1
    assert result["first_protection"] is None
    assert "no protection" in result["coordination"]["detail"].lower()


@pytest.mark.unit
def test_selective_still_requires_a_protection_event() -> None:
    """With a protection pickup + one breaker open it IS selective (contrast case)."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_pickup", "2026-07-12T10:00:00Z"),
            _ev("R1", "breaker_open", "2026-07-12T10:00:00.080Z"),
        ]
    )
    assert result["verdict"] == "selective_trip"


@pytest.mark.unit
def test_mixed_tz_naive_entries_are_rejected_not_assumed_utc() -> None:
    """When any event is tz-aware, tz-naive entries are ambiguous → ignored."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_trip", "2026-07-12T10:00:00+00:00"),  # aware
            _ev("BK2", "breaker_open", "2026-07-12T10:00:00.300"),      # naive → drop
        ]
    )
    assert result["ignored"] == 1
    assert result["events_analyzed"] == 1
    assert result["first_breaker_open"] is None  # the naive open was rejected


@pytest.mark.unit
def test_all_naive_events_still_analyzed() -> None:
    """A uniformly tz-naive SOE is kept as-is (no spurious rejection)."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "protection_trip", "2026-07-12T10:00:00"),
            _ev("R1", "breaker_open", "2026-07-12T10:00:00.080"),
        ]
    )
    assert result["ignored"] == 0
    assert result["events_analyzed"] == 2
    assert result["verdict"] == "selective_trip"


@pytest.mark.unit
def test_return_shape_has_all_keys_and_note() -> None:
    result = substation.substation_event_analysis(
        [_ev("R1", "protection_trip", "2026-07-12T10:00:00Z")]
    )
    expected_keys = {
        "events_analyzed",
        "ignored",
        "verdict",
        "first_protection",
        "first_breaker_open",
        "breakers_opened",
        "breaker_open_count",
        "affected_refs",
        "timeline",
        "coordination",
        "note",
    }
    assert expected_keys <= set(result)
    assert "monitor-only" in result["note"]
    assert set(result["coordination"]) == {"status", "detail"}


@pytest.mark.unit
def test_events_are_sorted_regardless_of_input_order() -> None:
    """Out-of-order input still resolves the correct first events."""
    result = substation.substation_event_analysis(
        [
            _ev("R1", "breaker_open", "2026-07-12T10:00:00.080Z"),
            _ev("R1", "protection_trip", "2026-07-12T10:00:00Z"),
        ]
    )
    assert result["verdict"] == "selective_trip"
    assert result["first_protection"]["ts"] == "2026-07-12T10:00:00"


@pytest.mark.unit
def test_tool_is_governed_low_risk_and_runs() -> None:
    """The MCP tool carries the governance markers and returns a verdict."""
    assert getattr(tool, "_is_governed_tool", False) is True
    assert getattr(tool, "_risk_level", None) == "low"
    result = tool(
        events=[
            _ev("R1", "protection_trip", "2026-07-12T10:00:00Z"),
            _ev("R1", "breaker_open", "2026-07-12T10:00:00.080Z"),
        ]
    )
    assert result["verdict"] == "selective_trip"
