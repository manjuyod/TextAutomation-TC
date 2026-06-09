from __future__ import annotations

import base64
import json
import os
from email.message import EmailMessage
from typing import Mapping, Sequence

from google.oauth2 import service_account
from googleapiclient.discovery import build

from ...config import load_config


DWD_ENV_PART_1 = "sysadmin_gmail_send_DWD_1"
DWD_ENV_PART_2 = "sysadmin_gmail_send_DWD_2"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
DEFAULT_SMOKE_FRANCHISE_IDS = (62, 95)
DEFAULT_SMOKE_RECIPIENT = "bmillares@tutoringclub.com"
DEFAULT_SMOKE_SUBJECT = "Bruh"
DEFAULT_SMOKE_BODY = "bruh"
DIRECT_INQUIRY_SUBJECT = "Thanks for contacting tutoring club!"
SERVICE_ACCOUNT_REQUIRED_FIELDS = ("type", "client_email", "private_key", "token_uri")


def service_account_info_from_env(env: Mapping[str, str] | None = None) -> dict:
    values = env if env is not None else os.environ
    part_1 = values.get(DWD_ENV_PART_1)
    part_2 = values.get(DWD_ENV_PART_2)
    if not part_1 or not part_2:
        raise RuntimeError(f"Missing Gmail DWD service account env vars: {DWD_ENV_PART_1}, {DWD_ENV_PART_2}")

    info = _load_combined_service_account_info(part_1, part_2)

    if not isinstance(info, dict):
        raise RuntimeError("Gmail DWD service account env vars must combine to a JSON object")

    missing = [field for field in SERVICE_ACCOUNT_REQUIRED_FIELDS if not info.get(field)]
    if missing:
        raise RuntimeError(f"Gmail DWD service account JSON is missing required fields: {', '.join(missing)}")
    return info


def _load_combined_service_account_info(part_1: str, part_2: str) -> dict:
    combined = f"{part_1}{part_2}"
    try:
        info = json.loads(combined)
    except json.JSONDecodeError as concat_error:
        try:
            shard_1 = json.loads(part_1)
            shard_2 = json.loads(part_2)
        except json.JSONDecodeError as shard_error:
            raise RuntimeError("Gmail DWD service account env vars must combine to valid JSON") from shard_error
        if not isinstance(shard_1, dict) or not isinstance(shard_2, dict):
            raise RuntimeError("Gmail DWD service account env vars must combine to a JSON object") from concat_error
        return {**shard_1, **shard_2}
    if not isinstance(info, dict):
        raise RuntimeError("Gmail DWD service account env vars must combine to a JSON object")
    return info


def delegated_credentials_for_sender(sender_email: str, *, service_account_info: dict | None = None):
    sender = _required_text(sender_email, "sender_email")
    info = service_account_info if service_account_info is not None else service_account_info_from_env()
    credentials = service_account.Credentials.from_service_account_info(
        info,
        scopes=[GMAIL_SEND_SCOPE],
    )
    return credentials.with_subject(sender)


def build_raw_message(
    *,
    sender_email: str,
    recipients: Sequence[str],
    subject: str,
    body: str,
) -> str:
    sender = _required_text(sender_email, "sender_email")
    to_recipients = _normalize_recipients(recipients)

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to_recipients)
    msg["Subject"] = str(subject or "")
    msg.set_content(str(body or ""))
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def send_email(
    *,
    sender_email: str,
    recipients: Sequence[str],
    subject: str,
    body: str,
) -> dict:
    service_account_info = service_account_info_from_env()
    credentials = delegated_credentials_for_sender(
        sender_email,
        service_account_info=service_account_info,
    )
    raw_message = build_raw_message(
        sender_email=sender_email,
        recipients=recipients,
        subject=subject,
        body=body,
    )
    service = build("gmail", "v1", credentials=credentials)
    result = service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
    return dict(result or {})


def send_jacksonville_hodges_smoke(
    *,
    to: str = DEFAULT_SMOKE_RECIPIENT,
    subject: str = DEFAULT_SMOKE_SUBJECT,
    body: str = DEFAULT_SMOKE_BODY,
    franchise_ids: Sequence[int] | None = None,
) -> list[dict]:
    target_ids = tuple(int(fid) for fid in (franchise_ids or DEFAULT_SMOKE_FRANCHISE_IDS))
    franchises = {int(f.id): f for f in load_config().franchises}
    results: list[dict] = []

    for franchise_id in target_ids:
        franchise = franchises.get(franchise_id)
        if franchise is None or not franchise.email:
            raise RuntimeError(f"No configured sender email found for franchise {franchise_id}")
        result = send_email(
            sender_email=franchise.email,
            recipients=[to],
            subject=subject,
            body=body,
        )
        results.append(
            {
                "franchise_id": franchise_id,
                "sender_email": franchise.email,
                "result": result,
            }
        )
    return results


def build_jacksonville_hodges_direct_inquiry_body(
    *,
    parent_first_name: str,
    student_first_name: str,
    booking_url: str = "",
) -> str:
    parent_first = _capitalize_name(_required_text(parent_first_name, "parent_first_name"))
    student_reference = _capitalize_name(str(student_first_name or "").strip()) or "your student"
    booking_url = str(booking_url or "").strip()

    if booking_url:
        return (
            f"Hi {parent_first},\n\n"
            f"Thanks so much for reaching out to Tutoring Club about {student_reference}! "
            "Please use the link below to book a quick 15-minute call with me so we can figure out the best next step for your child.\n\n"
            f"{booking_url}\n\n"
            "Feel free to reply to this email with any questions.\n\n"
            "Talk soon,\n"
            "Michele Tanner\n"
            "Tutoring Club"
        )

    return (
        f"Hi {parent_first},\n\n"
        f"Thanks so much for reaching out to Tutoring Club about {student_reference}! "
        "I'm looking forward to learning more about what support would be most helpful.\n\n"
        "Please reply with a few times that work for a quick 15-minute call, and I'll confirm a time with you.\n\n"
        "Talk soon,\n"
        "Michele Tanner\n"
        "Tutoring Club"
    )


def send_jacksonville_hodges_direct_inquiry_email(
    *,
    parent_first_name: str,
    student_first_name: str,
    recipient_email: str,
    franchise_id: int,
) -> dict:
    franchise_id = int(franchise_id)
    recipient = _required_text(recipient_email, "recipient_email")
    franchises = {int(f.id): f for f in load_config().franchises}
    franchise = franchises.get(franchise_id)
    if franchise is None or not franchise.email:
        raise RuntimeError(f"No configured sender email found for franchise {franchise_id}")

    body = build_jacksonville_hodges_direct_inquiry_body(
        parent_first_name=parent_first_name,
        student_first_name=student_first_name,
        booking_url=getattr(franchise, "direct_inquiry_booking_url", ""),
    )
    result = send_email(
        sender_email=franchise.email,
        recipients=[recipient],
        subject=DIRECT_INQUIRY_SUBJECT,
        body=body,
    )
    return {
        "franchise_id": franchise_id,
        "sender_email": franchise.email,
        "recipient_email": recipient,
        "result": result,
    }


def _normalize_recipients(recipients: Sequence[str]) -> list[str]:
    normalized = [str(recipient).strip() for recipient in recipients if str(recipient).strip()]
    if not normalized:
        raise ValueError("recipients must include at least one email address")
    return normalized


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _capitalize_name(name: str) -> str:
    return " ".join(part.capitalize() for part in str(name or "").split())
