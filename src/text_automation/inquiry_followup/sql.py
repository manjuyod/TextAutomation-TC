from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

import pandas as pd
from sqlalchemy import text

from ..db.sql import get_engine


INQUIRY_SQL = """
SELECT * FROM (
    SELECT DISTINCT
        tblInquiry.ID AS [InquiryID],
        tblInquiry.CFirstName AS [CFirstName],
        tblInquiryStudents.FirstName AS [StudentFirstName],
        tblInquiry.Date AS [DateInput],
        tblInquiry.FranchiesId AS [FranchiseID],
        tblInquiry.ContactPhone AS [ContactPhone],
        tblInquiry.Email AS [Email],
        tblStudents.HomeAddress AS [HomeAddress],
        CASE
            WHEN EXISTS (
                SELECT 1 FROM tblStudents 
                WHERE tblStudents.InquiryId = tblInquiry.Id 
                  AND (tblStudents.ID IS NOT NULL AND tblStudents.ID <> '')
            ) AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 1 THEN 'Enrolled'
            WHEN tblMeetings.MeetingFollowUp = 1 AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 0 THEN 'Meeting Follow Up'
            WHEN tblMeetings.CFirstName <> '' AND tblMeetings.Time <> '' AND tblMeetings.MeetingFollowUp = 0 AND tblMeetings.isDeleted = 0 AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 0 THEN 'Meeting'
            WHEN tblAssessments.CFirstName <> '' AND tblAssessments.Time <> '' AND tblAssessments.isDeleted = 0 AND tblAssessments.AssessmentCom = 0 AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 0 THEN 'Assessment'
            WHEN tblInquiry.isDirect = 0 AND tblInquiry.IsDeleted = 0 AND tblInquiry.PhoneFollowUp = 'Inquiry' AND tblMeetings.MeetingFollowUp = 0 THEN 'Inquiry'
            WHEN tblInquiry.isDirect = 0 AND tblInquiry.IsDeleted = 0 AND tblInquiry.PhoneFollowUp = 'Lead' THEN 'Lead'
            WHEN tblInquiry.IsDeleted = 1 THEN 'Deleted'
            ELSE 'Other'
        END AS [Status]
    FROM tblInquiry
    LEFT JOIN tblMeetings ON tblInquiry.Id = tblMeetings.InquiryId
    LEFT JOIN tblAssessments ON tblInquiry.Id = tblAssessments.InquiryId
    LEFT JOIN tblInvoiceStudents ON tblInquiry.Id = tblInvoiceStudents.InquiryId
    LEFT JOIN tblStudents ON tblInquiry.Id = tblStudents.InquiryId
    LEFT JOIN tblInquiryStudents ON tblInquiry.ID = tblInquiryStudents.InquiryID
    WHERE tblInquiry.FranchiesId IN ({franchise_clause})
      AND tblInquiry.Date >= :lower_bound
      AND tblInquiry.Date <= :upper_bound
      AND tblInquiry.ContactPhone IS NOT NULL AND tblInquiry.ContactPhone <> ''
) AS SubQuery
WHERE SubQuery.Status IN ('Inquiry', 'Lead')
ORDER BY SubQuery.[DateInput] ASC
OFFSET :offset ROWS FETCH NEXT :chunk_size ROWS ONLY
"""


def _build_franchise_clause(franchise_ids: Iterable[int] | None = None) -> str:
    ids = [int(x) for x in (franchise_ids or [87, 49]) if x is not None]
    if not ids:
        ids = [87, 49]
    return ",".join(str(int(x)) for x in ids)


def _build_bounds(
    *,
    since: str | None = None,
    lookback_days: int = 90,
    min_age_days: int = 7,
) -> tuple[str, str]:
    today = datetime.now().date()
    if since:
        lower_bound = str(since)
    else:
        lower_bound = (today - timedelta(days=max(int(lookback_days), 0))).isoformat()
    upper_bound = (today - timedelta(days=max(int(min_age_days), 0))).isoformat()
    return lower_bound, upper_bound


def fetch_inquiries(
    franchise_ids: Iterable[int] | None = None,
    *,
    since: str | None = None,
    lookback_days: int = 90,
    min_age_days: int = 7,
    chunk_size: int = 250,
) -> pd.DataFrame:
    franchise_clause = _build_franchise_clause(franchise_ids)
    lower_bound, upper_bound = _build_bounds(
        since=since, lookback_days=lookback_days, min_age_days=min_age_days
    )

    q = INQUIRY_SQL.format(franchise_clause=franchise_clause)
    params = {
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "chunk_size": int(chunk_size) if int(chunk_size) > 0 else 250,
        "offset": 0,
    }

    engine = get_engine()
    chunks: list[pd.DataFrame] = []
    with engine.connect() as conn:
        while True:
            chunk = pd.read_sql_query(text(q), conn, params=params)
            if chunk.empty:
                break
            chunks.append(chunk)
            params["offset"] += len(chunk)
            if len(chunk) < params["chunk_size"]:
                break

    if not chunks:
        return pd.DataFrame()
    return pd.concat(chunks, ignore_index=True)
