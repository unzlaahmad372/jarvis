"""Calendar tools (Phase 38) — read events from a local ICS file.

Parses RFC 5545 .ics files using the icalendar library.
No cloud connection required — works with any exported calendar file
(Google Calendar, Outlook, Apple Calendar, etc.).

Tools:
  - list_calendar_events: list upcoming events within a date range
  - get_todays_events: shortcut for today's events (morning briefing use case)
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.tools.base import RiskLevel, Tool, ToolResult


def _load_ics(ics_path: str) -> list[dict[str, str]]:
    """Parse an ICS file and return a list of event dicts."""
    try:
        from icalendar import Calendar  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError("icalendar package not installed. Run: pip install icalendar")

    path = Path(ics_path)
    if not path.is_file():
        raise FileNotFoundError(f"ICS file not found: {ics_path}")

    cal = Calendar.from_ical(path.read_bytes())
    events = []
    for component in cal.walk():
        if component.name != "VEVENT":
            continue
        dtstart = component.get("DTSTART")
        dtend = component.get("DTEND")
        start = dtstart.dt if dtstart else None
        end = dtend.dt if dtend else None

        # Normalise to datetime (all-day events use date objects)
        if isinstance(start, date) and not isinstance(start, datetime):
            start = datetime(start.year, start.month, start.day, tzinfo=UTC)
        if isinstance(end, date) and not isinstance(end, datetime):
            end = datetime(end.year, end.month, end.day, tzinfo=UTC)

        events.append({
            "summary": str(component.get("SUMMARY", "")),
            "start": start.isoformat() if start else "",
            "end": end.isoformat() if end else "",
            "location": str(component.get("LOCATION", "")),
            "description": str(component.get("DESCRIPTION", ""))[:500],
        })
    return events


def _filter_events(
    events: list[dict[str, str]],
    from_dt: datetime,
    to_dt: datetime,
) -> list[dict[str, str]]:
    result = []
    for ev in events:
        if not ev["start"]:
            continue
        try:
            start = datetime.fromisoformat(ev["start"])
            if start.tzinfo is None:
                start = start.replace(tzinfo=UTC)
        except ValueError:
            continue
        if from_dt <= start < to_dt:
            result.append(ev)
    return sorted(result, key=lambda e: e["start"])


class ListCalendarEventsTool(Tool):
    """List calendar events from a local ICS file within a date range."""

    def __init__(self, ics_path: str) -> None:
        self._ics_path = ics_path

    @property
    def name(self) -> str:
        return "list_calendar_events"

    @property
    def description(self) -> str:
        return (
            "List upcoming calendar events from the configured ICS file. "
            "Specify from_date and to_date as ISO date strings (YYYY-MM-DD)."
        )

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "from_date": {
                "type": "string",
                "description": "Start date inclusive (YYYY-MM-DD). Defaults to today.",
            },
            "to_date": {
                "type": "string",
                "description": "End date exclusive (YYYY-MM-DD). Defaults to 7 days from today.",
            },
        }

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        today = datetime.now(UTC).date()
        from_str = str(parameters.get("from_date", today.isoformat()))
        to_str = str(parameters.get("to_date", (today + timedelta(days=7)).isoformat()))

        try:
            from_dt = datetime.fromisoformat(from_str).replace(tzinfo=UTC)
            to_dt = datetime.fromisoformat(to_str).replace(tzinfo=UTC)
        except ValueError as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        try:
            all_events = _load_ics(self._ics_path)
        except (FileNotFoundError, RuntimeError) as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        events = _filter_events(all_events, from_dt, to_dt)
        return ToolResult(
            tool_name=self.name,
            success=True,
            output=json.dumps({"from": from_str, "to": to_str, "events": events}),
        )


class GetTodaysEventsTool(Tool):
    """Get today's calendar events — shortcut for morning briefing."""

    def __init__(self, ics_path: str) -> None:
        self._ics_path = ics_path

    @property
    def name(self) -> str:
        return "get_todays_events"

    @property
    def description(self) -> str:
        return "Get all calendar events scheduled for today."

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.READ_ONLY

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {}

    async def execute(self, parameters: dict[str, Any]) -> ToolResult:
        today = datetime.now(UTC).date()
        from_dt = datetime(today.year, today.month, today.day, tzinfo=UTC)
        to_dt = from_dt + timedelta(days=1)

        try:
            all_events = _load_ics(self._ics_path)
        except (FileNotFoundError, RuntimeError) as exc:
            return ToolResult(tool_name=self.name, success=False, output="", error=str(exc))

        events = _filter_events(all_events, from_dt, to_dt)
        return ToolResult(
            tool_name=self.name,
            success=True,
            output=json.dumps({"date": today.isoformat(), "events": events}),
        )
