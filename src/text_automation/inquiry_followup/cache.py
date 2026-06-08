from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pandas as pd
from sqlalchemy import text

from ..reporting.sqlite_db import get_sqlite_engine


TABLE = "InquiryFollowupCache"


def _normalize_ts(value: str | None) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    return s.split(".")[0]


def select_cache() -> pd.DataFrame:
    eng = get_sqlite_engine()
    try:
        with eng.connect() as conn:
            return pd.read_sql_query(text(f"SELECT * FROM {TABLE}"), conn)
    finally:
        eng.dispose()


def _find_by_inquiry_id(conn, inquiry_id: int):
    return conn.execute(
        text(f"SELECT * FROM {TABLE} WHERE InquiryID = :id"), {"id": int(inquiry_id)}
    ).first()


def upsert_from_server(df: pd.DataFrame, message_variant: str = "standard") -> None:
    if df is None or df.empty:
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    eng = get_sqlite_engine()
    try:
        with eng.begin() as conn:
            for _, row in df.iterrows():
                inquiry_id = int(row.get("InquiryID"))
                inquiry_date = _normalize_ts(row.get("DateInput"))
                if not inquiry_date:
                    inquiry_date = _normalize_ts(row.get("InquiryDate"))
                payload = {
                    "InquiryID": inquiry_id,
                    "FranchiseID": int(row.get("FranchiseID")) if row.get("FranchiseID") is not None else None,
                    "InquiryDate": inquiry_date,
                    "ContactFirstName": str(row.get("CFirstName") or row.get("ContactFirstName") or "").strip(),
                    "StudentFirstName": str(row.get("StudentFirstName") or row.get("StudentString") or "").strip(),
                    "ContactPhone": str(row.get("ContactPhone") or "").strip(),
                    "ContactEmail": str(
                        row.get("ContactEmail")
                        if row.get("ContactEmail") is not None and str(row.get("ContactEmail")).strip()
                        else row.get("Email")
                        or ""
                    ).strip(),
                    "MessageVariant": str(row.get("MessageVariant") or message_variant or "standard").strip() or "standard",
                    "UpdatedAt": now,
                }
                existing = _find_by_inquiry_id(conn, inquiry_id)
                if existing is None:
                    conn.execute(
                        text(
                            f"""
INSERT INTO {TABLE}
  (InquiryID, FranchiseID, InquiryDate, ContactFirstName, StudentFirstName, ContactPhone, ContactEmail, MessageVariant, IsText, UpdatedAt)
VALUES
  (:InquiryID, :FranchiseID, :InquiryDate, :ContactFirstName, :StudentFirstName, :ContactPhone, :ContactEmail, :MessageVariant, 'No', :UpdatedAt)
                        """
                        ),
                        payload,
                    )
                    continue

                previous = existing._mapping
                payload["IsText"] = str(previous.get("IsText") or "No")
                payload["ID"] = int(previous.get("ID"))
                conn.execute(
                    text(
                        f"""
UPDATE {TABLE}
SET FranchiseID=:FranchiseID,
    InquiryDate=:InquiryDate,
    ContactFirstName=:ContactFirstName,
    StudentFirstName=:StudentFirstName,
    ContactPhone=:ContactPhone,
    ContactEmail=:ContactEmail,
    MessageVariant=:MessageVariant,
    IsText=:IsText,
    UpdatedAt=:UpdatedAt
WHERE ID=:ID
                    """
                    ),
                    payload,
                )
    finally:
        eng.dispose()


def pending_to_text(
    lower_bound: str | None = None,
    upper_bound: str | None = None,
    franchise_ids: list[int] | None = None,
) -> pd.DataFrame:
    conditions = [
        "UPPER(TRIM(IFNULL(IsText,'No'))) = 'NO'"
    ]
    params: dict[str, object] = {}
    if lower_bound is not None:
        conditions.append("InquiryDate >= :lower_bound")
        params["lower_bound"] = str(lower_bound)
    if upper_bound is not None:
        conditions.append("InquiryDate <= :upper_bound")
        params["upper_bound"] = str(upper_bound)
    if franchise_ids:
        ids = [int(x) for x in franchise_ids if x]
        if ids:
            id_tokens = [str(x) for x in ids]
            conditions.append(f"FranchiseID IN ({','.join(id_tokens)})")
    where_sql = " AND ".join(conditions)

    eng = get_sqlite_engine()
    try:
        with eng.connect() as conn:
            return pd.read_sql_query(
                text(f"SELECT * FROM {TABLE} WHERE {where_sql} ORDER BY InquiryDate ASC, ID ASC"),
                conn,
                params=params,
            )
    finally:
        eng.dispose()


def mark_text_sent(inquiry_ids: Iterable[int]) -> None:
    ids = [int(x) for x in inquiry_ids if x is not None]
    if not ids:
        return
    eng = get_sqlite_engine()
    try:
        with eng.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {TABLE} SET IsText='Yes', TextedAtUtc=CURRENT_TIMESTAMP WHERE InquiryID IN ({','.join(str(i) for i in ids)})"
                )
            )
    finally:
        eng.dispose()


def mark_text_sent_by_row_ids(row_ids: Iterable[int]) -> None:
    ids = [int(x) for x in row_ids if x is not None]
    if not ids:
        return
    eng = get_sqlite_engine()
    try:
        with eng.begin() as conn:
            conn.execute(
                text(
                    f"UPDATE {TABLE} SET IsText='Yes', TextedAtUtc=CURRENT_TIMESTAMP WHERE ID IN ({','.join(str(i) for i in ids)})"
                )
            )
    finally:
        eng.dispose()


def claim_row_for_send(row_id: int) -> bool:
    eng = get_sqlite_engine()
    try:
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
                state = conn.execute(text(f"SELECT IsText FROM {TABLE} WHERE ID=:id"), {"id": int(row_id)}).first()
                return bool(state and str(state[0]).strip().lower() == "sending")
    finally:
        eng.dispose()


def revert_row_to_pending(row_id: int) -> None:
    eng = get_sqlite_engine()
    try:
        with eng.begin() as conn:
            conn.execute(
                text(f"UPDATE {TABLE} SET IsText='No' WHERE ID=:id"),
                {"id": int(row_id)},
            )
    finally:
        eng.dispose()
