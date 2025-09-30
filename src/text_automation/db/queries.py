from __future__ import annotations


def distilled_attendance_query(franchise_id: int) -> str:
    return f"""
SELECT * FROM (
  /* MASTER SCHEDULE */
  SELECT
    (SELECT CONCAT(FirstName,' ',LastName) FROM tblStudents WHERE ID = ms.StudentID1) AS StudentName,
    (SELECT CONCAT(CFirstName,' ',CLastName)
       FROM tblInquiry
       WHERE ID = (
         SELECT InquiryId FROM tblStudents WHERE ID = ms.StudentID1
       )
    ) AS ParentName,
    NULL AS PastSession, '' AS PastSessionTime, '' AS Attendance,
    '' AS UpcomingSession, '' AS UpcomingSessionTime,
    ms.Day AS MasterSession,
    (SELECT CONVERT(VARCHAR(30),t.Time,100) FROM tblTimes t WHERE t.ID = ms.TimeID) AS MasterSessionTime
  FROM tblMasterSchedule ms
  WHERE ms.FranchiseID = {franchise_id}

  UNION ALL

  /* PAST ATTENDANCE */
  SELECT
    (SELECT CONCAT(FirstName,' ',LastName) FROM tblStudents WHERE ID = a.StudentId) AS StudentName,
    (SELECT CONCAT(CFirstName,' ',CLastName)
       FROM tblInquiry
       WHERE ID = (
         SELECT InquiryId FROM tblStudents WHERE ID = a.StudentId
       )
    ) AS ParentName,
    a.Day AS PastSession,
    (SELECT CONVERT(VARCHAR(30),t.Time,100) FROM tblTimes t WHERE t.ID = a.TimeId) AS PastSessionTime,
    a.Attendance,
    '' AS UpcomingSession, '' AS UpcomingSessionTime,
    '' AS MasterSession, '' AS MasterSessionTime
  FROM tblAttendance a
  WHERE a.FranchiseID = {franchise_id}
    AND a.Day <= GETDATE()

  UNION ALL

  /* UPCOMING SESSIONS */
  SELECT
    (SELECT CONCAT(FirstName,' ',LastName) FROM tblStudents WHERE ID = s.StudentId1) AS StudentName,
    (SELECT CONCAT(CFirstName,' ',CLastName)
       FROM tblInquiry
       WHERE ID = (
         SELECT InquiryId FROM tblStudents WHERE ID = s.StudentID1
       )
    ) AS ParentName,
    NULL AS PastSession, '' AS PastSessionTime, '' AS Attendance,
    CONVERT(VARCHAR(10), s.ScheduleDate, 120) AS UpcomingSession,
    (SELECT CONVERT(VARCHAR(30),t.Time,100) FROM tblTimes t WHERE t.ID = s.TimeID) AS UpcomingSessionTime,
    '' AS MasterSession, '' AS MasterSessionTime
  FROM tblSessionSchedule s
  WHERE s.FranchiseID = {franchise_id}
    AND s.ScheduleDate > GETDATE()
) AS RESULTSET
ORDER BY
  UpcomingSession ASC,
  PastSession ASC,
  MasterSession ASC,
  MasterSessionTime ASC;
"""


def contact_info_active_not_deleted(franchise_id: int) -> str:
    return f"""SELECT
	InquiryID AS AccountNumber,
	CONCAT(FirstName, ' ', LastName) AS StudentName,
	(SELECT FranchiesName FROM tblFranchies WHERE tblFranchies.ID = tblStudents.FranchiseID) AS Center,
	Grade,
	(SELECT CONCAT(CFirstName, ' ', CLastName) FROM tblInquiry WHERE tblInquiry.ID = tblStudents.InquiryId) AS ParentName,
	(SELECT Email FROM tblInquiry WHERE tblInquiry.ID = tblStudents.InquiryId) AS Email,
	(SELECT ContactPhone FROM tblInquiry WHERE tblInquiry.ID = tblStudents.InquiryId) AS Phone
FROM tblStudents
WHERE FranchiseID IN {franchise_id}
AND IsTrail = 'Active'
AND IsDeleted = 0
"""


def contact_info_inactive(franchise_id: int) -> str:
    return f"""SELECT
	InquiryID AS AccountNumber,
	CONCAT(FirstName, ' ', LastName) AS StudentName,
	(SELECT FranchiesName FROM tblFranchies WHERE tblFranchies.ID = tblStudents.FranchiseID) AS Center,
	Grade,
	(SELECT CONCAT(CFirstName, ' ', CLastName) FROM tblInquiry WHERE tblInquiry.ID = tblStudents.InquiryId) AS ParentName,
	(SELECT Email FROM tblInquiry WHERE tblInquiry.ID = tblStudents.InquiryId) AS Email,
	(SELECT ContactPhone FROM tblInquiry WHERE tblInquiry.ID = tblStudents.InquiryId) AS Phone
FROM tblStudents
WHERE FranchiseID IN (6, 8, 11, 13, 15, 16, 19, 20, 22, 24, 49, 56, 57, 60, 87)
AND IsTrail = 'Inactive'
"""


def grab_inquiry_phone_four_months(franchise_id: int) -> str:
    return f"""WITH SubQuery AS (
	    SELECT DISTINCT
        tblInquiry.ID AS 'Acccount Number',
		tblInquiry.CfirstName AS 'Parent Name',
		tblInquiry.ContactPhone AS 'Phone',
        CASE
            WHEN EXISTS (
                SELECT 1 
                FROM tblStudents 
                WHERE tblStudents.InquiryId = tblInquiry.Id 
                AND (tblStudents.ID IS NOT NULL OR tblStudents.ID <> '')
            ) AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 1 THEN 'Enrolled'
            WHEN tblMeetings.MeetingFollowUp = 1 AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 0 THEN 'Meeting Follow Up'
            WHEN tblMeetings.CFirstName <> '' AND tblMeetings.Time <> '' AND tblMeetings.MeetingFollowUp = 0 AND tblMeetings.isDeleted = 0 AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 0 THEN 'Meeting'
            WHEN tblAssessments.CFirstName <> '' AND tblAssessments.Time <> '' AND tblAssessments.isDeleted = 0 AND tblAssessments.AssessmentCom = 0 AND tblInquiry.isDirect = 0 AND tblInquiry.isDeleted = 0 THEN 'Assessment'
            WHEN tblInquiry.isDirect = 0 AND tblInquiry.IsDeleted = 0 AND tblInquiry.PhoneFollowUp = 'Inquiry' AND tblMeetings.MeetingFollowUp = 0 THEN 'Inquiry'
            WHEN tblInquiry.isDirect = 0 AND tblInquiry.IsDeleted = 0 AND tblInquiry.PhoneFollowUp = 'Lead' THEN 'Lead'
            WHEN tblInquiry.IsDeleted = 1 THEN 'Deleted'
            ELSE 'Other'
        END AS 'Status'
    FROM tblInquiry
    LEFT JOIN tblMeetings ON tblInquiry.Id = tblMeetings.InquiryId
    LEFT JOIN tblAssessments ON tblInquiry.Id = tblAssessments.InquiryId
    LEFT JOIN tblInvoiceStudents ON tblInquiry.Id = tblInvoiceStudents.InquiryId
    LEFT JOIN tblStudents ON tblInquiry.Id = tblStudents.InquiryId
	LEFT JOIN tblInquiryStudents ON tblInquiry.ID = tblInquiryStudents.InquiryID
    WHERE tblInquiry.FranchiesId = 6
	AND tblInquiry.ContactPhone IS NOT NULL
	AND tblInquiry.ContactPhone != ''
    AND tblInquiry.Date >= DATEADD(MONTH, -3, GETDATE())
)
SELECT *
FROM SubQuery
WHERE SubQuery.Status = 'Inquiry'
"""

