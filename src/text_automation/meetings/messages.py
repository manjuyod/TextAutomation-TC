from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import requests

from ..config import load_config
from ..direct_inquiry.business_hours import localize_timestamp


def _greeting(fid: int) -> str:
    # Use the current local time for the franchise to determine greeting
    now_utc = datetime.now(timezone.utc)
    local = localize_timestamp(now_utc, fid)
    h = local.hour if local else 12
    if 5 <= h < 12:
        return "Good morning"
    if 12 <= h < 17:
        return "Good afternoon"
    return "Good evening"


def _capitalize_name(name: str) -> str:
    return " ".join(w if w.lower() == "and" else w.capitalize() for w in (name or "").split())


def _assess_group(fid: int) -> str:
    cfg = load_config()
    for f in cfg.franchises:
        if f.id == fid:
            return (f.assess_group or "").lower()
    return ""


def _webhook_for_franchise(fid: int) -> Optional[str]:
    grp = _assess_group(fid)
    if grp == "vegas":
        return os.getenv("ZapHookMeetingGilVeg")
    if grp == "cali":
        return os.getenv("ZapHookMeetingCali")
    return os.getenv("ZapHookMeetingGilVeg") or os.getenv("ZapHookMeetingCali")


def generate_message(
    franchise_id: int,
    meeting_dt: datetime,
    student_names: str,
    guardian_default: str,
    primary_parent: str | None = None,
    secondary_parent: str | None = None,
    grade: str | None = None,
    mode: str = "scheduled",
) -> str:
    greeting = _greeting(franchise_id)
    guardian_default = _capitalize_name(guardian_default)
    primary_parent = _capitalize_name(primary_parent or "") or None
    secondary_parent = _capitalize_name(secondary_parent or "") or None
    students = _capitalize_name(student_names)
    when = meeting_dt.strftime("%A, %B %d at %I:%M %p")

    # Laptop/Chromebook note when grade not in valid set
    if franchise_id == 20:
        valid_grades = {"Pre-K", "K", "1st", "2nd", "3rd", "4th", "5th", "6th"}
    else:
        valid_grades = {"Pre-K", "K", "1st", "2nd", "3rd", "4th", "5th"}
    grade_valid = bool(grade) and str(grade) in valid_grades
    if not grade_valid:
        if franchise_id == 20:
            laptop_message = (
                f"Be sure {students} know their grade portal login for the meeting."
            )
        else:
            laptop_message = (
                f"Please have {students} bring their Chromebook or laptop for the meeting, as we will log into their school portals."
            )
    else:
        laptop_message = ""

    closing_message_one = "Thank you!"
    closing_message_two = "Please text back to confirm your appointment. Thank you!"

    if mode != "morning":
        # Meeting1
        if franchise_id not in (8, 20):
            if primary_parent and secondary_parent:
                message_template = f"""{greeting} {primary_parent},

This is Tutoring Club. Thank you for allowing us to assess {students}. I have scheduled our enrollment meeting with you {secondary_parent} on {when} to discuss {students}’s academic plan, our different tuition options, and scheduling. If you have any questions, please feel free to contact me.

{closing_message_one}
"""
            else:
                message_template = f"""{greeting} {guardian_default},

This is Tutoring Club. Thank you for allowing us to assess {students}. I have scheduled our enrollment meeting with you on {when} to discuss {students}’s academic plan, our different tuition options, and scheduling. If you have any questions, please feel free to contact me.

{closing_message_one}
"""
        elif franchise_id == 20:
            message_template = f"""
Hi {guardian_default}! It's Katie from Tutoring Club Clovis.

Thank you for bringing {students} in for their assessment! I've scheduled a follow-up meeting with you on {when} to go over their results, create an academic plan, and walk through next steps.
Let me know if you have any questions in the meantime — looking forward to connecting soon!
"""
        elif franchise_id == 8:
            message_template = f"""
Hi {guardian_default}! It's Huy from Tutoring Club.

Thank you for bringing {students} in for their assessment! I've scheduled a follow-up meeting with you on {when} to go over their results, create an academic plan, and walk through next steps.
Let me know if you have any questions in the meantime — looking forward to connecting soon!
"""
        else:
            message_template = f"""
Hi {guardian_default}! It's Tutoring Club.

Thank you for bringing {students} in for their assessment! I've scheduled a follow-up meeting with you on {when} to go over their results, create an academic plan, and walk through next steps.
Let me know if you have any questions in the meantime — looking forward to connecting soon!
"""
        return message_template.strip()

    # Meeting2 (morning confirmations)
    relative_day = "today"
    meeting_time = meeting_dt.strftime("%I:%M %p")
    if primary_parent and secondary_parent:
        parts = f"""{greeting} {primary_parent},

This is Tutoring Club, and I would like to confirm our appointment {relative_day} at {meeting_time} with you {secondary_parent} to discuss {students}’s academic plan, our different tuition options, and scheduling."""
    else:
        parts =f"""{greeting} {guardian_default},

This is Tutoring Club, and I would like to confirm our appointment {relative_day} at {meeting_time} with you to discuss {students}’s academic plan, our different tuition options, and scheduling."""

    # Ensure parts is a list even if built as a raw string above
    if isinstance(parts, str):
        parts = [parts]
    if laptop_message:
        parts.append(laptop_message)
    parts.append(closing_message_two)

    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def send_to_webhook(franchise_id: int, message: str, phone: str) -> bool:
    url = _webhook_for_franchise(franchise_id)
    if not url:
        print("Meeting webhook URL not set")
        return False
    payload = {"message": message, "AssessmentPhone": phone, "FranchiseID": franchise_id}
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending meeting message to Zapier: {e}")
        return False
