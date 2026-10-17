"""Opening hours, as Google's English text, turned into something the filters can ask.

``places._hours`` stores "Monday: 9 AM-5 PM; Tuesday: 1-11 PM; ...", with "Open 24 hours",
"Closed", several ranges ("9 AM-1 PM, 3-7 PM") and ranges that end after midnight
("6 PM-2 AM"). Times are the business's own local time.
"""
from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
WHOLE_DAY = (0, 24 * 60)
_RANGE = re.compile(r"(\d{1,2})(?::(\d\d))?\s*([AP]M)?\s*-\s*(\d{1,2})(?::(\d\d))?\s*([AP]M)", re.I)


def _minutes(hour: str, minute: str | None, meridiem: str) -> int:
    value = int(hour) % 12 * 60 + int(minute or 0)
    return value + 12 * 60 if meridiem.upper() == "PM" else value


def weekly(text: str) -> dict[int, list[tuple[int, int]]]:
    """Day (0 = Monday) -> open ranges in minutes after midnight; an end past 1440 runs on
    into the next day. Days Google did not list are missing."""
    week: dict[int, list[tuple[int, int]]] = {}
    for part in (text or "").split(";"):
        name, _, times = part.partition(":")
        if name.strip() not in DAYS:
            continue
        day = DAYS.index(name.strip())
        ranges = week.setdefault(day, [])
        if "24 hours" in times.lower():
            ranges.append(WHOLE_DAY)
            continue
        for match in _RANGE.finditer(times):
            h1, m1, mer1, h2, m2, mer2 = match.groups()
            end = _minutes(h2, m2, mer2)
            # "1-11 PM": the start shares the end's AM/PM, unless that would put it after the end
            start = _minutes(h1, m1, mer1 or mer2)
            if not mer1 and start > end:
                start = _minutes(h1, m1, "AM")
            if end <= start:  # "9 AM-12 AM", "6 PM-2 AM": closes after midnight
                end += 24 * 60
            ranges.append((start, end))
    return week


def open_at(text: str, day: int, minute: int) -> bool:
    """Open on ``day`` at ``minute`` past midnight, counting last night's late hours."""
    week = weekly(text)
    if any(start <= minute < end for start, end in week.get(day, [])):
        return True
    yesterday = week.get((day - 1) % 7, [])
    return any(start <= minute + 24 * 60 < end for start, end in yesterday)


def open_now(text: str, timezone: str | None, now: datetime | None = None) -> bool:
    try:
        zone = ZoneInfo(timezone) if timezone else None
    except (ZoneInfoNotFoundError, ValueError):
        zone = None
    local = (now or datetime.now(zone)).astimezone(zone) if zone else (now or datetime.now())
    return open_at(text, local.weekday(), local.hour * 60 + local.minute)


def always_open(text: str) -> bool:
    week = weekly(text)
    return len(week) == 7 and all(WHOLE_DAY in ranges for ranges in week.values())


def open_weekends(text: str) -> bool:
    week = weekly(text)
    return bool(week.get(5) or week.get(6))
