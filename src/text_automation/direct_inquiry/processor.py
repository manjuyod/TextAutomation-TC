from __future__ import annotations

import re
from datetime import datetime
from typing import Optional
from sqlalchemy import text as sa_text

from ..config import load_config
from ..db.sql import get_engine
from ..general.telegram import send_message, AUTO_BOT, AUTO_CHAT, LOG_BOT, LOG_CHAT
from ..general.zapier import send_direct_inquiry
from .gmail import get_gmail_service, get_unread_messages, mark_as_read, extract_email_body
from .parser import (
    extract_website_url_from_soup,
    parse_email_for_data_from_html,
    split_name,
    sanitize_name_for_sql,
    franchise_from_to_header,
    extract_sent_utc,
)
from .business_hours import localize_timestamp, in_business_window


EXTRA_BLACKLIST = {
    "2499618600",
    "2563668195",
    "8852895525",
    "2206940173",
    "8557588624",
    "3454497480",
}


def is_phone_blacklisted(phone: str) -> bool:
    if not phone:
        return False
    digits_only = re.sub(r"\D", "", phone)
    cfg = load_config()
    di = cfg.direct_inquiry
    blacklist = set(EXTRA_BLACKLIST)
    if di and di.phone_blacklist:
        blacklist.update(di.phone_blacklist)
    if digits_only and digits_only in blacklist:
        return True
    m = re.search(r"\d", phone)
    return bool(m and m.group(0) in {"0", "1"})


def _franchise_by_url_fragment(url: str) -> int | None:
    cfg = load_config()
    for f in cfg.franchises:
        if f.url and f.url.lower() in (url or "").lower():
            return f.id
    return None


def _director_for_fid(fid: int) -> str:
    cfg = load_config()
    for f in cfg.franchises:
        if f.id == fid:
            return f.director or ""
    return ""


def _format_grade_phrase(grade: str) -> str:
    cfg = load_config()
    di = cfg.direct_inquiry
    grade_dict = di.grade_phrase_map if (di and di.grade_phrase_map) else {
        "Kindergarten": "Kindergartener",
        "1st Grade": "1st grader",
        "2nd Grade": "2nd grader",
        "3rd Grade": "3rd grader",
        "4th Grade": "4th grader",
        "5th Grade": "5th grader",
        "6th Grade": "6th grader",
        "7th Grade": "7th grader",
        "8th Grade": "8th grader",
        "9th Grade": "9th grader",
        "10th Grade": "10th grader",
        "11th Grade": "11th grader",
        "12th Grade": "12th grader",
    }
    return grade_dict.get((grade or "").strip(), "student")


def _grade_sql(grade: str) -> str:
    cfg = load_config()
    di = cfg.direct_inquiry
    grade_dict_sql = di.grade_sql_map if (di and di.grade_sql_map) else {
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
        "High School": "9th",
    }
    return grade_dict_sql.get((grade or "").strip(), "K")


def _build_insert_sql(
    parent_first: str,
    parent_last: str,
    student_first: str,
    student_last: str,
    phone: str,
    email_addr: str,
    local_date: str,
    franchise_id: int,
    grade_sql: str,
) -> str:
    return f"""
DECLARE @Students typeInquiryStudents;
DECLARE @Assessments typeAssessments_Time;
DECLARE @Meetings typeMeetings_Time;

INSERT INTO @Students (Grade, Subjects, School, Notes, FirstName, LastName)
VALUES ('{grade_sql}', '', '', '', '{student_first}', '{student_last}');

INSERT INTO @Assessments (Date, Subjects, Grade, Time, CFirstName, CLastName, SFirstName, SLastName)
VALUES ('{local_date}', '', '', '', '{parent_first}', '{parent_last}', '', '');

INSERT INTO @Meetings (Date, ContactNumber, ContactEmail, StudentNames, Time, CFirstName, CLastName)
VALUES ('{local_date}', '', '', '{student_first} {student_last}', '', '', '');

EXEC [dbo].[usp_CreateInquary]
    @Date = '{local_date}',
    @ContactFirstName = '{parent_first}',
    @ContactLastName = '{parent_last}',
    @ContactPhone = '{phone}',
    @Email = '{email_addr}',
    @Source = 'Online - TC Site',
    @Notes = '',
    @typeInquiryStudent = @Students,
    @typeAssessments = @Assessments,
    @typeMeetings = @Meetings,
    @FranchiseID = {franchise_id},
    @PhoneInterview = 'Lead';
"""


def process_direct_inquiry_payload(
    *,
    parent_name: str,
    student_name: str,
    phone: str,
    email_addr: str,
    grade: str,
    franchise_id: int,
    local_dt: datetime | None,
    dry_run: bool,
) -> bool:
    if not parent_name or not email_addr:
        return False

    if is_phone_blacklisted(phone):
        if not dry_run:
            send_message(f"[direct-inquiry] Skipping blacklisted phone for FID={franchise_id}", LOG_BOT, LOG_CHAT)
        return False

    p_first, p_last = split_name(parent_name)
    s_first, s_last = split_name(student_name)
    p_first = sanitize_name_for_sql(p_first)
    p_last = sanitize_name_for_sql(p_last)
    s_first = sanitize_name_for_sql(s_first)
    s_last = sanitize_name_for_sql(s_last)
    phone = sanitize_name_for_sql(phone)
    email_addr = sanitize_name_for_sql(email_addr)

    if not local_dt:
        local_dt = datetime.now()
    local_date = local_dt.strftime("%Y-%m-%d")

    sql = _build_insert_sql(
        parent_first=p_first,
        parent_last=p_last,
        student_first=s_first,
        student_last=s_last,
        phone=phone,
        email_addr=email_addr,
        local_date=local_date,
        franchise_id=franchise_id,
        grade_sql=_grade_sql(grade),
    )

    if dry_run:
        print(f"[direct-inquiry] [dry-run] Would execute SQL/Zapier for FID={franchise_id}")
        return True

    eng = get_engine()
    with eng.begin() as conn:
        send_message(f"[direct-inquiry] Executing SQL for FID={franchise_id}", LOG_BOT, LOG_CHAT)
        conn.execute(sa_text(sql))

    if franchise_id not in (1, 8):
        if not send_direct_inquiry(
            parent_first_name=p_first,
            student_first_name=s_first,
            phone=phone,
            franchise_id=franchise_id,
            grade_string=grade,
        ):
            send_message(f"[direct-inquiry] Zapier failed for FID={franchise_id}", LOG_BOT, LOG_CHAT)
            raise RuntimeError("Direct inquiry Zapier send failed")
        send_message(f"[direct-inquiry][ok] SQL+Zapier for FID={franchise_id}", AUTO_BOT or LOG_BOT, AUTO_CHAT or LOG_CHAT)

    return True


def _process_one(service, msg_id: str, msg, mode: str, dry_run: bool) -> Optional[bool]:
    cfg = load_config()
    fid = franchise_from_to_header(msg)
    if not fid:
        return None

    sent_utc = extract_sent_utc(msg)
    local_dt = localize_timestamp(sent_utc, fid)
    is_in_hours = in_business_window(local_dt)
    is_vegas = fid in (cfg.direct_inquiry.vegas_ids if cfg.direct_inquiry else (6, 11, 15, 16, 60, 110))

    # routing logic
    if mode == "auto":
        if is_vegas:
            if is_in_hours:
                if not dry_run:
                    mark_as_read(service, msg_id)  # mark read, no action
                return True
            # after-hours vegas: process
        else:
            # non-vegas: process any time
            pass
    elif mode == "all-day":
        if is_vegas:
            # NV: only mark read during hours, skip otherwise
            if is_in_hours:
                if not dry_run:
                    mark_as_read(service, msg_id)
                return True
            return None
        # non-vegas: process
    elif mode == "after-hours":
        # Only process after-hours for Vegas to avoid overlap
        if not (is_vegas and (not is_in_hours)):
            return None

    # Extract content
    plain_text, raw_html = extract_email_body(msg)
    if not raw_html:
        if not dry_run:
            mark_as_read(service, msg_id)
        return None

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw_html, "html.parser")
    website = extract_website_url_from_soup(soup)
    parent_str, student_str, phone_str, email_str, grade_str = parse_email_for_data_from_html(raw_html)

    # route by location fragment on the source URL
    fid_detected = _franchise_by_url_fragment(website)
    if not fid_detected:
        if not dry_run:
            mark_as_read(service, msg_id)
        if not dry_run:
            send_message(
                f"[direct-inquiry] No configured location fragment found in source URL for message {msg_id}.",
                LOG_BOT,
                LOG_CHAT,
            )
        return None

    if is_phone_blacklisted(phone_str):
        if not dry_run:
            send_message(f"[direct-inquiry] Blacklisted phone for message {msg_id}.", LOG_BOT, LOG_CHAT)
            mark_as_read(service, msg_id)
        return None

    if not parent_str or not email_str:
        if not dry_run:
            mark_as_read(service, msg_id)
        return None

    local_dt = localize_timestamp(extract_sent_utc(msg), fid_detected)
    if not local_dt:
        local_dt = datetime.now()

    try:
        processed = process_direct_inquiry_payload(
            parent_name=parent_str,
            student_name=student_str,
            phone=phone_str,
            email_addr=email_str,
            grade=grade_str,
            franchise_id=fid_detected,
            local_dt=local_dt,
            dry_run=dry_run,
        )
    except Exception as e:
        send_message(f"[direct-inquiry] Processing failed for msg {msg_id}: {e}", LOG_BOT, LOG_CHAT)
        return None

    if not dry_run and processed:
        mark_as_read(service, msg_id)
    elif not dry_run and not processed:
        mark_as_read(service, msg_id)

    return processed


def process(mode: str = "auto", max_results: int = 50, dry_run: bool = False) -> int:
    service = get_gmail_service()
    messages = get_unread_messages(service, max_results=max_results)
    processed = 0
    for msg_id, msg in messages:
        try:
            res = _process_one(service, msg_id, msg, mode, dry_run)
            if res:
                processed += 1
        except Exception as e:
            send_message(f"DirectInquiry error for {msg_id}: {e}", LOG_BOT, LOG_CHAT)
            # best effort: mark as read to avoid re-processing loops
            if not dry_run:
                try:
                    mark_as_read(service, msg_id)
                except Exception:
                    pass
    return processed
