from __future__ import annotations

from typing import Iterable

import pandas as pd
from sqlalchemy import text

from ..reporting.sqlite_db import get_sqlite_engine


def _norm_ts(val: str | None) -> str:
    s = (str(val) if val is not None else "").strip()
    if not s:
        return ""
    if "." in s:
        s = s.split(".", 1)[0]
    return s


TABLE = "AssessmentCache"


def _ensure_assessment_id_column() -> None:
    """Add AssessmentID column if missing (for safe deletes by PK)."""
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        info = conn.execute(text(f"PRAGMA table_info({TABLE})")).fetchall()
        colnames = {row[1] for row in info}
        if "AssessmentID" not in colnames:
            conn.execute(text(f"ALTER TABLE {TABLE} ADD COLUMN AssessmentID INTEGER"))




def select_cache() -> pd.DataFrame:
    eng = get_sqlite_engine()
    with eng.connect() as conn:
        return pd.read_sql_query(text(f"SELECT * FROM {TABLE}"), conn)


def _get_existing(inquiry_id: int) -> dict | None:
    eng = get_sqlite_engine()
    with eng.connect() as conn:
        row = conn.execute(
            text(f"SELECT ID, AssessmentDate, AssessmentTime, IsText FROM {TABLE} WHERE InquiryID = :id"),
            {"id": int(inquiry_id)},
        ).first()
        return dict(row._mapping) if row else None


def upsert_from_server(df: pd.DataFrame) -> None:
    if df is None or df.empty:
        return
    _ensure_assessment_id_column()
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        for _, r in df.iterrows():
            inquiry_id = int(r.get("InquiryID"))
            student_str = str(r.get("StudentString") or "").strip()
            exists = conn.execute(
                text(
                    f"SELECT ID, AssessmentDate, AssessmentTime, IsText FROM {TABLE} WHERE InquiryID = :id AND StudentString = :student"
                ),
                {"id": inquiry_id, "student": student_str},
            ).first()
            date_str = _norm_ts(r.get("AssessmentDate"))
            time_str = _norm_ts(r.get("AssessmentTime"))
            params = {
                "AutomationStage": str(r.get("AutomationStage", "Assessment1")),
                "InquiryID": inquiry_id,
                "AssessmentID": int(r.get("AssessmentID")) if r.get("AssessmentID") is not None else None,
                "FranchiseID": int(r.get("FranchiseID")) if r.get("FranchiseID") is not None else None,
                "AssessmentDate": date_str,
                "AssessmentTime": time_str,
                "AssessmentEmail": str(r.get("AssessmentEmail") or ""),
                "AssessmentPhone": str(r.get("AssessmentPhone") or ""),
                "GuardianFirstName": str(r.get("GuardianFirstName") or ""),
                "StudentString": student_str,
            }
            if not exists:
                conn.execute(
                    text(
                        f"""
INSERT INTO {TABLE}
  (AutomationStage, InquiryID, AssessmentID, FranchiseID, AssessmentDate, AssessmentTime, AssessmentEmail, AssessmentPhone, GuardianFirstName, StudentString, IsText)
VALUES
  (:AutomationStage, :InquiryID, :AssessmentID, :FranchiseID, :AssessmentDate, :AssessmentTime, :AssessmentEmail, :AssessmentPhone, :GuardianFirstName, :StudentString, 'No')
                        """
                    ),
                    params,
                )
            else:
                prev_date = _norm_ts(exists._mapping.get("AssessmentDate"))
                prev_time = _norm_ts(exists._mapping.get("AssessmentTime"))
                # If date/time changed, reset IsText to 'No'
                reset = (prev_date != date_str) or (prev_time != time_str)
                new_istext = 'No' if reset else None
                conn.execute(
                    text(
                        f"""
UPDATE {TABLE}
SET AutomationStage=:AutomationStage,
    AssessmentID=:AssessmentID,
    FranchiseID=:FranchiseID,
    AssessmentDate=:AssessmentDate,
    AssessmentTime=:AssessmentTime,
    AssessmentEmail=:AssessmentEmail,
    AssessmentPhone=:AssessmentPhone,
    GuardianFirstName=:GuardianFirstName,
    StudentString=:StudentString,
    IsText=COALESCE(:_new_istext, IsText)
WHERE ID=:row_id
                        """
                    ),
                    {**params, "_new_istext": new_istext, "row_id": int(exists._mapping.get("ID"))},
                )


def delete_missing_sent_by_pk(server_pks: Iterable[int]) -> None:
    """Delete only rows with IsText='Yes' whose AssessmentID is missing from server."""
    _ensure_assessment_id_column()
    pks = [int(x) for x in server_pks if x is not None]
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        if pks:
            conn.execute(
                text(
                    f"DELETE FROM {TABLE} WHERE UPPER(IFNULL(IsText,'No'))='YES' AND (AssessmentID IS NULL OR AssessmentID NOT IN ({','.join(str(i) for i in pks)}))"
                )
            )
        else:
            # If no server PKs, do not delete anything to be safe
            pass


def pending_to_text() -> pd.DataFrame:
    eng = get_sqlite_engine()
    with eng.connect() as conn:
        # Exclude rows in transient 'Sending' state and dedupe by latest row per InquiryID
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
            # Some DBAPIs do not expose rowcount; perform a read to verify
            chk = conn.execute(
                text(f"SELECT IsText FROM {TABLE} WHERE ID=:id"), {"id": int(row_id)}
            ).first()
            return bool(chk and str(chk[0]).strip().lower() == "sending")


def revert_row_to_pending(row_id: int) -> None:
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        conn.execute(text(f"UPDATE {TABLE} SET IsText='No' WHERE ID=:id"), {"id": int(row_id)})
