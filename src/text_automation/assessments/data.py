from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from ..config import load_config
from ..db.sql import get_engine


def _configured_franchise_ids_sql() -> str:
    cfg = load_config()
    franchise_ids = sorted({int(f.id) for f in cfg.franchises if not f.direct_inquiry_only})
    return ",".join(str(fid) for fid in franchise_ids)


def fetch_assessment_data() -> pd.DataFrame:
    """
    Pull recent scheduled assessments from SQL Server with normalized columns.
    Mirrors legacy Assessment1DataCollectionsOnly.fetch_assessment_data.
    """
    franchise_ids_sql = _configured_franchise_ids_sql()
    q = text(
        f"""
SELECT TOP 150
    'Assessment1' AS AutomationStage,
    a.ID AS AssessmentID,
    a.InquiryID AS InquiryID,
    (SELECT TOP 1 FranchiesId FROM tblInquiry WHERE ID = a.InquiryID) AS FranchiseID,
    a.Date AS AssessmentDate,
    a.Time AS AssessmentTime,
    (SELECT TOP 1 Email FROM tblInquiry WHERE ID = a.InquiryID) AS AssessmentEmail,
    (SELECT TOP 1 ContactPhone FROM tblInquiry WHERE ID = a.InquiryID) AS AssessmentPhone,
    a.CFirstName AS GuardianFirstName,
    a.SFirstName AS StudentString
FROM tblAssessments a
WHERE a.InquiryID IN (
    SELECT ID FROM tblInquiry
    WHERE FranchiesId IN ({franchise_ids_sql})
)
AND a.IsDeleted = 0
AND a.Time IS NOT NULL
AND a.Time <> '00:00:00.0000000'
AND a.Date >= DATEADD(HOUR, -1, CAST(CAST(GETDATE() AS DATE) AS DATETIME))
ORDER BY a.Date DESC, a.Time DESC
        """
    )
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql_query(q, conn)
    # Ensure types reasonable
    if not df.empty:
        # Normalize guardian first name (strip)
        df["GuardianFirstName"] = df["GuardianFirstName"].astype(str).str.strip()
    return df


def fetch_assessment_data_morning(
    franchise_ids: list[int] | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Morning-of window for assessments, mark stage as Assessment2.
    Uses a date slice around GETDATE() by default (yesterday..tomorrow) to capture "today".
    Accepts optional ISO8601 strings for since/until to override server time.
    """
    where_parts = [
        "a.IsDeleted = 0",
        "a.AssessmentCom = 0",
        "a.Time IS NOT NULL",
        "a.Time <> '00:00:00.0000000'",
    ]
    params: dict = {}
    if since and until:
        where_parts.append("a.Date >= :since AND a.Date <= :until")
        params["since"] = since
        params["until"] = until
    else:
        where_parts.append(
            "a.Date > CAST(DATEADD(DAY, -1, GETDATE()) AS DATE) AND a.Date < CAST(DATEADD(DAY, 1, GETDATE()) AS DATE)"
        )
    if franchise_ids:
        in_clause = ",".join(str(int(x)) for x in franchise_ids)
        where_parts.append(
            f"a.InquiryID IN (SELECT ID FROM tblInquiry WHERE FranchiesId IN ({in_clause}))"
        )
    where_sql = " AND ".join(where_parts)
    top = f"TOP {int(limit)}" if limit else ""
    q = text(
        f"""
SELECT {top}
    'Assessment2' AS AutomationStage,
    a.ID AS AssessmentID,
    a.InquiryID AS InquiryID,
    (SELECT TOP 1 FranchiesId FROM tblInquiry WHERE ID = a.InquiryID) AS FranchiseID,
    a.Date AS AssessmentDate,
    a.Time AS AssessmentTime,
    (SELECT TOP 1 Email FROM tblInquiry WHERE ID = a.InquiryID) AS AssessmentEmail,
    (SELECT TOP 1 ContactPhone FROM tblInquiry WHERE ID = a.InquiryID) AS AssessmentPhone,
    a.CFirstName AS GuardianFirstName,
    a.SFirstName AS StudentString
FROM tblAssessments a
WHERE {where_sql}
ORDER BY a.Date DESC, a.Time DESC
        """
    )
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql_query(q, conn, params=params)
    return df
