import imaplib
import email
from bs4 import BeautifulSoup
import re

# For testing; consider using environment variables for credentials in production
InquiryGmail = 'inquiryautomation@tutoringclub.com'
InquiryPass = 'nQWoovFH4Wku4gfKkPRp'

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
    """
    Extracts the email body.
    Returns a tuple: (plain_text, raw_html).
    If HTML is present, raw_html is returned so that we can work with it.
    """
    plain_text = None
    raw_html = None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
            except Exception as e:
                print(f"Error decoding part: {e}")
                continue

            if ctype == 'text/plain' and payload and plain_text is None:
                try:
                    plain_text = payload.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"Error decoding text/plain: {e}")
            elif ctype == 'text/html' and payload:
                try:
                    raw_html = payload.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"Error decoding text/html: {e}")
    else:
        ctype = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
        except Exception as e:
            print(f"Error decoding email: {e}")
            return None, None

        if ctype == 'text/plain' and payload:
            plain_text = payload.decode('utf-8', errors='ignore')
        elif ctype == 'text/html' and payload:
            raw_html = payload.decode('utf-8', errors='ignore')
    
    return plain_text, raw_html

def extract_website_url_from_soup(soup):
    """
    Scans the text nodes in the BeautifulSoup object to find a URL that starts with
    the base URL (https://tutoringclub.com/). Returns the first URL found.
    """
    base = "https://tutoringclub.com/"
    for text in soup.stripped_strings:
        if base in text:
            # Find the start index of the URL
            start_index = text.find(base)
            # Assume the URL ends at the next space or end of string.
            end_index = text.find(" ", start_index)
            if end_index == -1:
                end_index = len(text)
            url_candidate = text[start_index:end_index]
            # Optional: If you want to extract only the first directory, you could do:
            parts = url_candidate.split('/')
            if len(parts) >= 4:
                # parts[3] is the first directory after the base
                return f"{base}{parts[3]}/"
            return url_candidate
    return ""

def parse_email_for_data_from_html(html):
    """
    Parses the raw HTML to extract data from the table.
    Looks for table rows with bgcolor="#EAF2FA" as headings, and assumes
    that the next <tr> holds the corresponding data.
    
    Returns a tuple of data: (ParentString, StudentString, PhoneString, EmailString, GradeString)
    """
    headings_map = {
        "parent": ["parent", "parents", "parent's name", "parents name", "parent name", "your name"],
        "student": ["student", "students", "student's name", "students name", "student name"],
        "phone": ["phone", "phone number"],
        "email": ["email", "email address"],
        "grade": ["grade", "grade level"]
    }

    soup = BeautifulSoup(html, 'html.parser')
    data = {
        "parent": "",
        "student": "",
        "phone": "",
        "email": "",
        "grade": ""
    }
    
    # Find all table rows with the specified heading background color.
    for tr in soup.find_all('tr', attrs={'bgcolor': '#EAF2FA'}):
        heading_text = tr.get_text(separator=" ", strip=True).lower()
        for key, variations in headings_map.items():
            if any(variant in heading_text for variant in variations):
                # Assume the next table row holds the data.
                next_tr = tr.find_next_sibling('tr')
                if next_tr:
                    # Get the text from the next row.
                    data_value = next_tr.get_text(separator=" ", strip=True)
                    data[key] = data_value
                break

    # Optional: Sanitize the extracted data.
    for key in data:
        data[key] = data[key].replace("'", "''")

    return data["parent"], data["student"], data["phone"], data["email"], data["grade"]

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

    # Process the first unread email for testing
    eid, msg = emails[0]
    
    # --- Optional Debugging Block: Print Raw HTML ---
    # Uncomment the following block to print raw, non-parsed HTML content
    """
    print("---- Raw HTML Content ----")
    for part in msg.walk():
        if part.get_content_type() == 'text/html':
            try:
                html_payload = part.get_payload(decode=True)
                if html_payload:
                    raw_html = html_payload.decode('utf-8', errors='ignore')
                    print(raw_html)
            except Exception as e:
                print(f"Error decoding HTML part: {e}")
    print("---- End of Raw HTML ----")
    """

    # Extract both plain text and raw HTML versions.
    plain_text, raw_html = extract_email_body(msg)
    
    if not raw_html:
        print("No HTML part found in email.")
        mail.close()
        mail.logout()
        return
    
    # Create a BeautifulSoup object from the raw HTML.
    soup = BeautifulSoup(raw_html, 'html.parser')
    
    # Grab the website URL using the dedicated function.
    WebsiteString = extract_website_url_from_soup(soup)
    
    # Parse the rest of the data from the HTML.
    ParentString, StudentString, PhoneString, EmailString, GradeString = parse_email_for_data_from_html(raw_html)
    
    print("Parsed Data:")
    print("Extracted Website URL:", WebsiteString)
    print("ParentString:", ParentString)
    print("StudentString:", StudentString)
    print("PhoneString:", PhoneString)
    print("EmailString:", EmailString)
    print("GradeString:", GradeString)
    
    mail.close()
    mail.logout()

if __name__ == "__main__":
    main()
    