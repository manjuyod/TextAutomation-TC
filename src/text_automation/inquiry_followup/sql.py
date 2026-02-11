from __future__ import annotations

from text_automation.db.sql import get_db_data


INQUIRY_SQL = """
SELECT * FROM (
    SELECT DISTINCT
        tblInquiry.ID AS [InquiryID],
        tblInquiry.CFirstName AS [CFirstName],
        tblInquiryStudents.FirstName AS [StudentFirstName],
        tblInquiry.Date AS [DateInput],
        tblInquiry.ContactPhone AS [ContactPhone],
        tblInquiry.Email AS [Email],
        tblStudents.HomeAddress AS [HomeAddress],
        CASE
            WHEN tblStudents.Grade IS NOT NULL AND tblStudents.Grade <> '' THEN tblStudents.Grade
            ELSE tblInquiryStudents.Grade
        END AS [Grade],
        tblFranchies.FranchiesName AS [FranchiseName],
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
    LEFT JOIN tblFranchies ON tblInquiry.FranchiesId = tblFranchies.ID
    WHERE tblInquiry.FranchiesId = :franchise_id
      AND tblInquiry.Date >= DATEADD(MONTH, -:months_back, CAST(GETDATE() AS date))
      AND tblInquiry.Date <= GETDATE()
      AND tblInquiry.ContactPhone IS NOT NULL AND tblInquiry.ContactPhone <> ''
) AS SubQuery
WHERE SubQuery.Status = 'Inquiry'
ORDER BY SubQuery.[DateInput] ASC
"""


def fetch_inquiries(franchise_id: int, months_back: int = 3, limit: int | None = None):
    sql = INQUIRY_SQL
    if limit is not None:
        # Insert TOP into the inner SELECT DISTINCT to bound the result size
        sql = sql.replace(
            "SELECT DISTINCT\n        tblInquiry.ID AS [InquiryID]",
            f"SELECT DISTINCT TOP {int(limit)}\n        tblInquiry.ID AS [InquiryID]",
            1,
        )
    params = {"franchise_id": int(franchise_id), "months_back": int(months_back)}
    return get_db_data(sql, params)

