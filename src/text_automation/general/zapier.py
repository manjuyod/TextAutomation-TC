from __future__ import annotations

import os
import requests
from datetime import datetime, timezone

from ..config import load_config
from ..direct_inquiry.utils import format_grade_phrase
from ..direct_inquiry.business_hours import localize_timestamp
from ..direct_inquiry.parser import extract_sent_utc  # optional reference if needed


WINTER_BREAK_START_MONTH = 12
WINTER_BREAK_START_DAY = 19
WINTER_BREAK_END_MONTH = 1
WINTER_BREAK_END_DAY = 4


def _get_local_now(franchise_id: int):
    now_utc = datetime.now(timezone.utc)
    return localize_timestamp(now_utc, franchise_id)


def _format_greeting(local_now) -> str:
    # Greeting based on local current hour for the franchise
    hour = local_now.hour if local_now else 12
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"


def _is_on_winter_break(franchise_id: int, local_now) -> bool:
    if not local_now:
        return False

    cfg = load_config()
    di = cfg.direct_inquiry
    vegas_ids = di.vegas_ids if (di and di.vegas_ids) else (6, 11, 15, 16, 60)
    if franchise_id not in vegas_ids:
        return False

    month = local_now.month
    day = local_now.day

    if month == WINTER_BREAK_START_MONTH and day >= WINTER_BREAK_START_DAY:
        return True
    if month == WINTER_BREAK_END_MONTH and day <= WINTER_BREAK_END_DAY:
        return True

    return False


def _capitalize_name(name: str) -> str:
    return " ".join(w.capitalize() for w in (name or "").split())


def send_direct_inquiry(
    parent_first_name: str,
    student_first_name: str,
    phone: str,
    franchise_id: int,
    grade_string: str,
) -> None:
    webhook = os.getenv("ZapHookDirectInquiry")
    if not webhook:
        print("Zapier webhook URL is not set (ZapHookDirectInquiry)")
        return

    local_now = _get_local_now(franchise_id)
    parent_first_name = _capitalize_name(parent_first_name)
    student_first_name = _capitalize_name(student_first_name)
    grade_phrase = format_grade_phrase(grade_string)
    greeting = _format_greeting(local_now)
    winter_break_note = ""
    if _is_on_winter_break(franchise_id, local_now):
        winter_break_note = "We're out for winter break now, but we'll be back on the 5th.\n\n"

    if franchise_id in (57, 103):
        message = (
            f"{greeting} {parent_first_name}, from Tutoring Club!\n\n"
            "Thank you for filling out our contact request form.\n\n"
            "We are available Monday through Thursday From 10 AM to 7 PM, and Saturday From 10 AM to 2 PM.\n\n"
            f"Please let us know a couple of convenient times for a 15-minute phone call to discuss {student_first_name}'s educational needs, our hours of operation, tuition options, and how Tutoring Club can best help your {grade_phrase}. We'll confirm once we receive your availability.\n\n"
            f"{winter_break_note}"
            "Looking forward to speaking with you!"
        )
    elif franchise_id == 20:
        message = (
            f"{greeting} {parent_first_name}, from Tutoring Club!\n\n"
            "Thank you for filling out our contact request form.\n\n"
            "We are available Monday through Thursday from 11 AM to 8 PM.\n\n"
            f"Please let us know a couple of convenient times for a 15-minute phone call to discuss {student_first_name}'s educational needs, our hours of operation, tuition options, and how Tutoring Club can best help your {grade_phrase}. We'll confirm once we receive your availability.\n\n"
            f"{winter_break_note}"
            "Looking forward to speaking with you!"
        )
    else:
        message = (
            f"{greeting} {parent_first_name}, from Tutoring Club!\n\n"
            "Thank you for filling out our contact request form.\n\n"
            f"Please let us know a couple of convenient times for a 15-minute phone call to discuss {student_first_name}'s educational needs, our hours of operation, tuition options, and how Tutoring Club can best help your {grade_phrase}. We'll confirm once we receive your availability.\n\n"
            f"{winter_break_note}"
            "Looking forward to speaking with you!"
        )

    payload = {"message": message, "AssessmentPhone": phone, "FranchiseID": franchise_id}
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error sending message to Zapier: {e}")
