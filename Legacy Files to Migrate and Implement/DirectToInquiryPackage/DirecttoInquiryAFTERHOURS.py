import datetime
from pathlib import Path
import os
import email
import re
import requests
import base64
import json
from telegramHandler import send_telegram_message, AUTO_BOT, AUTO_CHAT, LOG_BOT, LOG_CHAT
from bs4 import BeautifulSoup
import pandas as pd
from typing import Iterable, Set
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import googleapiclient
from googleapiclient.discovery import build
from email.utils import getaddresses, parsedate_to_datetime

# Franchise info mapping: Adjust or add more if needed
franchise_info = [
    (15, 'North Las Vegas','https://tutoringclub.com/northlasvegasnv/', 'Jessica', 'northlasvegasnv@tutoringclub.com'),
    (60, 'Centennial', 'https://tutoringclub.com/centennialnv/', 'Jessica', 'centennialnv@tutoringclub.com'),
    (11, 'Green Valley', 'https://tutoringclub.com/hendersonnv/', 'Shannon', 'hendersonnv@tutoringclub.com'),
    (6, 'Anthem','https://tutoringclub.com/anthemnv/', 'Shannon', 'anthemnv@tutoringclub.com'),
    (16, 'Rhodes Ranch', 'https://tutoringclub.com/rhodesranchnv/', 'Shannon', 'rhodesranchnv@tutoringclub.com')
]
# ORDER: FranchiseID, FranchiseName, WebString, Director, InboundEmailQUestion

############################################
# Gmail API helper (replaces imaplib usage)#
############################################

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

def get_gmail_service() -> "googleapiclient.discovery.Resource":
    """Authorise (or refresh) and return a Gmail API service resource."""
    TOKEN_PATH = Path(r"C:\Users\Administrator\Desktop\Scripts\reporting-v1\ReportScripts\ZapierAutomation\DirectToInquiryPackage\token.json")
    creds = None
    try:
        if os.path.exists(TOKEN_PATH):                     # cached access/refresh
            creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                secret_json = json.loads(os.environ['InquiryAutoAPI'])
                flow = InstalledAppFlow.from_client_config(secret_json, SCOPES)
                creds = flow.run_local_server(
                    port=0,
                    access_type='offline',
                    prompt='consent'
                )
            TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_PATH.write_text(creds.to_json())
    except Exception as e:
        # Notify on Telegram that auth failed and needs manual re‑run
        err_msg = f"🚨 Gmail API auth error: {e} - Please re‑run interactively to regenerate token.json."
        send_telegram_message(err_msg, AUTO_BOT, AUTO_CHAT)
        # re‑raise so your script sees the failure
        raise
         
    return build('gmail', 'v1', credentials=creds)

def debug_unread(service):
    who = service.users().getProfile(userId='me').execute()['emailAddress']
    print("✓  API authenticated as:", who)

    resp = service.users().messages().list(
        userId='me',
        labelIds=['INBOX'],          # only Inbox
        q='is:unread',               # unread filter
        maxResults=10                # just peek
    ).execute()

    print("✓  API sees", resp.get('resultSizeEstimate', 0), "unread messages")

    for m in resp.get('messages', []):
        print("   ‣ message id", m['id'])

class DummyMail:
    """Provides .close() / .logout() so downstream code is unchanged."""
    def close(self):  pass
    def logout(self): pass

# DB Connection Info (from environment variables)
server = os.getenv('CRMSrvAddress')
username = os.getenv('CRMSrvUs')
password = os.getenv('CRMSrvPs')
database = os.getenv('CRMSrvDb')

connection_string = f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC Driver 17 for SQL Server"
engine = create_engine(connection_string)
Session = sessionmaker(bind=engine)

###_________Time Handling Functions_________###
def get_timezone(franchise_id):
    # Nevada centers use Pacific; Gilbert (57) uses Mountain
    pacific_fids = {6, 11, 15, 16, 60}
    if franchise_id in pacific_fids:
        return 'PST/PDT'
    if franchise_id == 57:
        return 'MST/MDT'
    return 'MST/MDT'  # sensible fallback

def get_timezone_offset(timezone_str):
    timezone_offsets = {
        'MST/MDT': {'standard': -7, 'dst': -6},
        'PST/PDT': {'standard': -8, 'dst': -7},
    }
    return timezone_offsets.get(timezone_str, {'standard': -8, 'dst': -7})

def is_dst(dt, timezone_str):
    # Calculate DST start and end dates for the given year.
    dst_start = datetime.datetime(dt.year, 3, 8)
    dst_end = datetime.datetime(dt.year, 11, 1)
    while dst_start.weekday() != 6:
        dst_start += datetime.timedelta(days=1)
    while dst_end.weekday() != 6:
        dst_end += datetime.timedelta(days=1)
    return dst_start <= dt < dst_end

def get_local_date_time(franchise_id):
    utc_now = datetime.datetime.utcnow()
    timezone_str = get_timezone(franchise_id)
    offset_info = get_timezone_offset(timezone_str)
    if is_dst(utc_now, timezone_str):
        offset = datetime.timedelta(hours=offset_info['dst'])
    else:
        offset = datetime.timedelta(hours=offset_info['standard'])
    local_now = utc_now + offset
    return local_now

def format_greeting(franchise_id):
    local_now = get_local_date_time(franchise_id)
    hour = local_now.hour
    if 5 <= hour < 12:
        return "Good morning"
    elif 12 <= hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"

###_________Grade Handling_________###
def format_grade_phrase(grade):
    grade_dict = {
        'Kindergarten': "Kindergartener",
        '1st Grade': "1st grader",
        '2nd Grade': "2nd grader",
        '3rd Grade': "3rd grader",
        '4th Grade': "4th grader",
        '5th Grade': "5th grader",
        '6th Grade': "6th grader",
        '7th Grade': "7th grader",
        '8th Grade': "8th grader",
        '9th Grade': "9th grader",
        '10th Grade': "10th grader",
        '11th Grade': "11th grader",
        '12th Grade': "12th grader"
    }
    grade_key = (grade or "").strip()
    return grade_dict.get(grade_key, "student")


###_________Email Handling Functions_________###
def get_unread_emails(service):
    """
    Returns a list of (msg_id, email.message.Message) for unread threads.
    """
    resp = service.users().messages().list(
        userId='me', q='is:unread',
        maxResults=50              # tweak as you like
    ).execute()
    msgs = []
    for m in resp.get('messages', []):
        raw = service.users().messages().get(
            userId='me', id=m['id'], format='raw'
        ).execute()['raw']
        msg_bytes = base64.urlsafe_b64decode(raw.encode('ascii'))
        msg = email.message_from_bytes(msg_bytes)
        msgs.append((m['id'], msg))
    return msgs

def mark_as_read(service, msg_id):
    """Remove the UNREAD label (requires gmail.modify scope)."""
    service.users().messages().modify(
        userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}
    ).execute()

def extract_email_body(msg):
    plain_text, raw_html = None, None
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            if ctype == 'text/plain' and plain_text is None:
                plain_text = payload.decode('utf-8', errors='ignore')
            elif ctype == 'text/html' and raw_html is None:
                raw_html = payload.decode('utf-8', errors='ignore')
    else:
        ctype = msg.get_content_type()
        payload = msg.get_payload(decode=True)
        if payload:
            if ctype == 'text/plain':
                plain_text = payload.decode('utf-8', errors='ignore')
            elif ctype == 'text/html':
                raw_html = payload.decode('utf-8', errors='ignore')
    return plain_text, raw_html 

def extract_sent_utc(msg):
    """
    Read RFC 2822 Date header and return a UTC datetime (aware).
    Returns None if missing/invalid.
    """
    try:
        d = msg.get('Date')
        if not d:
            return None
        dt = parsedate_to_datetime(d)  # aware or naive
        if dt is None:
            return None
        # If naive (rare), assume UTC
        if dt.tzinfo is None:
            return dt.replace(tzinfo=datetime.timezone.utc)
        # Convert to UTC
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        return None

def localize_to_franchise(utc_dt, franchise_id):
    """
    Convert a UTC datetime to the franchise's local time using fixed US rules
    already in this file (no external tz libs).
    """
    if utc_dt is None:
        return None
    # convert utc_dt to naive UTC for our arithmetic
    utc_naive = utc_dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    tz_str = get_timezone(franchise_id)
    offsets = get_timezone_offset(tz_str)
    # Decide DST based on local date; first compute a tentative local using standard offset,
    # then re-evaluate DST against that local date.
    tentative_local = utc_naive + datetime.timedelta(hours=offsets['standard'])
    use_dst = is_dst(tentative_local, tz_str)
    offset_hours = offsets['dst'] if use_dst else offsets['standard']
    return utc_naive + datetime.timedelta(hours=offset_hours)

def sent_in_business_window(local_dt):
    """
    Business windows:
      • Mon–Thu: 10:00 to 19:00 inclusive of endpoints
      • Sat:     10:00 to 14:00 inclusive of endpoints
    """
    if local_dt is None:
        return False

    dow = local_dt.weekday()  # Mon=0 ... Sun=6
    t = local_dt.time()

    open_10 = datetime.time(10, 0, 0)
    close_19 = datetime.time(19, 0, 0)
    close_14 = datetime.time(14, 0, 0)

    if 0 <= dow <= 3:  # Mon-Thu
        return (t >= open_10) and (t <= close_19)
    if dow == 5:       # Saturday
        return (t >= open_10) and (t <= close_14)
    return False

def extract_website_url_from_soup(soup):
    """
    Scans the text nodes in the BeautifulSoup object to find a URL that starts with
    the base URL (https://tutoringclub.com/). Returns the first URL found.
    """
    base = "https://tutoringclub.com/"
    for text in soup.stripped_strings:
        if base in text:
            start_index = text.find(base)
            end_index = text.find(" ", start_index)
            if end_index == -1:
                end_index = len(text)
            url_candidate = text[start_index:end_index]
            parts = url_candidate.split('/')
            if len(parts) >= 4:
                # Return only the base and the first subdirectory
                return f"{base}{parts[3]}/"
            return url_candidate
    return ""

def parse_email_for_data_from_html(html):
    """
    Parses the raw HTML to extract data fields from the inquiry table.
    Looks for table rows with bgcolor="#EAF2FA" as headings, then assumes the next row
    contains the corresponding data.
    
    Returns a tuple: (ParentString, StudentString, PhoneString, EmailString, GradeString)
    """
    headings_map = {
        "parent": ["parent", "parents", "parent's name", "parents name", "parent name", "your name"],
        "student": ["student", "students", "student's name", "students name", "student name"],
        "phone": ["phone", "phone number"],
        "email": ["email", "email address"],
        "grade": ["grade", "grade level"]
    }
    soup = BeautifulSoup(html, 'html.parser')
    data = {"parent": "", "student": "", "phone": "", "email": "", "grade": ""}
    for tr in soup.find_all('tr', attrs={'bgcolor': '#EAF2FA'}):
        heading_text = tr.get_text(separator=" ", strip=True).lower()
        for key, variations in headings_map.items():
            if any(variant in heading_text for variant in variations):
                next_tr = tr.find_next_sibling('tr')
                if next_tr:
                    data_value = next_tr.get_text(separator=" ", strip=True)
                    data[key] = data_value
                break
    # Sanitize the extracted strings (escape single quotes)
    for key in data:
        data[key] = data[key].replace("'", "''")
    return data["parent"], data["student"], data["phone"], data["email"], data["grade"]

###_________Utility Functions_________###
def split_name(full_name):
    """Given a full name string, attempt to split it into first and last names."""
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return full_name.strip(), ""
    else:
        return " ".join(parts[:-1]), parts[-1]

def sanitize_name_for_sql(name):
    return name.replace("'", "''")

def get_franchise_id(WebsiteString):
    for fid, fname, wstring, director, _ in franchise_info:
        if wstring.lower() in WebsiteString.lower():
            return fid
    return 1  # Default if not found

def get_director(franchise_id):
    for fid, _, _, director, _ in franchise_info:
        if fid == franchise_id:
            return director
    return "Daniel"  # default if not found

# Fast lookup: recipient email -> FranchiseID
FID_BY_ADDRESS = {fid: addr.lower() for fid, _, _, _, addr in franchise_info}
FID_BY_ADDRESS = {v: k for k, v in FID_BY_ADDRESS.items()}  # invert to {email: fid}

def franchise_from_to_header(msg):
    to_hdr = msg.get('To', '')
    for _, addr in getaddresses([to_hdr]):
        if addr and addr.lower() in FID_BY_ADDRESS:
            return FID_BY_ADDRESS[addr.lower()]
    return None

###_________Zapier Integration_________###
def send_to_zapier(ParentFirstName, StudentFirstName, PhoneString, FranchiseID, GradeString):
    """
    Sends a formatted message to Zapier.
    The message includes a time-appropriate greeting and a grade phrase.
    """
    # Nested helper function to capitalize names.
    def capitalize_name(name):
        # Capitalize each word in the name (e.g., "john doe" -> "John Doe")
        return ' '.join(word.capitalize() for word in name.split())
    
    # Capitalize the parent's and student's names.
    ParentFirstName = capitalize_name(ParentFirstName)
    StudentFirstName = capitalize_name(StudentFirstName)

    zapier_webhook_url = os.getenv('ZapHookDirectInquiry')
    if not zapier_webhook_url:
        print("Zapier webhook URL is not set.")
        return
    greeting = format_greeting(FranchiseID)
    grade_phrase = format_grade_phrase(GradeString)
    director = get_director(FranchiseID)
    message = f"""{greeting} {ParentFirstName}, from Tutoring Club!

Thank you for filling out our contact request form.

We are available Monday through Thursday From 10 AM to 7 PM, and Saturday From 10 AM to 2 PM.

Please let us know a couple of convenient times for a 15-minute phone call to discuss {StudentFirstName}'s educational needs, our hours of operation, tuition options, and how Tutoring Club can best help your {grade_phrase}. We'll confirm once we receive your availability.

Looking forward to speaking with you!"""
    payload = {
        'message': message,
        'AssessmentPhone': PhoneString,
        'FranchiseID': FranchiseID
    }
    try:
        response = requests.post(zapier_webhook_url, json=payload)
        response.raise_for_status()
        print(f"Message sent to Zapier - {ParentFirstName} with phone {PhoneString}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending message to Zapier: {e}")

###_________Final Checks Before Insertion_________###

EXTRA_BLACKLIST: Set[str] = {
    "2499618600",
    "2563668195",
    "8852895525",
    "2206940173",
    "8557588624",
    "3454497480"
    # add more (digits only, no spaces/dashes) …
}

def is_phone_blacklisted(phone: str, extra: Iterable[str] = EXTRA_BLACKLIST) -> bool:
    """
    Rules:
      1. If the *normalised* phone (digits‑only) is in `extra`, block.
      2. Otherwise, if the first numeric character in the original string
         is 0 or 1, block.
    """
    # rule #0 - empty/None → let it through
    if not phone:
        return False
    # rule #1 - Return true when extra blacklist is hit
    digits_only = re.sub(r"\D", "", phone)   # strip ()‑ + etc.
    if digits_only and digits_only in extra:
        return True
    # rule #2 - Return true when Number starts with 0 or 1
    m = re.search(r"\d", phone)          # first numeric character
    return bool(m and m.group(0) in {"0", "1"})

###_________Database Insertion_________###
def insert_inquiry(ParentString, StudentString, PhoneString, EmailString, WebsiteString, GradeString):
    # 1) Build grade lookup dict and resolve Grade_SQL
    grade_dict_SQL = {
        "1st Grade": "1st",
        "2nd Grade": "2nd",
        "3rd Grade": "3rd",
        "4th Grade": "4th",
        "5th Grade": "5th",
        "6th Grade": "6th",
        "7th Grade": "7th",
        "8th Grade": "8th",
        "9th Grade": "9th",
        "10th Grade": "10th",
        "11th Grade": "11th",
        "12th Grade": "12th",
        "Middle School": "6th",
        "High School": "9th"
    }
    grade_string_SQL = (GradeString or "").strip()
    grade_SQL = grade_dict_SQL.get(grade_string_SQL, "K")
    
    # Split names for parent and student:
    ParentFirst, ParentLast = split_name(ParentString)
    StudentFirst, StudentLast = split_name(StudentString)
    ParentFirst = sanitize_name_for_sql(ParentFirst)
    ParentLast = sanitize_name_for_sql(ParentLast)
    StudentFirst = sanitize_name_for_sql(StudentFirst)
    StudentLast = sanitize_name_for_sql(StudentLast)

    # Get franchise ID from the website string.
    FranchiseID = get_franchise_id(WebsiteString)

    # Get the local date and time based on the franchise's timezone.
    local_dt = get_local_date_time(FranchiseID)
    local_date = local_dt.strftime('%Y-%m-%d')

    # Construct SQL to run the stored procedure with TVPs.
    sql = f"""
DECLARE @Students typeInquiryStudents;
DECLARE @Assessments typeAssessments_Time;
DECLARE @Meetings typeMeetings_Time;

INSERT INTO @Students (Grade, Subjects, School, Notes, FirstName, LastName)
VALUES ('{grade_SQL}', '', '', '', '{StudentFirst}', '{StudentLast}');

INSERT INTO @Assessments (Date, Subjects, Grade, Time, CFirstName, CLastName, SFirstName, SLastName)
VALUES ('{local_date}', '', '', '', '{ParentFirst}', '{ParentLast}', '', '');

INSERT INTO @Meetings (Date, ContactNumber, ContactEmail, StudentNames, Time, CFirstName, CLastName)
VALUES ('{local_date}', '', '', '{StudentFirst} {StudentLast}', '', '', '');

EXEC [dbo].[usp_CreateInquary]
    @Date = '{local_date}',
    @ContactFirstName = '{ParentFirst}',
    @ContactLastName = '{ParentLast}',
    @ContactPhone = '{PhoneString}',
    @Email = '{EmailString}',
    @Source = 'Online - TC Site',
    @Notes = '',
    @typeInquiryStudent = @Students,
    @typeAssessments = @Assessments,
    @typeMeetings = @Meetings,
    @FranchiseID = {FranchiseID},
    @PhoneInterview = 'Lead';
    """

    session = Session()
    try:
        send_telegram_message(f"SQL about to execute:\n{sql}",LOG_BOT, LOG_CHAT)
        session.execute(text(sql))
        session.commit()
        # After successful insertion, you might send the message to Zapier, except for 87:
        if FranchiseID != 1:
            send_to_zapier(ParentFirst, StudentFirst, PhoneString, FranchiseID, GradeString)
        else:
            print("Invalid FranchiseID detected. Skipping Zapier Text")
        return True
    except SQLAlchemyError as e:
        print(f"Error inserting inquiry: {e}")
        session.rollback()
        return False
    finally:
        session.close()

###_________Main Function_________###
def main():
    # Build the Service
    service = get_gmail_service()
    # Grab the Emails
    debug_unread(service)
    emails = get_unread_emails(service)
    if not emails:
        print("No unread emails found.")
        return

    for msg_id, msg in emails:
        try:
            # Only process if To: matches one of your franchise inboxes
            fid_to = franchise_from_to_header(msg)
            if not fid_to:
                continue

            sent_utc = extract_sent_utc(msg)
            local_sent = localize_to_franchise(sent_utc, fid_to)
            if sent_in_business_window(local_sent):
                # Inside business hours → let ALLDAY own it
                # mark_as_read(service, msg_id)  # optional triage
                try:
                    send_telegram_message(
                        f"⛔ AFTERHOURS skipped (in-hours) — FID {fid_to}, local sent: {local_sent}",
                        LOG_BOT, LOG_CHAT
                    )
                except Exception:
                    pass
                continue

            plain_text, raw_html = extract_email_body(msg)
            if not raw_html:
                print("No HTML content; skipping.")
                mark_as_read(service, msg_id)
                continue

            soup = BeautifulSoup(raw_html, 'html.parser')
            WebsiteString = extract_website_url_from_soup(soup)
            ParentString, StudentString, PhoneString, EmailString, GradeString = \
                parse_email_for_data_from_html(raw_html)
            send_telegram_message(
                f"📥 Parsed inquiry\n"
                f"• Website : {WebsiteString}\n"
                f"• Parent  : {repr(ParentString)}\n"
                f"• Student : {repr(StudentString)}\n"
                f"• Email   : {EmailString}\n"
                f"• Phone   : {PhoneString}\n"
                f"• Grade   : {repr(GradeString)}",
                LOG_BOT, LOG_CHAT
            )

            #Silly Blacklist LOL
            if is_phone_blacklisted(PhoneString):
                reason = (
                    "explicitly black‑listed"
                    if re.sub(r"\D", "", PhoneString) in EXTRA_BLACKLIST
                    else "starts with 0/1"
                )
                rsn_message = (f"Phone {reason}: {PhoneString} – skipped.")
                send_telegram_message(rsn_message, AUTO_BOT, AUTO_CHAT)
                mark_as_read(service, msg_id)
                continue


            if not ParentString or not EmailString:
                print("Missing critical fields – skipped.")
                mark_as_read(service, msg_id)
                continue

            insert_ok = insert_inquiry(
                ParentString, StudentString, PhoneString,
                EmailString, WebsiteString, GradeString
            )
            mark_as_read(service, msg_id)   # mark either way

        except Exception as e:
            print(f"Unexpected error for {msg_id}: {e}")
            mark_as_read(service, msg_id)

if __name__ == "__main__":
    main()
