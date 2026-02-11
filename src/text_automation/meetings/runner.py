from __future__ import annotations

import time
from datetime import datetime

import pandas as pd

from .data import fetch_meeting_data
from .messages import generate_message, send_to_webhook
from .data import fetch_meeting_data_morning
from .cache import (
    select_cache,
    upsert_from_server,
    delete_missing_sent_by_pk,
    pending_to_text,
    mark_text_sent,
    claim_row_for_send,
    mark_text_sent_by_row_ids,
    revert_row_to_pending,
)
from ..general.telegram import send_message, LOG_BOT, LOG_CHAT
from ..general.student_names import parse_student_names, format_student_names


def _resolve_parent_names(guardian_name: str, parent1_name: str | None, parent2_name: str | None) -> tuple[str, str, str]:
    """
    Resolve guardian_default, primary_parent, secondary_parent for messages.

    - guardian_default: original GuardianFirstName (trimmed)
    - primary_parent: chosen greeting addressee (first name or guardian)
    - secondary_parent: formatted as " and {FirstName}" or empty string
    """
    guardian = (guardian_name or "").strip()
    p1 = (parent1_name or "").strip()
    p2 = (parent2_name or "").strip()

    p1_first = p1.split()[0].strip() if p1 else ""
    p2_first = p2.split()[0].strip() if p2 else ""

    invalid_tokens = {"n/a", "na", "not available", "deceased", "dead"}

    primary_parent = ""
    secondary_parent = ""
    guardian_default = guardian

    if not p1_first and not p2_first:
        primary_parent = guardian_default
    elif p1_first and p2_first and p1_first == p2_first:
        primary_parent = guardian_default
        secondary_parent = ""
    elif p1_first.lower() in invalid_tokens:
        secondary_parent = guardian_default
        primary_parent = ""
    elif p2_first.lower() in invalid_tokens:
        primary_parent = guardian_default
        secondary_parent = ""
    elif guardian and guardian.lower() in p1_first.lower():
        primary_parent = p1_first
        secondary_parent = f" and {p2_first}" if p2_first else ""
    elif guardian and guardian.lower() in p2_first.lower():
        primary_parent = p2_first
        secondary_parent = f" and {p1_first}" if p1_first else ""
    else:
        primary_parent = guardian_default
        secondary_parent = ""

    return primary_parent, secondary_parent, guardian_default


def _parse_datetime(date_val, time_val) -> datetime | None:
    try:
        dt_date = pd.to_datetime(str(date_val)).date()
        dt_time = pd.to_datetime(str(time_val)).time()
        return datetime.combine(dt_date, dt_time)
    except Exception:
        return None


def scheduled_to_webhook(dry_run: bool = False, sleep_seconds: float = 1.5) -> int:
    """Meeting1 scheduled notifications with local cache synchronization."""
    df_server = fetch_meeting_data()
    df_cache = select_cache()

    if df_server.empty and (df_cache is None or df_cache.empty):
        return 0

    # Upsert all server rows; reset IsText='No' when date/time changed
    upsert_from_server(df_server)

    # Run monthly cleanup AFTER upsert to ensure cache rows carry the latest MeetingID,
    # avoiding delete+reinsert cascades that could reset IsText unnecessarily.
    if not df_server.empty:
        try:
            from datetime import datetime as _dt

            today = _dt.now()
            if today.day == 1:
                server_pks = set(int(x) for x in df_server["MeetingID"].dropna().astype(int).unique())
                print({"mode": "scheduled", "entity": "meeting", "op": "monthly_delete", "status": "execute", "server_pk_count": len(server_pks)})
                # delete_missing_sent_by_pk(server_pks)
                # Warning: Buggy Function. Fix Later.
            else:
                print({"mode": "scheduled", "entity": "meeting", "op": "monthly_delete", "status": "skip", "day": today.day})
        except Exception as _ex:
            print({"mode": "scheduled", "entity": "meeting", "op": "monthly_delete", "status": "error", "error": str(_ex)})

    df_current = pending_to_text()
    if df_current is None or df_current.empty:
        return 0
    sent_count = 0
    for _, row in df_current.iterrows():
        row_id = int(row.get("ID") or 0)
        dt = _parse_datetime(row.get("MeetingDate"), row.get("MeetingTime"))
        if not dt:
            continue
        fid = int(row.get("FranchiseID") or 0)
        primary_parent, secondary_parent, guardian_default = _resolve_parent_names(
            str(row.get("GuardianFirstName", "")),
            (str(row.get("Parent1Name")) if row.get("Parent1Name") is not None else None),
            (str(row.get("Parent2Name")) if row.get("Parent2Name") is not None else None),
        )
        # Normalize student names to first names only (e.g., "Alice and Bob")
        raw_students = str(row.get("StudentString", ""))
        first_names = parse_student_names(raw_students)
        formatted_names = format_student_names(first_names, max_names=4)

        msg = generate_message(
            franchise_id=fid,
            meeting_dt=dt,
            student_names=formatted_names,
            guardian_default=guardian_default,
            primary_parent=primary_parent,
            secondary_parent=secondary_parent,
            grade=str(row.get("Grade")) if row.get("Grade") is not None else None,
            mode="scheduled",
        )
        header = f"[meeting][scheduled] FID={fid} InquiryID={int(row.get('InquiryID') or 0)} MeetingID={row.get('MeetingID') or ''} Date={str(row.get('MeetingDate') or '')} Time={str(row.get('MeetingTime') or '')}"
        if dry_run:
            print({"mode": "scheduled", "entity": "meeting", "franchise_id": fid, "decision": "send", "dry_run": True})
            send_message(header + " [dry-run]", LOG_BOT, LOG_CHAT)
        else:
            # Atomic claim (No -> Sending)
            if row_id and not claim_row_for_send(row_id):
                print({
                    "mode": "scheduled",
                    "entity": "meeting",
                    "op": "claim",
                    "status": "skip",
                    "id": row_id,
                    "inquiry_id": int(row.get("InquiryID") or 0),
                })
                continue
            try:
                send_message(header, LOG_BOT, LOG_CHAT)
                ok = send_to_webhook(fid, msg, phone=str(row.get("AssessmentPhone", "")))
                if ok:
                    mark_text_sent_by_row_ids([row_id])
                    sent_count += 1
                else:
                    revert_row_to_pending(row_id)
                    print({
                        "mode": "scheduled",
                        "entity": "meeting",
                        "op": "send_failed",
                        "id": row_id,
                        "inquiry_id": int(row.get("InquiryID") or 0),
                    })
            finally:
                time.sleep(sleep_seconds)
    return sent_count


def morning_to_webhook(
    dry_run: bool = False,
    franchise_ids: list[int] | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
    sleep_seconds: float = 1.5,
) -> int:
    df = fetch_meeting_data_morning(franchise_ids=franchise_ids, since=since, until=until, limit=limit)
    if df.empty:
        return 0
    sent = 0
    for _, row in df.iterrows():
        fid = int(row.get("FranchiseID") or 0)
        dt = _parse_datetime(row.get("MeetingDate"), row.get("MeetingTime"))
        if dt is None:
            print({"mode": "morning", "entity": "meeting", "franchise_id": fid, "decision": "skip_invalid_dt", "dry_run": dry_run})
            continue
        primary_parent, secondary_parent, guardian_default = _resolve_parent_names(
            str(row.get("GuardianFirstName", "")),
            (str(row.get("Parent1Name")) if row.get("Parent1Name") is not None else None),
            (str(row.get("Parent2Name")) if row.get("Parent2Name") is not None else None),
        )
        # Normalize student names to first names only (e.g., "Alice and Bob")
        raw_students = str(row.get("StudentString", ""))
        first_names = parse_student_names(raw_students)
        formatted_names = format_student_names(first_names, max_names=4)

        msg = generate_message(
            franchise_id=fid,
            meeting_dt=dt,
            student_names=formatted_names,
            guardian_default=guardian_default,
            primary_parent=primary_parent,
            secondary_parent=secondary_parent,
            grade=str(row.get("Grade")) if row.get("Grade") is not None else None,
            mode="morning",
        )
        header = f"[meeting][morning] FID={fid} InquiryID={int(row.get('InquiryID') or 0)} MeetingID={row.get('MeetingID') or ''} Date={str(row.get('MeetingDate') or '')} Time={str(row.get('MeetingTime') or '')}"
        if dry_run:
            print({"mode": "morning", "entity": "meeting", "franchise_id": fid, "decision": "send", "dry_run": True})
            send_message(header + " [dry-run]", LOG_BOT, LOG_CHAT)
        else:
            send_message(header, LOG_BOT, LOG_CHAT)
            send_to_webhook(fid, msg, phone=str(row.get("AssessmentPhone", "")))
            sent += 1
            time.sleep(sleep_seconds)
    return sent
