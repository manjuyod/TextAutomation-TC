from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from bs4 import BeautifulSoup
from sqlalchemy import text as sa_text

from ..config import load_config
from ..db.sql import get_engine
from ..general.telegram import send_message, AUTO_BOT, AUTO_CHAT, LOG_BOT, LOG_CHAT
from ..direct_inquiry.gmail import (
    get_gmail_service,
    get_unread_messages,
    mark_as_read,
    extract_email_body,
)


def _display_name(first: Optional[str], last: Optional[str]) -> str:
    first = (first or "").strip()
    last = (last or "").strip()
    return (first + (" " + last if last else "")).strip() or "Unknown"

def _format_phone_number(phone_str: Optional[str]) -> Optional[str]:
    if not phone_str:
        return None
    digits = re.sub(r"\D", "", phone_str)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return phone_str
    return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def _sanitize_for_sql(val: Optional[str], max_length: Optional[int] = None, is_numeric: bool = False) -> str:
    if val is None:
        return "NULL"
    s = str(val).strip().replace("'", "''")
    if is_numeric and not s.isdigit():
        return "NULL"
    if max_length is not None and len(s) > max_length:
        s = s[:max_length]
    return s


def _sanitize_value(val: Any) -> str:
    if val is None or val == "":
        return "NULL"
    if isinstance(val, str):
        return f"'{_sanitize_for_sql(val)}'"
    return f"'{str(val)}'"


def _extract_web_link(html: str) -> Optional[str]:
    m = re.search(r"(https://tutoringclub\.com/[^\s\"<]+student-intake-form/?\b)", html)
    return m.group(1) if m else None


def _franchise_id_from_link(link: Optional[str]) -> Optional[int]:
    if not link:
        return None
    norm = link.rstrip("/")
    cfg = load_config()
    for f in cfg.franchises:
        if f.assessment_form and f.assessment_form.rstrip("/") == norm:
            return f.id
    # Fallback: try matching by site url prefix
    for f in cfg.franchises:
        if f.url and norm.startswith(f.url.rstrip("/")):
            return f.id
    return None


def _parse_html_to_mapping(html: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    inner_table = soup.find("table", {"bgcolor": "#FFFFFF"})
    if not inner_table:
        return {}
    rows = inner_table.find_all("tr")

    data: List[Tuple[str, str]] = []
    for row in rows:
        ul = row.find("ul")
        answer = str(ul) if ul else row.get_text(" ", strip=True)
        td = row.find("td", colspan=True)
        if td and "font-size:14px" in td.get("style", "") and td.get_text(strip=True):
            data.append(("header", td.get_text(strip=True)))
        else:
            strong = row.find("strong")
            if strong:
                data.append(("question", strong.get_text(" ", strip=True)))
            else:
                if answer:
                    data.append(("answer", answer))

    sections: Dict[str, List[Tuple[str, str]]] = {}
    current: Optional[str] = None
    i = 0
    while i < len(data):
        typ, content = data[i]
        if typ == "header":
            current = content
            sections[current] = []
            i += 1
        elif typ == "question":
            if i + 1 < len(data) and data[i + 1][0] == "answer":
                q = content
                a = data[i + 1][1]
                if current is None:
                    current = "General"
                    sections[current] = []
                sections[current].append((q, a))
                i += 2
            else:
                i += 1
        else:
            i += 1

    result: Dict[str, Any] = {
        "franchise_id": None,
        "student_info": [
            {
                "home_address": None,
                "siblings": None,
                "student_1": {},
                "student_2": {},
                "student_3": {},
                "student_4": {},
            }
        ],
        "parent_info": [{}],
    }

    # Address
    if "Address" in sections:
        addr: Dict[str, Any] = {}
        for q, a in sections["Address"]:
            if "Street Address" in q:
                addr["addr_line1"] = a
            elif "City" in q:
                addr["city"] = a
            elif "State" in q:
                addr["state"] = a
            elif "ZIP" in q or "Postal Code" in q:
                addr["postal"] = a
        addr.setdefault("addr_line1", "")
        addr.setdefault("addr_line2", "")
        addr.setdefault("city", "")
        addr.setdefault("state", "")
        addr.setdefault("postal", "")
        result["student_info"][0]["home_address"] = addr

    # Parent info (limited subset; rest defaults to None)
    parent_info: Dict[str, Any] = {}
    if "Parent or Guardian 1" in sections:
        p1 = {k: None for k in ("first", "last", "occupation", "employer", "email", "cell")}
        for q, a in sections["Parent or Guardian 1"]:
            if "First Name" in q:
                p1["first"] = a
            elif "Last Name" in q:
                p1["last"] = a
            elif "Occupation" in q:
                p1["occupation"] = a
            elif "Employer" in q:
                p1["employer"] = a
            elif "Email" in q:
                p1["email"] = a
            elif "Phone" in q:
                p1["cell"] = a
        parent_info["parent_1"] = {
            "full_name": {"first": p1["first"], "last": p1["last"]},
            "occupation": p1["occupation"],
            "employer": p1["employer"],
            "cell": p1["cell"],
            "email": p1["email"],
            "permission_to_text": None,
        }
    if "Parent or Guardian 2" in sections:
        p2 = {k: None for k in ("first", "last", "occupation", "employer", "email", "cell")}
        for q, a in sections["Parent or Guardian 2"]:
            if "First Name" in q:
                p2["first"] = a
            elif "Last Name" in q:
                p2["last"] = a
            elif "Occupation" in q:
                p2["occupation"] = a
            elif "Employer" in q:
                p2["employer"] = a
            elif "Email" in q:
                p2["email"] = a
            elif "Phone" in q:
                p2["cell"] = a
        parent_info["parent_2"] = {
            "full_name": {"first": p2["first"], "last": p2["last"]},
            "occupation": p2["occupation"],
            "employer": p2["employer"],
            "cell": p2["cell"],
            "email": p2["email"],
            "permission_to_text": None,
        }
    if "Emergency Contact" in sections:
        ec = {k: None for k in ("first", "last", "phone")}
        for q, a in sections["Emergency Contact"]:
            if "First Name" in q:
                ec["first"] = a
            elif "Last name" in q:
                ec["last"] = a
            elif "Phone" in q:
                ec["phone"] = a
        parent_info["emergency_contact"] = {
            "name": {"first": ec["first"], "last": ec["last"]},
            "phone_number": ec["phone"],
            "type": "Relative",
        }
    result["parent_info"] = [parent_info]

    # Students (minimal extraction: name, dob, grade)
    for idx, key in enumerate(["Student 1", "Student 2", "Student 3", "Student 4"], start=1):
        if key not in sections:
            continue
        info: Dict[str, Any] = {}
        fn = ln = dob = grade = None
        for q, a in sections[key]:
            ql = q.lower()
            if "first name" in ql:
                fn = a
            elif "last name" in ql:
                ln = a
            elif "date of birth" in ql or "dob" in ql:
                dob = a
            elif ql.startswith("grade") or "current grade" in ql:
                grade = a
        if fn or ln or dob or grade:
            info["name"] = {"FirstName": fn, "LastName": ln}
            info["dob"] = dob
            info["grade"] = grade
            result["student_info"][0][f"student_{idx}"] = info

    return result


def _count_students(template: Dict[str, Any]) -> int:
    try:
        block = template.get("student_info", [{}])[0]
        return sum(1 for k, v in block.items() if k.startswith("student_") and v)
    except Exception:
        return 0


def _convert_dob(dob_str: Optional[str]) -> str:
    if not dob_str:
        return "NULL"
    try:
        dob = datetime.strptime(dob_str, "%m/%d/%Y")
        return f"'{dob.strftime('%Y-%m-%d')}'"
    except Exception:
        return "NULL"


def _generate_sql(input_data: Dict[str, Any], template: Dict[str, Any], student_count: int) -> str:
    address_info = (template.get("student_info", [{}])[0] or {}).get("home_address", {}) or {}
    pinfo = (template.get("parent_info") or [{}])[0] or {}
    p1 = pinfo.get("parent_1", {})
    p2 = pinfo.get("parent_2", {})
    ec = pinfo.get("emergency_contact", {})

    father = p1.get("full_name", {})
    mother = p2.get("full_name", {})
    emergency = ec.get("name", {})

    sp_name = (
        "dpinket_TC_QA.dbo.USP_UpdateTempStudentAuto" if input_data.get("InquiryID") else "dpinket_TC_QA.dbo.USP_InsertTempStudentAuto"
    )

    base = f"""
EXEC {sp_name}
    @StudentCount={student_count},
    @InquiryID={_sanitize_value(input_data.get('InquiryID'))},
    @FormID=NULL,
    @SubmissionID=NULL,
    @GuardianFirstName={_sanitize_value(input_data.get('GuardianFirstName'))},
    @GuardianLastName={_sanitize_value(input_data.get('GuardianLastName'))},
    @FranchiseID={_sanitize_value(template.get('franchise_id'))},
    @FranchiseName={_sanitize_value(input_data.get('FranchiseName'))},
    @FranchiseEmail={_sanitize_value(input_data.get('FranchiseEmail'))},
    @FranchiseAddress={_sanitize_value(input_data.get('FranchiseAddress'))},
    @HomeAddress={_sanitize_value(address_info.get('addr_line1'))},
    @City={_sanitize_value(address_info.get('city'))},
    @State={_sanitize_value(address_info.get('state'))},
    @Zip={_sanitize_value(address_info.get('postal'))},
    @Street1={_sanitize_value(address_info.get('addr_line1'))},
    @FatherName={_sanitize_value(f"{(father.get('first') or '').strip()} {(father.get('last') or '').strip()}")},
    @FatherOccupation={_sanitize_value(p1.get('occupation'))},
    @FatherEmployer={_sanitize_value(p1.get('employer'))},
    @FatherCellPhone={_sanitize_value(_format_phone_number(p1.get('cell')))},
    @FatherEmail={_sanitize_value(p1.get('email'))},
    @MotherName={_sanitize_value(f"{(mother.get('first') or '').strip()} {(mother.get('last') or '').strip()}")},
    @MotherOccupation={_sanitize_value(p2.get('occupation'))},
    @MotherEmployer={_sanitize_value(p2.get('employer'))},
    @MotherCellPhone={_sanitize_value(_format_phone_number(p2.get('cell')))},
    @MotherEmail={_sanitize_value(p2.get('email'))},
    @EmergencyContact1Type={_sanitize_value(ec.get('type'))},
    @EmergencyContact1Name={_sanitize_value(f"{(emergency.get('first') or '').strip()} {(emergency.get('last') or '').strip()}")},
    @EmergencyContact1Phone={_sanitize_value(_format_phone_number(ec.get('phone_number')))}
""".strip()

    students_block = (template.get("student_info", [{}])[0] or {})
    for i in range(1, student_count + 1):
        s = students_block.get(f"student_{i}", {}) or {}
        name = s.get("name", {}) or {}
        dob = _convert_dob(s.get("dob"))
        base += (
            f",\n    @FirstName{i}={_sanitize_value(name.get('FirstName'))}"
            f",\n    @LastName{i}={_sanitize_value(name.get('LastName'))}"
            f",\n    @Grade{i}={_sanitize_value(s.get('grade'))}"
            f",\n    @Birthdate{i}={dob}"
            f",\n    @Age{i}={_sanitize_value(None)}"
            f",\n    @Question1String{i}={_sanitize_value(None)}"
            f",\n    @Question2String{i}={_sanitize_value(None)}"
            f",\n    @Question3String{i}={_sanitize_value(None)}"
            f",\n    @Question4String{i}={_sanitize_value(None)}"
            f",\n    @Question5String{i}={_sanitize_value(None)}"
            f",\n    @AdditionalComments{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion1Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion2Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion2Details{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion3Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion3Details{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion4Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion4Details{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion5Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion5Details{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion6Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion6Details{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion7Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion7Details{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion8Issue{i}={_sanitize_value(None)}"
            f",\n    @MedicalQuestion8Details{i}={_sanitize_value(None)}"
        )

    return base


def _fetch_missing_input(fid: Optional[int], student_first: Optional[str], student_last: Optional[str]) -> Dict[str, Any]:
    if not (fid and (student_first or student_last)):
        return {}
    q = sa_text(
        """
SELECT TOP 1 InquiryID, GuardianFirstName, GuardianLastName, FranchiseName, FranchiseEmail, FranchiseAddress
FROM dpinket_TC_QA.dbo.tblTempStudentAuto
WHERE FranchiseID = :fid AND FirstName = :first AND LastName = :last
        """
    )
    eng = get_engine()
    try:
        with eng.connect() as conn:
            row = conn.execute(q, {"fid": fid, "first": student_first or "", "last": student_last or ""}).first()
            if not row:
                return {}
            keys = [c for c in row._mapping.keys()]
            return {k: row._mapping[k] for k in keys}
    except Exception as ex:
        print(f"[student-intake] lookup error: {ex}")
        return {}


def process(max_results: int = 10, dry_run: bool = False) -> int:
    cfg = load_config()
    si_token = Path(cfg.student_intake.token_path) if (cfg.student_intake and cfg.student_intake.token_path) else None
    service = get_gmail_service(token_path=si_token)
    messages = get_unread_messages(service, max_results=max_results)
    processed = 0
    for msg_id, msg in messages:
        plain, raw_html = extract_email_body(msg)
        html = raw_html or (f"<html><body><pre>{plain or ''}</pre></body></html>")
        if "student-intake-form" not in (html or ""):
            continue  # not a student intake form email

        mapping = _parse_html_to_mapping(html)
        link = _extract_web_link(html)
        fid = _franchise_id_from_link(link)
        mapping["franchise_id"] = fid

        student_count = _count_students(mapping)
        s1 = mapping.get("student_info", [{}])[0].get("student_1", {}).get("name", {})
        missing = _fetch_missing_input(fid, s1.get("FirstName"), s1.get("LastName"))
        input_data = {
            "InquiryID": missing.get("InquiryID"),
            "form_id": None,
            "submission_id": None,
            "GuardianFirstName": missing.get("GuardianFirstName"),
            "GuardianLastName": missing.get("GuardianLastName"),
            "FranchiseName": missing.get("FranchiseName"),
            "FranchiseEmail": missing.get("FranchiseEmail"),
            "FranchiseAddress": missing.get("FranchiseAddress"),
        }

        sql = _generate_sql(input_data, mapping, student_count)

        # Compose log context
        student_name = _display_name(s1.get("FirstName"), s1.get("LastName"))
        guardian_name = _display_name(input_data.get("GuardianFirstName"), input_data.get("GuardianLastName"))
        inquiry_id = input_data.get("InquiryID") or ""
        header = f"[student-intake] FID={fid or 'Unknown'} InquiryID={inquiry_id} Parent={guardian_name} Student={student_name}"

        if dry_run:
            print("[dry-run] Would execute Student Intake SQL:")
            print(sql[:1000] + ("..." if len(sql) > 1000 else ""))
            # Unconditional Telegram logs (legacy parity)
            send_message(f"{header}\n[dry-run] Would execute SQL", LOG_BOT, LOG_CHAT)
            send_message(sql[:3500] + ("\n..." if len(sql) > 3500 else ""), LOG_BOT, LOG_CHAT)
            mark_as_read(service, msg_id)
            processed += 1
            continue

        eng = get_engine()
        try:
            with eng.begin() as conn:
                # Log SQL before executing for traceability
                send_message(header, LOG_BOT, LOG_CHAT)
                send_message(sql[:3500] + ("\n..." if len(sql) > 3500 else ""), LOG_BOT, LOG_CHAT)
                conn.execute(sa_text(sql))
            send_message(f"[student-intake][ok] {header}", AUTO_BOT or LOG_BOT, AUTO_CHAT or LOG_CHAT)
            mark_as_read(service, msg_id)
            processed += 1
        except Exception as ex:
            print(f"[student-intake] SQL error: {ex}")
            send_message(f"[student-intake][error] {header}\n{ex}", AUTO_BOT or LOG_BOT, AUTO_CHAT or LOG_CHAT)
            # Also log failing SQL for debugging
            try:
                send_message(sql[:3500] + ("\n..." if len(sql) > 3500 else ""), LOG_BOT, LOG_CHAT)
            except Exception:
                pass
            # Still mark as read to avoid loops, mirroring other flows
            mark_as_read(service, msg_id)
    return processed
