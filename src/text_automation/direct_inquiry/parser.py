from __future__ import annotations

import re
from email.utils import getaddresses, parsedate_to_datetime
from typing import Iterable, Optional, Tuple

from bs4 import BeautifulSoup

from ..config import load_config, Franchise


def extract_website_url_from_soup(soup: BeautifulSoup) -> str:
    base = "https://tutoringclub.com/"
    for text in soup.stripped_strings:
        if base in text:
            start = text.find(base)
            end = text.find(" ", start)
            if end == -1:
                end = len(text)
            url_candidate = text[start:end]
            parts = url_candidate.split("/")
            if len(parts) >= 4:
                return f"{base}{parts[3]}/"
            return url_candidate
    return ""


def parse_email_for_data_from_html(html: str) -> tuple[str, str, str, str, str]:
    headings_map = {
        "parent": ["parent", "parents", "parent's name", "parents name", "parent name", "your name"],
        "student": ["student", "students", "student's name", "students name", "student name"],
        "phone": ["phone", "phone number"],
        "email": ["email", "email address"],
        "grade": ["grade", "grade level"],
    }
    soup = BeautifulSoup(html, "html.parser")
    data = {"parent": "", "student": "", "phone": "", "email": "", "grade": ""}
    for tr in soup.find_all("tr", attrs={"bgcolor": "#EAF2FA"}):
        heading_text = tr.get_text(separator=" ", strip=True).lower()
        for key, variations in headings_map.items():
            if any(v in heading_text for v in variations):
                next_tr = tr.find_next_sibling("tr")
                if next_tr:
                    data_value = next_tr.get_text(separator=" ", strip=True)
                    data[key] = data_value
                break
    for key in data:
        data[key] = data[key].replace("'", "''")
    return data["parent"], data["student"], data["phone"], data["email"], data["grade"]


def split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split()
    if len(parts) <= 1:
        return full_name.strip(), ""
    return " ".join(parts[:-1]), parts[-1]


def sanitize_name_for_sql(name: str) -> str:
    return name.replace("'", "''")


def franchise_from_to_header(msg) -> Optional[int]:
    cfg = load_config()
    to_hdr = msg.get("To", "")
    addr_to_fid = {
        f.email.lower(): f.id
        for f in cfg.franchises
        if f.email
    }
    for _, addr in getaddresses([to_hdr]):
        if addr and addr.lower() in addr_to_fid:
            return addr_to_fid[addr.lower()]
    return None


def extract_sent_utc(msg):
    try:
        d = msg.get("Date")
        if not d:
            return None
        dt = parsedate_to_datetime(d)
        if dt is None:
            return None
        from datetime import timezone
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None
