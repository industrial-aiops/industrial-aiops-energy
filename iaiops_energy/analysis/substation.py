"""Sequence-of-Events (SOE) protection-trip analysis for substations.

Pure, read-only reasoning over an injected list of time-stamped substation
events (relay pickups/trips, breaker open/close, lockouts, bus undervoltage) —
the "what tripped, and did protection coordinate correctly?" question a
substation engineer asks after a disturbance. No live protocol I/O happens
here: an agent harvests the SOE (e.g. via the energy edition's IEC-104 / DNP3 /
IEC 61850 reads, or a station-computer export) and feeds it in.

Protection-engineering intent
-----------------------------
* **Selectivity (coordination):** only the breaker CLOSEST to the fault should
  trip, isolating the smallest possible zone. One protection trip clearing via
  exactly one breaker, promptly, is the healthy signature.
* **Breaker failure (50BF):** if a faulted breaker fails to interrupt,
  breaker-failure protection trips the surrounding breakers after a short timer
  (``breaker_fail_window_s``). A trip with no local breaker open followed by a
  remote breaker open is that fingerprint — the outage is wider than intended.
* **Backup zones (zone-2/3, time-graded):** if primary protection or its
  breaker is slow/absent, an upstream backup clears the fault after a
  coordination margin (``backup_margin_s``). Multiple breakers opening, or a
  breaker opening only after that margin, means backup — not primary — operated:
  a non-selective, wider outage worth investigating.

Every returned claim is tied to a timestamped event (cite-first). This is
advisory structural analysis only; it never commands anything (monitor-only
edition).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

_PROTECTION_TYPES = frozenset({"protection_pickup", "protection_trip"})
_KNOWN_TYPES = frozenset(
    {
        "protection_pickup",
        "protection_trip",
        "breaker_open",
        "breaker_close",
        "lockout",
        "bus_undervoltage",
    }
)
# Ordered keyword → type inference for free-text labels / unknown ``type``.
# Order matters: more specific phrases are matched before generic ones.
_LABEL_KEYWORDS: tuple[tuple[str, str], ...] = (
    ("lockout", "lockout"),
    ("undervoltage", "bus_undervoltage"),
    ("under voltage", "bus_undervoltage"),
    ("bus uv", "bus_undervoltage"),
    ("pickup", "protection_pickup"),
    ("pick-up", "protection_pickup"),
    ("start", "protection_pickup"),
    ("trip", "protection_trip"),
    ("close", "breaker_close"),
    ("open", "breaker_open"),
)
# Bounds so a huge SOE cannot bloat the response.
_MAX_TIMELINE = 50
_MAX_LIST = 100
_NOTE = (
    "Advisory, monitor-only structural analysis of injected SOE events; no live "
    "protocol I/O and no control action. Every finding is tied to a timestamped "
    "event (cite-first) — verify against the station's relay targets and event "
    "recorder before acting."
)


@dataclass(frozen=True)
class _Event:
    """A normalized SOE entry (immutable)."""

    ref: str
    ts: datetime
    type: str


def _classify_type(raw_type: object, label: object) -> str:
    """Map a declared ``type`` (or free-text label) to a known event type."""
    if isinstance(raw_type, str) and raw_type in _KNOWN_TYPES:
        return raw_type
    text = " ".join(
        str(value).lower() for value in (raw_type, label) if isinstance(value, str)
    )
    for keyword, mapped in _LABEL_KEYWORDS:
        if keyword in text:
            return mapped
    return "other"


def _parse_ts(value: object) -> datetime | None:
    """Parse an ISO-8601 timestamp (tolerating a trailing ``Z``); None if bad.

    Timezone-awareness is PRESERVED here (aware stays aware, naive stays naive) so
    :func:`_normalize` can detect a mixed-tz SOE — a tz-naive local time silently
    treated as UTC would skew the inter-event delays that drive breaker-failure /
    backup-margin decisions.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _normalize(events: list[dict]) -> tuple[list[_Event], int]:
    """Parse + sort SOE events; return (sorted events, ignored count).

    Guards against a mixed timezone SOE: if ANY event is tz-aware, tz-naive entries
    are ambiguous (local vs UTC) and would corrupt inter-event delay math, so they
    are rejected (counted as ignored) rather than silently assumed UTC. All-aware
    events normalize to naive UTC; an all-naive SOE is left as-is (uniform).
    """
    raw: list[tuple[datetime, str, str]] = []
    ignored = 0
    for event in events:
        if not isinstance(event, dict):
            ignored += 1
            continue
        ts = _parse_ts(event.get("timestamp"))
        if ts is None:
            ignored += 1
            continue
        ref = str(event.get("ref", "")) or "?"
        etype = _classify_type(event.get("type"), event.get("label"))
        raw.append((ts, ref, etype))

    any_aware = any(ts.tzinfo is not None for ts, _, _ in raw)
    parsed: list[_Event] = []
    for ts, ref, etype in raw:
        if any_aware and ts.tzinfo is None:
            ignored += 1  # ambiguous tz-naive local time amid tz-aware events
            continue
        norm = ts.astimezone(UTC).replace(tzinfo=None) if ts.tzinfo is not None else ts
        parsed.append(_Event(ref=ref, ts=norm, type=etype))
    parsed.sort(key=lambda entry: entry.ts)
    return parsed, ignored


def _point(event: _Event | None) -> dict | None:
    """Cite a single event as ``{ref, ts}`` (or None)."""
    return {"ref": event.ref, "ts": event.ts.isoformat()} if event else None


def _distinct_opens(opens: list[_Event]) -> list[dict]:
    """First open time per distinct breaker ref, chronologically (``opens`` sorted)."""
    seen: dict[str, datetime] = {}
    for event in opens:
        seen.setdefault(event.ref, event.ts)
    return [{"ref": ref, "ts": ts.isoformat()} for ref, ts in seen.items()]


def _local_open_within(trip: _Event, opens: list[_Event], window_s: float) -> bool:
    """Did the tripped ref's own breaker open within the breaker-failure timer?"""
    for event in opens:
        delay = (event.ts - trip.ts).total_seconds()
        if event.ref == trip.ref and 0.0 <= delay <= window_s:
            return True
    return False


def _first_remote_open(trip: _Event, opens: list[_Event]) -> _Event | None:
    """Earliest breaker open on a DIFFERENT ref at/after the trip (``opens`` sorted)."""
    for event in opens:
        if event.ref != trip.ref and event.ts >= trip.ts:
            return event
    return None


def _breaker_failure_detail(trip: _Event, remote: _Event, window_s: float) -> str:
    delay = (remote.ts - trip.ts).total_seconds()
    return (
        f"Protection tripped on {trip.ref} but its own breaker did not open within "
        f"the {window_s:.3f}s breaker-failure window; breaker {remote.ref} opened "
        f"{delay:.3f}s later — breaker-failure backup operated (wider outage)."
    )


def _classify_verdict(
    protections: list[_Event],
    trips: list[_Event],
    opens: list[_Event],
    open_count: int,
    bf_window_s: float,
    margin_s: float,
) -> tuple[str, str, str]:
    """Return (verdict, coordination status, cite-first detail)."""
    if not protections and not opens:
        return "insufficient", "no_operation", (
            "No protection pickup/trip and no breaker-open events present — "
            "nothing to coordinate."
        )
    first_trip = trips[0] if trips else None
    reference = first_trip or (protections[0] if protections else opens[0])
    if first_trip is not None and not _local_open_within(first_trip, opens, bf_window_s):
        remote = _first_remote_open(first_trip, opens)
        if remote is not None:
            detail = _breaker_failure_detail(first_trip, remote, bf_window_s)
            return "breaker_failure", "breaker_failure", detail
    if open_count > 1:
        return "backup_operation", "non_selective", (
            f"{open_count} breakers opened — the outage spread beyond one zone; "
            "backup/adjacent protection operated (non-selective)."
        )
    if opens and (opens[0].ts - reference.ts).total_seconds() > margin_s:
        delay = (opens[0].ts - reference.ts).total_seconds()
        return "backup_operation", "non_selective", (
            f"Breaker {opens[0].ref} opened {delay:.3f}s after the first protection "
            f"event — beyond the {margin_s:.3f}s backup margin, so a slow/upstream "
            "time-graded backup cleared it (non-selective)."
        )
    if open_count == 1:
        if not protections:
            # A breaker opened but NO relay pickup/trip is in the SOE — this is not a
            # protection-cleared fault (no selectivity to confirm). Could be a manual/
            # local open or missing relay events; never label it "selective_trip".
            return "breaker_operation_no_protection", "no_protection_record", (
                f"Breaker {opens[0].ref} opened but no protection pickup/trip was "
                "recorded in the SOE — a breaker operation without a protection "
                "record (manual/local open, or the relay events are missing). Cannot "
                "confirm selective protection coordination; check the relay targets."
            )
        return "selective_trip", "selective", (
            f"One protection operation cleared via one breaker ({opens[0].ref}) within "
            "the coordination window — the fault was contained to a single zone "
            "(selective)."
        )
    return "insufficient", "inconclusive", (
        "Protection activity present but no confirmed breaker interruption — "
        "inconclusive; check the breaker-status points in the SOE."
    )


def _affected_refs(events: list[_Event]) -> list[str]:
    """Distinct refs that lost supply (breaker open / lockout / bus undervoltage)."""
    outage_types = {"breaker_open", "lockout", "bus_undervoltage"}
    refs: list[str] = []
    for event in events:
        if event.type in outage_types and event.ref not in refs:
            refs.append(event.ref)
    return refs[:_MAX_LIST]


def _timeline(events: list[_Event]) -> list[dict]:
    return [
        {"ref": event.ref, "type": event.type, "ts": event.ts.isoformat()}
        for event in events[:_MAX_TIMELINE]
    ]


def substation_event_analysis(
    events: list[dict],
    breaker_fail_window_s: float = 0.25,
    backup_margin_s: float = 0.5,
) -> dict:
    """Analyse a substation SOE for protection selectivity / breaker failure / backup.

    Pure, monitor-only structural analysis over ``events`` (no live I/O). Parses
    and time-sorts the SOE, then classifies a ``verdict`` describing whether
    protection coordinated correctly — see the module docstring for the
    protection-engineering intent. Every field is a citation to a timestamped
    event so an agent can attribute each claim.

    Args:
        events: SOE list of ``{ref, timestamp (ISO-8601), type, label?}``.
        breaker_fail_window_s: Breaker-failure timer (default 0.25s).
        backup_margin_s: Backup coordination margin (default 0.5s).

    Returns:
        A dict; see the tool docstring for the full key set.
    """
    parsed, ignored = _normalize(events if isinstance(events, list) else [])
    protections = [event for event in parsed if event.type in _PROTECTION_TYPES]
    trips = [event for event in parsed if event.type == "protection_trip"]
    opens = [event for event in parsed if event.type == "breaker_open"]
    breakers_opened = _distinct_opens(opens)
    verdict, status, detail = _classify_verdict(
        protections,
        trips,
        opens,
        len(breakers_opened),
        max(breaker_fail_window_s, 0.0),
        max(backup_margin_s, 0.0),
    )
    return {
        "events_analyzed": len(parsed),
        "ignored": ignored,
        "verdict": verdict,
        "first_protection": _point(protections[0] if protections else None),
        "first_breaker_open": _point(opens[0] if opens else None),
        "breakers_opened": breakers_opened[:_MAX_LIST],
        "breaker_open_count": len(breakers_opened),
        "affected_refs": _affected_refs(parsed),
        "timeline": _timeline(parsed),
        "coordination": {"status": status, "detail": detail},
        "note": _NOTE,
    }
