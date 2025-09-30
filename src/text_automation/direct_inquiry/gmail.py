from __future__ import annotations

import base64
import email
import json
from pathlib import Path
from typing import Iterable, List, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from ..config import load_config
from ..general.telegram import send_message, LOG_BOT, LOG_CHAT


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]


def _token_path() -> Path:
    cfg = load_config()
    assert cfg.direct_inquiry and cfg.direct_inquiry.token_path
    return Path(cfg.direct_inquiry.token_path)


def get_gmail_service():
    token_path = _token_path()
    creds = None
    try:
        if token_path.exists():
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                secret_json = json.loads(_get_client_secret_json())
                flow = InstalledAppFlow.from_client_config(secret_json, SCOPES)
                creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
            token_path.parent.mkdir(parents=True, exist_ok=True)
            token_path.write_text(creds.to_json())
    except Exception as e:
        send_message(
            f"Gmail API auth error: {e} - Re-run interactively to regenerate token.json.",
            LOG_BOT,
            LOG_CHAT,
        )
        raise
    return build("gmail", "v1", credentials=creds)


def _get_client_secret_json() -> str:
    # Expect env var InquiryAutoAPI to contain the JSON string
    import os

    js = os.environ.get("InquiryAutoAPI")
    if not js:
        raise RuntimeError("Missing InquiryAutoAPI environment variable with Gmail OAuth client JSON")
    return js


def get_unread_messages(service, max_results: int = 50) -> List[Tuple[str, email.message.Message]]:
    resp = service.users().messages().list(userId="me", q="is:unread", maxResults=max_results).execute()
    messages = []
    for m in resp.get("messages", []):
        raw = service.users().messages().get(userId="me", id=m["id"], format="raw").execute()["raw"]
        msg_bytes = base64.urlsafe_b64decode(raw.encode("ascii"))
        msg = email.message_from_bytes(msg_bytes)
        messages.append((m["id"], msg))
    return messages


def mark_as_read(service, msg_id: str) -> None:
    service.users().messages().modify(userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}).execute()


def extract_email_body(msg: email.message.Message) -> tuple[str | None, str | None]:
    plain_text, raw_html = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            if ctype == "text/plain" and plain_text is None:
                plain_text = payload.decode("utf-8", errors="ignore")
            elif ctype == "text/html" and raw_html is None:
                raw_html = payload.decode("utf-8", errors="ignore")
    else:
        ctype = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            if ctype == "text/plain":
                plain_text = payload.decode("utf-8", errors="ignore")
            elif ctype == "text/html":
                raw_html = payload.decode("utf-8", errors="ignore")
    return plain_text, raw_html

