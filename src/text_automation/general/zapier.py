from __future__ import annotations

import os
import requests

from ..config import load_config
from ..direct_inquiry.processor import _format_grade_phrase  # reuse
from ..direct_inquiry.business_hours import localize_timestamp
from ..direct_inquiry.parser import extract_sent_utc  # optional reference if needed


def _format_greeting(franchise_id: int) -> str:
    # Greeting based on local current hour for the franchise
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    local_now = localize_timestamp(now_utc, franchise_id)
    hour = local_now.hour if local_now else 12
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"


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

    parent_first_name = _capitalize_name(parent_first_name)
    student_first_name = _capitalize_name(student_first_name)
    grade_phrase = _format_grade_phrase(grade_string)
    greeting = _format_greeting(franchise_id)

    if franchise_id == 57:
        message = (
            f"{greeting} {parent_first_name}, from Tutoring Club!\n\n"
            "Thank you for filling out our contact request form.\n\n"
            "We are available Monday through Thursday From 10 AM to 7 PM, and Saturday From 10 AM to 2 PM.\n\n"
            f"Please let us know a couple of convenient times for a 15-minute phone call to discuss {student_first_name}'s educational needs, our hours of operation, tuition options, and how Tutoring Club can best help your {grade_phrase}. We'll confirm once we receive your availability.\n\n"
            "Looking forward to speaking with you!"
        )
    else:
        message = (
            f"{greeting} {parent_first_name}, from Tutoring Club!\n\n"
            "Thank you for filling out our contact request form.\n\n"
            f"Please let us know a couple of convenient times for a 15-minute phone call to discuss {student_first_name}'s educational needs, our hours of operation, tuition options, and how Tutoring Club can best help your {grade_phrase}. We'll confirm once we receive your availability.\n\n"
            "Looking forward to speaking with you!"
        )

    payload = {"message": message, "AssessmentPhone": phone, "FranchiseID": franchise_id}
    try:
        resp = requests.post(webhook, json=payload, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"Error sending message to Zapier: {e}")

