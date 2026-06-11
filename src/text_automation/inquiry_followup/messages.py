from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ..config import load_config


JUNE_ADDENDUM = "We're offering free assessments for the rest of June."


def _title_case(value: str) -> str:
    return " ".join(
        (w if w.lower() == "and" else w.capitalize()) for w in (value or "").split() if w
    )


def _franchise_timezone(franchise_id: int) -> str:
    cfg = load_config()
    for f in cfg.franchises:
        if f.id == int(franchise_id):
            return f.timezone or "America/Los_Angeles"
    return "America/Los_Angeles"


def _greeting(franchise_id: int, contact: str = "", now_utc: datetime | None = None) -> str:
    now = now_utc or datetime.now(timezone.utc)
    try:
        local_now = now.astimezone(ZoneInfo(_franchise_timezone(franchise_id)))
        hour = local_now.hour
    except Exception:
        hour = datetime.now().hour

    suffix = f" {contact}," if contact else ","
    if 5 <= hour < 12:
        return f"Good morning{suffix}"
    if 12 <= hour < 17:
        return f"Good afternoon{suffix}"
    return f"Good evening{suffix}"


def _is_june(franchise_id: int | None, now_utc: datetime | None = None) -> bool:
    now = now_utc or datetime.now(timezone.utc)
    if franchise_id is not None:
        try:
            return now.astimezone(ZoneInfo(_franchise_timezone(franchise_id))).month == 6
        except Exception:
            pass

    try:
        return now.astimezone().month == 6
    except Exception:
        return datetime.now().month == 6


def _franchise_location(franchise_id: int) -> str:
    cfg = load_config()
    for f in cfg.franchises:
        if f.id == int(franchise_id):
            name = (f.name or "").strip()
            break
    else:
        name = ""
    if not name:
        return "Tutoring Club"
    if "Tutoring Club of" in name:
        return name
    return f"Tutoring Club of {name}"


def build_message(
    contact_first: str | None,
    student_first: str | None,
    franchise_id: int | None = None,
    *,
    summer: bool = False,
    now_utc: datetime | None = None,
) -> str:
    contact = (contact_first or "").strip()
    student = (student_first or "").strip()

    contact_name = _title_case(contact)
    student_name = _title_case(student)

    phrase = f" for {student_name}" if student_name else ""
    salutation = f"Hey {contact_name}," if contact_name else "Hello,"
    location = _franchise_location(franchise_id or 0)
    question = (
        f"{salutation} This is the {location}. We haven't spoken in a while. "
        f"Would you still be interested in some tutoring{phrase}? "
    )
    closing = "If this is something that interests you, I'd be happy to have a conversation."
    base = f"{question}{closing}"

    if summer and franchise_id is not None:
        location = _franchise_location(franchise_id)
        greeting = _greeting(franchise_id, contact_name, now_utc)
        return (
            f"{greeting}\n\n"
            f"This is the {location}. You previously reached out to us about tutoring, and since summer is almost here, we wanted to reconnect.\n\n"
            "We're currently offering a complimentary assessment if you schedule within the next two weeks. Summer is a great time to help students fill in learning gaps, "
            "preview next year's courses, or tackle SAT prep. It's also a fantastic way to keep their minds active and engaged (and give them a productive break from screen time!).\n\n"
            "Let me know if you'd like to grab a spot on our calendar. Hope you're having a great week!"
        )

    if not summer and _is_june(franchise_id, now_utc):
        return f"{question}{JUNE_ADDENDUM} {closing}"

    return base
