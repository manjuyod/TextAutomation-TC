from __future__ import annotations

from typing import Iterable

import pandas as pd
from sqlalchemy import text

from ..reporting.sqlite_db import get_sqlite_engine


TABLE = "MeetingCache"


def _norm_ts(val: str | None) -> str:
    s = (str(val) if val is not None else "").strip()
    if not s:
        return ""
    if "." in s:
        s = s.split(".", 1)[0]
    return s

def select_cache() -> pd.DataFrame:
    eng = get_sqlite_engine()
    with eng.connect() as conn:
        return pd.read_sql_query(text(f"SELECT * FROM {TABLE}"), conn)


def upsert_from_server(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    _ensure_unique_indexes()
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        for _, r in df.iterrows():
            inquiry_id = int(r.get("InquiryID"))
            student_str = str(r.get("StudentString") or "").strip()
            exists = conn.execute(
                text(f"SELECT ID, MeetingDate, MeetingTime, IsText FROM {TABLE} WHERE InquiryID = :id AND StudentString = :student"),
                {"id": inquiry_id, "student": student_str},
            ).first()
            d = _norm_ts(r.get("MeetingDate"))
            t = _norm_ts(r.get("MeetingTime"))
            params = {
                "AutomationStage": str(r.get("AutomationStage", "Meeting1")),
                "InquiryID": inquiry_id,
                "FranchiseID": int(r.get("FranchiseID")) if r.get("FranchiseID") is not None else None,
                "MeetingID": int(r.get("MeetingID")) if r.get("MeetingID") is not None else None,
                "MeetingDate": d,
                "MeetingTime": t,
                "AssessmentEmail": str(r.get("AssessmentEmail") or ""),
                "AssessmentPhone": str(r.get("AssessmentPhone") or ""),
                "CurrentDate": str(r.get("CurrentDate") or ""),
                "GuardianFirstName": str(r.get("GuardianFirstName") or ""),
                "StudentString": student_str,
                "Grade": str(r.get("Grade")) if r.get("Grade") is not None else None,
                "Parent1Name": str(r.get("Parent1Name")) if r.get("Parent1Name") is not None else None,
                "Parent2Name": str(r.get("Parent2Name")) if r.get("Parent2Name") is not None else None,
            }
            if not exists:
                conn.execute(
                    text(
                        f"""
INSERT INTO {TABLE}
  (AutomationStage, InquiryID, FranchiseID, MeetingID, MeetingDate, MeetingTime, AssessmentEmail, AssessmentPhone, CurrentDate, GuardianFirstName, StudentString, Grade, Parent1Name, Parent2Name, IsText)
VALUES
  (:AutomationStage, :InquiryID, :FranchiseID, :MeetingID, :MeetingDate, :MeetingTime, :AssessmentEmail, :AssessmentPhone, :CurrentDate, :GuardianFirstName, :StudentString, :Grade, :Parent1Name, :Parent2Name, 'No')
                        """
                    ),
                    params,
                )
            else:
                prev_d = _norm_ts(exists._mapping.get("MeetingDate"))
                prev_t = _norm_ts(exists._mapping.get("MeetingTime"))
                reset = (prev_d != d) or (prev_t != t)
                new_istext = 'No' if reset else None
                conn.execute(
                    text(
                        f"""
UPDATE {TABLE}
SET AutomationStage=:AutomationStage,
    FranchiseID=:FranchiseID,
    MeetingID=:MeetingID,
    MeetingDate=:MeetingDate,
    MeetingTime=:MeetingTime,
    AssessmentEmail=:AssessmentEmail,
    AssessmentPhone=:AssessmentPhone,
    CurrentDate=:CurrentDate,
    GuardianFirstName=:GuardianFirstName,
    StudentString=:StudentString,
    Grade=:Grade,
    Parent1Name=:Parent1Name,
    Parent2Name=:Parent2Name,
    IsText=COALESCE(:_new_istext, IsText)
WHERE ID=:row_id
                        """
                    ),
                    {**params, "_new_istext": new_istext, "row_id": int(exists._mapping.get("ID"))},
                )


def delete_not_in(server_ids: Iterable[int]) -> None:
    # Deprecated by delete_missing_sent_by_pk; keeping stub to avoid import errors if any
    return


def pending_to_text() -> pd.DataFrame:
    eng = get_sqlite_engine()
    with eng.connect() as conn:
        q = text(
            f"""
SELECT * FROM {TABLE}
WHERE UPPER(TRIM(IFNULL(IsText,'No'))) = 'NO'
  AND ID IN (
      SELECT MAX(ID) FROM {TABLE} GROUP BY InquiryID
  )
            """
        )
        return pd.read_sql_query(q, conn)


def mark_text_sent(inquiry_ids: Iterable[int]) -> None:
    ids = [int(x) for x in inquiry_ids]
    if not ids:
        return
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        conn.execute(text(f"UPDATE {TABLE} SET IsText = 'Yes' WHERE InquiryID IN ({','.join(str(i) for i in ids)})"))


def delete_missing_sent_by_pk(server_pks: Iterable[int]) -> None:
    """Delete only rows with IsText='Yes' whose MeetingID is missing from server."""
    pks = [int(x) for x in server_pks if x is not None]
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        if pks:
            conn.execute(
                text(
                    f"DELETE FROM {TABLE} WHERE UPPER(TRIM(IFNULL(IsText,'No')))='YES' AND (MeetingID IS NULL OR MeetingID NOT IN ({','.join(str(i) for i in pks)}))"
                )
            )
        else:
            # No server PKs provided; skip deletion to be safe
            pass


def _ensure_unique_indexes() -> None:
    # Index creation disabled; gating uses InquiryID + StudentString
    return


def mark_text_sent_by_row_ids(row_ids: Iterable[int]) -> None:
    row_ids = [int(x) for x in row_ids]
    if not row_ids:
        return
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        conn.execute(text(f"UPDATE {TABLE} SET IsText = 'Yes' WHERE ID IN ({','.join(str(i) for i in row_ids)})"))


def claim_row_for_send(row_id: int) -> bool:
    """Atomically transition a row from 'No' to 'Sending'. Returns True if claimed."""
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        res = conn.execute(
            text(
                f"UPDATE {TABLE} SET IsText='Sending' WHERE ID=:id AND UPPER(TRIM(IFNULL(IsText,'No')))='NO'"
            ),
            {"id": int(row_id)},
        )
        try:
            return bool(res.rowcount)
        except Exception:
            chk = conn.execute(text(f"SELECT IsText FROM {TABLE} WHERE ID=:id"), {"id": int(row_id)}).first()
            return bool(chk and str(chk[0]).strip().lower() == "sending")


def revert_row_to_pending(row_id: int) -> None:
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        conn.execute(text(f"UPDATE {TABLE} SET IsText='No' WHERE ID=:id"), {"id": int(row_id)})
