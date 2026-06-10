from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
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
SERVICE_ACCOUNT_REQUIRED_FIELDS = ("type", "client_email", "private_key", "token_uri")


@dataclass(frozen=True)
class InlineImage:
    content_id: str
    filename: str
    content_type: str
    data: bytes


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
    html_body: str | None = None,
    inline_images: Sequence[InlineImage] | None = None,
) -> str:
    sender = _required_text(sender_email, "sender_email")
    to_recipients = _normalize_recipients(recipients)
    related_images = tuple(inline_images or ())
    if related_images and html_body is None:
        raise ValueError("html_body is required when inline_images are provided")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to_recipients)
    msg["Subject"] = str(subject or "")
    msg.set_content(str(body or ""))
    if html_body is not None:
        msg.add_alternative(str(html_body or ""), subtype="html")
        html_part = msg.get_payload()[-1]
        for image in related_images:
            maintype, subtype = _split_content_type(image.content_type)
            html_part.add_related(
                image.data,
                maintype=maintype,
                subtype=subtype,
                cid=f"<{_clean_content_id(image.content_id)}>",
                filename=image.filename,
                disposition="inline",
            )
    return base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")


def send_email(
    *,
    sender_email: str,
    recipients: Sequence[str],
    subject: str,
    body: str,
    html_body: str | None = None,
    inline_images: Sequence[InlineImage] | None = None,
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
        html_body=html_body,
        inline_images=inline_images,
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


def _normalize_recipients(recipients: Sequence[str]) -> list[str]:
    normalized = [str(recipient).strip() for recipient in recipients if str(recipient).strip()]
    if not normalized:
        raise ValueError("recipients must include at least one email address")
    return normalized


def _split_content_type(content_type: str) -> tuple[str, str]:
    maintype, sep, subtype = str(content_type or "").partition("/")
    if not sep or not maintype or not subtype:
        raise ValueError(f"Invalid inline image content_type: {content_type}")
    return maintype, subtype


def _clean_content_id(content_id: str) -> str:
    text = _required_text(content_id, "content_id")
    return text.strip("<>")


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text
