import datetime
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
import os

def json_serial(obj):
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    elif isinstance(obj, datetime.time):
        return obj.strftime("%H:%M:%S")  # Format time as HH:MM:SS
    raise TypeError("Type %s not serializable" % type(obj))

# Define your connection details
server = 'localhost'
username = os.getenv('CRMSrvUs')
password = os.getenv('CRMSrvPs')
database = os.getenv('CRMSrvDb')

# Create the connection string for SQLAlchemy
connection_string = f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC Driver 17 for SQL Server"

# Create the engine
engine = create_engine(connection_string)

def fetch_data(query, engine, params=None):
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except Exception as query_err:
        print(f"SQL execution error: {query_err}")
        return pd.DataFrame()  # Return an empty DataFrame in case of an error

def fetch_meeting_data(engine):
    meeting_query = text("""
SELECT
    'Meeting2' AS AutomationStage,
    (SELECT TOP 1 FranchiesId FROM tblInquiry WHERE ID = tblMeetings.InquiryID) AS FranchiseID,
    tblMeetings.ID AS MeetingID,
    tblMeetings.Date AS MeetingDate,
    tblMeetings.Time AS MeetingTime,
    tblMeetings.ContactEmail AS AssessmentEmail,
    tblMeetings.ContactNumber AS AssessmentPhone,
    CONVERT(date, GETDATE()) AS CurrentDate,
    tblMeetings.CFirstName AS GuardianFirstName,
    tblMeetings.StudentNames AS StudentString,
    (SELECT MAX(Grade) FROM tblInquiryStudents WHERE InquiryID = tblMeetings.InquiryID) AS Grade,
    tblMeetings.InquiryID,
    (SELECT TOP 1 FatherName FROM dpinket_TC_QA.dbo.tblTempStudentAuto 
	WHERE InquiryID = tblMeetings.InquiryID 
	AND (dpinket_TC_QA.dbo.tblTempStudentAuto.FatherName IS NOT NULL OR dpinket_TC_QA.dbo.tblTempStudentAuto.MotherName IS NOT NULL)
	ORDER BY dpinket_TC_QA.dbo.tblTempStudentAuto.ID ASC) AS Parent1Name,
    (SELECT TOP 1 MotherName FROM dpinket_TC_QA.dbo.tblTempStudentAuto 
	WHERE InquiryID = tblMeetings.InquiryID 
	AND (dpinket_TC_QA.dbo.tblTempStudentAuto.FatherName IS NOT NULL OR dpinket_TC_QA.dbo.tblTempStudentAuto.MotherName IS NOT NULL)
	ORDER BY dpinket_TC_QA.dbo.tblTempStudentAuto.ID ASC) AS Parent2Name
FROM tblMeetings
WHERE tblMeetings.InquiryID IN (
    SELECT ID
    FROM tblInquiry
    WHERE FranchiesId IN (6, 11, 15, 16, 19, 24, 20, 60, 87)
)
AND NOT EXISTS (
	SELECT 1
	FROM tblAssessments
	WHERE tblAssessments.InquiryID = tblMeetings.InquiryID
	AND tblAssessments.Date = tblMeetings.Date
	AND tblAssessments.IsDeleted   = 0
	AND tblAssessments.Time IS NOT NULL
	AND tblAssessments.Time <> '00:00:00.0000000'
)
AND tblMeetings.Date > CAST(DATEADD(DAY, -1, GETDATE()) AS DATE)
AND tblMeetings.Date < CAST(DATEADD(DAY, 1, GETDATE()) AS DATE)
AND tblMeetings.IsDeleted = 0
AND tblMeetings.Time IS NOT NULL 
AND tblMeetings.Time <> '00:00:00.0000000';
""")
    #Initialize SQL Alchemy Sesson
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        result = session.execute(meeting_query)
        # Converting to DataFrame
        meeting_info_df = fetch_data(meeting_query, engine)
        session.commit()
        return meeting_info_df
    except SQLAlchemyError as e:
        session.rollback()
        print(f"An unexpected SQL error occurred: {e}")
        return pd.DataFrame()  # Return an empty DataFrame in case of an error
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return pd.DataFrame()  # Handle non-SQL errors
    finally:
        session.close()
# Function Calls
if __name__ == "__main__":
    df = fetch_meeting_data(engine)
    if not df.empty:
        print(df)
    else:
        print("No new meetings to process.")
