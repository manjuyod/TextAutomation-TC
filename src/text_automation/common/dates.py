from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


def weekday_proper(value, tz: str | None = "America/Los_Angeles") -> str:
    """
    Return a proper-cased weekday name (e.g., "Monday").

    - If value is a datetime/date: use strftime("%A"). If datetime is timezone-aware
      and a timezone name is provided, convert via astimezone before formatting.
      If datetime is naive, format directly to avoid altering semantics.
    - If value is a string: trim and capitalize the first letter.
    - Otherwise: raise TypeError.
    """
    if isinstance(value, datetime):
        dt = value
        # Only convert if aware; avoid altering naive datetimes' semantics
        if dt.tzinfo is not None and tz:
            try:
                dt = dt.astimezone(ZoneInfo(tz))
            except Exception:
                # Fallback: keep as-is if timezone conversion fails
                pass
        return dt.strftime("%A")
    if isinstance(value, date):
        return value.strftime("%A")
    if isinstance(value, str):
        return value.strip().capitalize()
    raise TypeError(f"Unsupported type for weekday_proper: {type(value)!r}")

