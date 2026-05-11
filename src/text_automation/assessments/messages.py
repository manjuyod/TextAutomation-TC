from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import requests
from urllib.parse import quote_plus

from ..config import load_config
from ..common.dates import weekday_proper
from ..direct_inquiry.business_hours import localize_timestamp
# from ..accounts.quo import send_payload as send_to_quo


# QUO_FRANCHISE_IDS = {95}


def _greeting(fid: int) -> str:
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


def _franchise_links(fid: int) -> dict[str, Optional[str]]:
    cfg = load_config()
    for f in cfg.franchises:
        if f.id == fid:
            return {
                "assessment_form": f.assessment_form or None,
                "payment_form": f.payment_form or None,
                "address": f.address or None,
                "assess_group": f.assess_group or None,
                # Build a simple Google Maps link from the address if present
                "map_link": (f"https://maps.google.com/?q={quote_plus(f.address)}" if (f.address or "").strip() else None),
            }
    return {"assessment_form": None, "payment_form": None, "address": None, "assess_group": None, "map_link": None}


def _webhook_for_franchise(fid: int) -> Optional[str]:
    links = _franchise_links(fid)
    group = (links.get("assess_group") or "").lower()
    if group == "vegas":
        return os.getenv("ZapHookAssessGilVeg")
    if group == "cali":
        return os.getenv("ZapHookAssessCali")
    if group == "east_q":
        return None
    # default fallback
    return os.getenv("ZapHookAssessGilVeg") or os.getenv("ZapHookAssessCali")


def generate_message(
    franchise_id: int,
    automation_stage: str,
    parent_first_name: str,
    student_names: str,
    assessment_date: datetime,
    assessment_time_str: str,
) -> str:
    # Greeting and capitalization
    greeting = _greeting(franchise_id)
    parent_name = _capitalize_name(parent_first_name)
    students = _capitalize_name(student_names)

    links = _franchise_links(franchise_id)
    assessment_link = links.get("assessment_form")
    payment_link = links.get("payment_form")
    map_link = links.get("address")

    assessment_day = weekday_proper(assessment_date)
    assessment_date_pretty = assessment_date.strftime("%B %d")
    assessment_date_info = f"{assessment_day}, {assessment_date_pretty} at {assessment_time_str}"

    # Franchise-specific intros
    if franchise_id == 20:
        intro_one = f"""Hi! {parent_name}! It's Katie from Tutoring Club Clovis — we're excited to get started with {students}!
        
Their assessment is set for {assessment_date_info}."""
        
        intro_two =f"""Hi {parent_name}! It's Katie from Tutoring Club Clovis, just confirming your visit with us {assessment_day}.

{students}'s assessment is scheduled for {assessment_time_str}.\n"""
    elif franchise_id == 8:
        
        intro_one = f"""Hi {parent_name}! It's Huy from Tutoring Club — we're excited to get started with {students}!

Their assessment is set for {assessment_date_info}."""
        
        intro_two = f"""Hi {parent_name}! It's Huy from Tutoring Club, just confirming your visit with us {assessment_day}.

Their assessment is set for {assessment_date_info}."""
    
    else:
        intro_one = f"""{greeting} {parent_name},

Thank you for choosing Tutoring Club as a partner in your child's educational journey. We are delighted to support {students}'s academic progress.

Your child's assessment is set for {assessment_date_info}."""

        intro_two = f"""{greeting} {parent_name},

This is Tutoring Club. I'm reaching out to confirm our appointment scheduled for {students} on {assessment_day}, at {assessment_time_str}."""

    # Link blocks
    if franchise_id in (8, 20):
        assessment_block_one = (
            f"If you haven't already, you can fill out our student info form here:\n{assessment_link}\n\n"
            if assessment_link
            else ""
        )
        assessment_block_two = assessment_block_one
    else:
        assessment_block_one = (
            f"For convenience, you may complete our Student Information form with the following link:\n{assessment_link}\n\n"
            if assessment_link
            else ""
        )
        assessment_block_two = (
            f"If you haven't already, you may complete our Student Information form with the following link:\n{assessment_link}\n\n"
            if assessment_link
            else ""
        )

    payment_block_one = (
        f"Also for your convenience, you may pay for the Assessment by clicking on the following link:\n{payment_link}\n\n"
        if payment_link
        else ""
    )
    payment_block_two = (
        f"You may also pay for the Assessment by clicking on the following link:\n{payment_link}\n\n"
        if payment_link
        else ""
    )
    
    if franchise_id in (8, 20):
        map_link_message = f"""{
map_link}
""" if map_link else ""
        
    else:
        map_link_message =f"""For your convenience, please find the location of our center here:
{map_link}
""" if map_link else ""

    # Stage-specific pieces
    # Map link message is part of the link block (Assessment2 only per legacy)

    if franchise_id in (8, 20):
        closing_message_one = (
            "Let me know if you have any questions before then — we're looking forward to meeting you both!"
        )
        closing_message_two = (
            "Looking forward to seeing you both soon! Please reply to confirm or let me know if you have any questions."
        )
    else:
        closing_message_one = (
            "We look forward to creating a personalized academic plan together.\n\n"
            "If you have any questions feel free to reach out. \n\n"
            "Thank You!"
        )
        closing_message_two = "Please text back to confirm your appointment."

    if automation_stage == "Assessment1":
        intro = intro_one.strip()
        links_block = (
            assessment_block_one + payment_block_one + (map_link_message if franchise_id == 20 else "")
        ).strip()
        closing = closing_message_one.strip()
    elif automation_stage == "Assessment2":
        intro = intro_two.strip()
        links_block = (assessment_block_two + payment_block_two + map_link_message).strip()
        closing = closing_message_two.strip()
    else:
        intro = "An unexpected error occurred with the automation stage."
        links_block = ""
        closing = ""

    # Assemble: intro, link block (assessment/payment/map), then closing by itself
    sections = [intro]
    if links_block:
        sections.append(links_block)
    if closing:
        sections.append(closing)
    msg = "\n\n".join(sections)
    return msg.strip()


def send_to_webhook(franchise_id: int, message: str, phone: str) -> bool:
    if int(franchise_id) in (62, 95):
        print({"assessment": {"send": "skipped", "reason": "franchise_gate", "franchise_id": int(franchise_id)}})
        return True

    payload = {"message": message, "AssessmentPhone": phone, "FranchiseID": franchise_id}
    # if int(franchise_id) in QUO_FRANCHISE_IDS:
    #     return send_to_quo(payload)

    url = _webhook_for_franchise(franchise_id)
    if not url:
        print("Assessment webhook URL not set")
        return False
    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"Error sending message to Zapier: {e}")
        return False
