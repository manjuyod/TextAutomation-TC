import imaplib
import email
import re
import os
from bs4 import BeautifulSoup

InquiryGmail = os.getenv('InquiryAutoGmail')
InquiryPass = os.getenv('InquiryAutoPass')  # For testing; consider environment vars later

def get_unread_emails(username, password, imap_server='imap.gmail.com'):
    """Connects to Gmail IMAP and fetches unread emails."""
    try:
        mail = imaplib.IMAP4_SSL(imap_server)
        mail.login(username, password)
        mail.select("INBOX")
        status, data = mail.search(None, '(UNSEEN)')
        if status != 'OK':
            print("Failed to search emails.")
            return [], None
        email_ids = data[0].split()
        emails = []
        for eid in email_ids:
            status, msg_data = mail.fetch(eid, '(RFC822)')
            if status == 'OK':
                raw_email = msg_data[0][1]
                msg = email.message_from_bytes(raw_email)
                emails.append((eid, msg))
        return emails, mail
    except Exception as e:
        print(f"Error connecting or fetching emails: {e}")
        return [], None

def extract_email_body(msg):
    """Extract the text body from an email, trying text/plain first, then falling back to text/html."""
    body = None
    if msg.is_multipart():
        # Iterate through parts to find text/plain or text/html
        html_content = None
        for part in msg.walk():
            ctype = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
            except Exception as e:
                print(f"Error decoding part: {e}")
                continue

            if ctype == 'text/plain' and payload:
                try:
                    body = payload.decode('utf-8', errors='ignore')
                    break  # If we find a plain text part, use it
                except Exception as e:
                    print(f"Error decoding text/plain: {e}")
            elif ctype == 'text/html' and payload and body is None:
                # Keep track of HTML content if no plain text found yet
                try:
                    html_content = payload.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"Error decoding text/html: {e}")

        # If no plain text found, fall back to html
        if not body and html_content:
            soup = BeautifulSoup(html_content, 'html.parser')
            body = soup.get_text(separator='\n')
    else:
        # Not multipart
        ctype = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
        except Exception as e:
            print(f"Error decoding email: {e}")
            return None

        if ctype == 'text/plain' and payload:
            body = payload.decode('utf-8', errors='ignore')
        elif ctype == 'text/html' and payload:
            html_content = payload.decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html_content, 'html.parser')
            body = soup.get_text(separator='\n')

    return body

def main():
    emails, mail = get_unread_emails(InquiryGmail, InquiryPass)

    if not mail:
        print("No connection to mail server.")
        return

    if not emails:
        print("No unread emails found.")
        mail.close()
        mail.logout()
        return

    # Just process the first unread email
    eid, msg = emails[0]
    body = extract_email_body(msg)

    if body:
        print("Extracted Email Body:")
        print(body)
    else:
        print("Email body is empty or could not be extracted.")

    # Close mail connection
    mail.close()
    mail.logout()

if __name__ == "__main__":
    main()
