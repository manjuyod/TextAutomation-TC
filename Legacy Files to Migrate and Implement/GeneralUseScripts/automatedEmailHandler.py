import os
import smtplib
from pathlib import Path
import imghdr
from email.message import EmailMessage

emailAddress = os.environ.get("AutoEmAd")
emailPass = os.environ.get("AutoEmPs")


def emailTextOnly(subj, recipients, emailBody):

    msg = EmailMessage()
    msg["From"] = emailAddress

    msg["Subject"] = subj
    msg["To"] = ", ".join(recipients)
    msg.set_content(emailBody)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:

        smtp.login(emailAddress, emailPass)

        smtp.send_message(msg)


def emailDocumentAttachments(subj, recipients, emailBody, fPath, attachments):

    msg = EmailMessage()
    msg["From"] = emailAddress

    msg["Subject"] = subj
    msg["To"] = ", ".join(recipients)
    msg.set_content(emailBody)

    for file in attachments:
        fileToOpen = Path(fPath) / file
        with open(fileToOpen, "rb") as f:
            file_data = f.read()
            file_name = file

        msg.add_attachment(
            file_data,
            maintype="application",
            subtype="octet-stream",
            filename=file_name,
        )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:

        smtp.login(emailAddress, emailPass)

        smtp.send_message(msg)
