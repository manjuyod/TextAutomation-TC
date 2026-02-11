from __future__ import annotations

import time
from datetime import datetime

import pandas as pd

from .data import fetch_assessment_data
from .messages import generate_message, send_to_webhook
from .data import fetch_assessment_data_morning
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


def _parse_datetime(date_val, time_val) -> tuple[datetime | None, str]:
    try:
        dt_date = pd.to_datetime(str(date_val)).date()
        dt_time = pd.to_datetime(str(time_val)).time()
        combined = datetime.combine(dt_date, dt_time)
        time_str = combined.strftime("%I:%M %p")
        return combined, time_str
    except Exception:
        return None, ""


def scheduled_to_webhook(dry_run: bool = False, sleep_seconds: float = 1.5) -> int:
    """Orchestrate cache sync and send assessment notifications (Assessment1).

    - Sync local cache (insert new, remove extraneous, handle reschedules).
    - Send for cache rows with IsText == 'No'.
    Returns number of rows texted.
    """
    df_server = fetch_assessment_data()
    df_cache = select_cache()

    if df_server.empty and (df_cache is None or df_cache.empty):
        return 0

    # Upsert all current server rows; reset IsText='No' when date/time changed
    upsert_from_server(df_server)

    # Run monthly cleanup AFTER upsert, so existing cache rows are updated with latest PKs,
    # avoiding an unnecessary delete+reinsert that could flip IsText to 'No'.
    if not df_server.empty:
        try:
            from datetime import datetime as _dt

            today = _dt.now()
            if today.day == 1:
                server_pks = set(int(x) for x in df_server["AssessmentID"].dropna().astype(int).unique())
                print({"mode": "scheduled", "entity": "assessment", "op": "monthly_delete", "status": "execute", "server_pk_count": len(server_pks)})
                # delete_missing_sent_by_pk(server_pks)
                # Warning: Buggy Function. Fix Later
            else:
                print({"mode": "scheduled", "entity": "assessment", "op": "monthly_delete", "status": "skip", "day": today.day})
        except Exception as _ex:
            print({"mode": "scheduled", "entity": "assessment", "op": "monthly_delete", "status": "error", "error": str(_ex)})

    # Send for cache rows with IsText == 'No'
    df_current = pending_to_text()
    if df_current is None or df_current.empty:
        return 0
    sent_count = 0
    for _, row in df_current.iterrows():
        row_id = int(row.get("ID") or 0)
        fid = int(row.get("FranchiseID") or 0)
        dt, time_str = _parse_datetime(row.get("AssessmentDate"), row.get("AssessmentTime"))
        if dt is None:
            continue
        msg = generate_message(
            franchise_id=fid,
            automation_stage=str(row.get("AutomationStage", "Assessment1")),
            parent_first_name=str(row.get("GuardianFirstName", "")),
            student_names=str(row.get("StudentString", "")),
            assessment_date=dt,
            assessment_time_str=time_str,
        )
        header = f"[assessment][scheduled] FID={fid} InquiryID={int(row.get('InquiryID') or 0)} Date={str(row.get('AssessmentDate') or '')} Time={str(row.get('AssessmentTime') or '')}"
        if dry_run:
            print({"mode": "scheduled", "entity": "assessment", "franchise_id": fid, "decision": "send", "dry_run": True})
            send_message(header + " [dry-run]", LOG_BOT, LOG_CHAT)
        else:
            # Atomic claim (No -> Sending) to prevent duplicates across concurrent runs
            if row_id and not claim_row_for_send(row_id):
                # Already claimed or sent elsewhere; skip
                print({
                    "mode": "scheduled",
                    "entity": "assessment",
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
                    # Roll back to pending on failure
                    revert_row_to_pending(row_id)
                    print({
                        "mode": "scheduled",
                        "entity": "assessment",
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
    """
    Morning-of confirmation pass (Assessment2). No local cache; rely on SQL filters.
    """
    df = fetch_assessment_data_morning(franchise_ids=franchise_ids, since=since, until=until, limit=limit)
    if df.empty:
        return 0
    sent = 0
    seen_inquiries: set[int] = set()

    # Group by InquiryID to ensure exactly one send per inquiry
    try:
        grouped = df.groupby("InquiryID", sort=False)
    except Exception:
        # Fallback if grouping fails for any reason: treat entire frame as one group per row InquiryID
        grouped = ((int(r.get("InquiryID") or 0), pd.DataFrame([r])) for _, r in df.iterrows())

    for inquiry_id, g in grouped:
        try:
            iid = int(inquiry_id) if inquiry_id is not None else 0
        except Exception:
            iid = 0
        if iid in seen_inquiries:
            # Belt-and-suspenders: skip duplicates within same run
            continue
        seen_inquiries.add(iid)

        # Pull representative fields from the first row
        first_row = g.iloc[0]
        fid = int(first_row.get("FranchiseID") or 0)
        dt, time_str = _parse_datetime(first_row.get("AssessmentDate"), first_row.get("AssessmentTime"))
        if dt is None:
            print({
                "mode": "morning",
                "entity": "assessment",
                "franchise_id": fid,
                "inquiry_id": iid,
                "decision": "skip_invalid_dt",
                "dry_run": dry_run,
            })
            continue

        # Aggregate and format student names via common handler
        raw_names = [str(x) for x in g.get("StudentString", []) if str(x).strip()]
        first_names: list[str] = parse_student_names(raw_names)
        formatted_names = format_student_names(first_names, max_names=4)

        parent_first = str(first_row.get("GuardianFirstName", ""))
        phone = str(first_row.get("AssessmentPhone", ""))

        # Pre-send DEBUG log
        print({
            "mode": "morning",
            "entity": "assessment",
            "stage": "Assessment2",
            "franchise_id": fid,
            "inquiry_id": iid,
            "student_names": formatted_names,
            "phone": phone,
            "dry_run": dry_run,
        })

        msg = generate_message(
            franchise_id=fid,
            automation_stage="Assessment2",
            parent_first_name=parent_first,
            student_names=formatted_names,
            assessment_date=dt,
            assessment_time_str=time_str,
        )
        header = (
            f"[assessment][morning] FID={fid} InquiryID={iid} "
            f"Date={str(first_row.get('AssessmentDate') or '')} "
            f"Time={str(first_row.get('AssessmentTime') or '')}"
        )
        if dry_run:
            print({"mode": "morning", "entity": "assessment", "franchise_id": fid, "inquiry_id": iid, "decision": "send", "dry_run": True})
            send_message(header + " [dry-run]", LOG_BOT, LOG_CHAT)
        else:
            send_message(header, LOG_BOT, LOG_CHAT)
            send_to_webhook(fid, msg, phone=phone)
            sent += 1
            time.sleep(sleep_seconds)
    return sent
