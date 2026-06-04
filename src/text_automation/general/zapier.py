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
DEFAULT_VEGAS_IDS = (6, 11, 15, 16, 60, 110)
DIRECT_INQUIRY2_IDS = (49, 110)


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
    vegas_ids = di.vegas_ids if (di and di.vegas_ids) else DEFAULT_VEGAS_IDS
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


def _franchise_name(franchise_id: int) -> str:
    cfg = load_config()
    return next((f.name for f in cfg.franchises if f.id == int(franchise_id)), "")


def _is_vegas_center(franchise_id: int) -> bool:
    cfg = load_config()
    di = cfg.direct_inquiry
    vegas_ids = di.vegas_ids if (di and di.vegas_ids) else DEFAULT_VEGAS_IDS
    return franchise_id in vegas_ids


def send_direct_inquiry(
    parent_first_name: str,
    student_first_name: str,
    phone: str,
    franchise_id: int,
    grade_string: str,
) -> bool:
    webhook_env = "ZapHookDirectInquiry2" if int(franchise_id) in DIRECT_INQUIRY2_IDS else "ZapHookDirectInquiry"
    webhook = os.getenv(webhook_env)
    if not webhook and webhook_env != "ZapHookDirectInquiry":
        webhook = os.getenv("ZapHookDirectInquiry")
    if not webhook:
        print(f"Zapier webhook URL is not set ({webhook_env})")
        return False

    local_now = _get_local_now(franchise_id)
    parent_first_name = _capitalize_name(parent_first_name)
    student_first_name = _capitalize_name(student_first_name)
    grade_phrase = format_grade_phrase(grade_string)
    greeting = _format_greeting(local_now)
    winter_break_note = ""
    if _is_on_winter_break(franchise_id, local_now):
        winter_break_note = "We're out for winter break now, but we'll be back on the 5th.\n\n"

    if franchise_id in (62, 95):
        message = (
            f"Hi {parent_first_name}! This is Michele Tanner from Tutoring Club 😊\n"
            "Thanks so much for reaching out about your student! I just sent you an email — "
            "check it for a link to book a quick 15-min call with me so we can figure out "
            "the best next step for your child.\n"
            "Feel free to text me here anytime with questions. Can't wait to connect!"
        )
    elif franchise_id in (57, 103):
        franchise_name = _franchise_name(franchise_id) or "Gilbert"
        message = (
            f"Hi, {parent_first_name},\n\n"
            f"This is Daniel from Tutoring Club of {franchise_name}. Thanks for reaching out about tutoring for {student_first_name}! "
            f"We begin with a personalized learning plan so we can focus on the skills {student_first_name} needs most and build academic confidence. "
            f"Our next step is a quick 15-minute call to discuss {student_first_name}'s academic needs, our enrollment process, scheduling, and tuition options.\n\n"
            "Please provide a few times that are most convenient for this phone call. "
            "We are available Monday-Thursday 10AM-6PM. "
            "We look forward to connecting with you soon. Have a great day."
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
    elif _is_vegas_center(franchise_id):
        franchise_name = _franchise_name(franchise_id)
        center_greeting = f"{greeting} {parent_first_name}, from Tutoring Club!\n\n"
        if franchise_name:
            center_greeting = (
                f"{greeting} {parent_first_name}, from Tutoring Club of {franchise_name}!\n\n"
            )

        message = (
            center_greeting
            + "Thank you for filling out our contact request form.\n\n"
            + f"We begin with a personalized learning plan so we can focus on the skills {student_first_name} needs most and build academic confidence. "
            + f"Our next step is a quick 15-minute call to discuss {student_first_name}'s academic needs, our enrollment process, scheduling, and tuition options.\n\n"
            + "Please provide a few times that are most convenient for this phone call. "
            + "We are available Monday-Thursday 10AM-6PM. "
            + f"{winter_break_note}"
            + "Looking forward to speaking with you!"
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
        return True
    except Exception as e:
        print(f"Error sending message to Zapier: {e}")
        return False
