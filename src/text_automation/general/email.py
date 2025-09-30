from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Sequence


def _creds() -> tuple[str | None, str | None]:
    return os.getenv("AutoEmAd"), os.getenv("AutoEmPs")


def send_text(subject: str, recipients: Sequence[str], body: str) -> None:
    sender, password = _creds()
    if not sender or not password:
        raise RuntimeError("Missing AutoEmAd/AutoEmPs environment variables for email sending")
    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = subject
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)


def send_with_attachments(
    subject: str,
    recipients: Sequence[str],
    body: str,
    base_path: str | Path,
    attachments: Iterable[str | Path],
) -> None:
    sender, password = _creds()
    if not sender or not password:
        raise RuntimeError("Missing AutoEmAd/AutoEmPs environment variables for email sending")
    msg = EmailMessage()
    msg["From"] = sender
    msg["Subject"] = subject
    msg["To"] = ", ".join(recipients)
    msg.set_content(body)
    base = Path(base_path)
    for file in attachments:
        file_path = base / file
        with open(file_path, "rb") as f:
            file_data = f.read()
        msg.add_attachment(
            file_data,
            maintype="application",
            subtype="octet-stream",
            filename=file_path.name,
        )
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(sender, password)
        smtp.send_message(msg)

