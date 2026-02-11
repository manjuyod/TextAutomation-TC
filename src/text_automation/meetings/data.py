from __future__ import annotations

import pandas as pd
from sqlalchemy import text

from ..db.sql import get_engine


def fetch_meeting_data() -> pd.DataFrame:
    q = text(
        """
SELECT TOP 100
    'Meeting1' AS AutomationStage,
    m.InquiryID,
    (SELECT TOP 1 FranchiesId FROM tblInquiry WHERE ID = m.InquiryID) AS FranchiseID,
    m.ID AS MeetingID,
    m.Date AS MeetingDate,
    m.Time AS MeetingTime,
    m.ContactEmail AS AssessmentEmail,
    m.ContactNumber AS AssessmentPhone,
    CONVERT(date, GETDATE()) AS CurrentDate,
    m.CFirstName AS GuardianFirstName,
    m.StudentNames AS StudentString,
    (SELECT MAX(Grade) FROM tblInquiryStudents WHERE InquiryID = m.InquiryID) AS Grade,
    (SELECT TOP 1 LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.FatherName))
       FROM dpinket_TC_QA.dbo.tblTempStudentAuto
       WHERE dpinket_TC_QA.dbo.tblTempStudentAuto.InquiryID = m.InquiryID
         AND NULLIF(LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.FatherName)), '') IS NOT NULL
       ORDER BY dpinket_TC_QA.dbo.tblTempStudentAuto.ID DESC) AS Parent1Name,
    (SELECT TOP 1 LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.MotherName))
       FROM dpinket_TC_QA.dbo.tblTempStudentAuto
       WHERE dpinket_TC_QA.dbo.tblTempStudentAuto.InquiryID = m.InquiryID
         AND NULLIF(LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.MotherName)), '') IS NOT NULL
       ORDER BY dpinket_TC_QA.dbo.tblTempStudentAuto.ID DESC) AS Parent2Name
FROM tblMeetings m
WHERE m.InquiryID IN (
    SELECT ID FROM tblInquiry
    WHERE FranchiesId IN (1, 2, 3, 6, 11, 15, 16, 19, 24, 20, 60, 57, 87, 103)
)
AND NOT EXISTS (
    SELECT 1 FROM tblAssessments a
    WHERE a.InquiryID = m.InquiryID
      AND a.Date = m.Date
      AND a.IsDeleted = 0
      AND a.Time IS NOT NULL
      AND a.Time <> '00:00:00.0000000'
)
AND m.IsDeleted = 0
AND m.MeetingFollowUp = 0
AND m.Date >= DATEADD(HOUR, -1, CAST(CAST(GETDATE() AS DATE) AS DATETIME))
AND m.Time IS NOT NULL
AND m.Time <> '00:00:00.0000000'
        """
    )
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql_query(q, conn)
    return df


def fetch_meeting_data_morning(
    franchise_ids: list[int] | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int | None = None,
) -> pd.DataFrame:
    """
    Morning-of window for meetings (Meeting2 in legacy naming).
    Exclude rows that overlap with assessments on the same date, mirror legacy.
    """
    where_parts = [
        "m.IsDeleted = 0",
        "m.Time IS NOT NULL",
        "m.Time <> '00:00:00.0000000'",
        "NOT EXISTS (SELECT 1 FROM tblAssessments a WHERE a.InquiryID = m.InquiryID AND a.Date = m.Date AND a.IsDeleted = 0 AND a.Time IS NOT NULL AND a.Time <> '00:00:00.0000000')",
    ]
    params: dict = {}
    if since and until:
        where_parts.append("m.Date >= :since AND m.Date <= :until")
        params["since"] = since
        params["until"] = until
    else:
        where_parts.append(
            "m.Date > CAST(DATEADD(DAY, -1, GETDATE()) AS DATE) AND m.Date < CAST(DATEADD(DAY, 1, GETDATE()) AS DATE)"
        )
    if franchise_ids:
        in_clause = ",".join(str(int(x)) for x in franchise_ids)
        where_parts.append(
            f"m.InquiryID IN (SELECT ID FROM tblInquiry WHERE FranchiesId IN ({in_clause}))"
        )
    where_sql = " AND ".join(where_parts)
    top = f"TOP {int(limit)}" if limit else ""
    q = text(
        f"""
SELECT {top}
    'Meeting2' AS AutomationStage,
    m.InquiryID,
    (SELECT TOP 1 FranchiesId FROM tblInquiry WHERE ID = m.InquiryID) AS FranchiseID,
    m.ID AS MeetingID,
    m.Date AS MeetingDate,
    m.Time AS MeetingTime,
    m.ContactEmail AS AssessmentEmail,
    m.ContactNumber AS AssessmentPhone,
    CONVERT(date, GETDATE()) AS CurrentDate,
    m.CFirstName AS GuardianFirstName,
    m.StudentNames AS StudentString,
    (SELECT MAX(Grade) FROM tblInquiryStudents WHERE InquiryID = m.InquiryID) AS Grade,
    (SELECT TOP 1 LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.FatherName))
       FROM dpinket_TC_QA.dbo.tblTempStudentAuto
       WHERE dpinket_TC_QA.dbo.tblTempStudentAuto.InquiryID = m.InquiryID
         AND NULLIF(LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.FatherName)), '') IS NOT NULL
       ORDER BY dpinket_TC_QA.dbo.tblTempStudentAuto.ID DESC) AS Parent1Name,
    (SELECT TOP 1 LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.MotherName))
       FROM dpinket_TC_QA.dbo.tblTempStudentAuto
       WHERE dpinket_TC_QA.dbo.tblTempStudentAuto.InquiryID = m.InquiryID
         AND NULLIF(LTRIM(RTRIM(dpinket_TC_QA.dbo.tblTempStudentAuto.MotherName)), '') IS NOT NULL
       ORDER BY dpinket_TC_QA.dbo.tblTempStudentAuto.ID DESC) AS Parent2Name
FROM tblMeetings m
WHERE {where_sql}
ORDER BY m.Date DESC, m.Time DESC
        """
    )
    eng = get_engine()
    with eng.connect() as conn:
        df = pd.read_sql_query(q, conn, params=params)
    return df
