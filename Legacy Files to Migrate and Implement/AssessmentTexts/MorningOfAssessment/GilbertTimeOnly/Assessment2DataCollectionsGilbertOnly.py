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

def consolidate_rows(df):
    # Group by InquiryID and aggregate the results
    consolidated_df = df.groupby('InquiryID').agg({
        'AutomationStage': 'first',  # Keeps the first value
        'FranchiseID': 'first',      # Keeps the first value
        'AssessmentDate': 'min',   # Keeps the earlist value
        'AssessmentTime': 'min',   # Keeps the ealiest value
        'AssessmentEmail': 'first',  # Keeps the first value
        'AssessmentPhone': 'first',  # Keeps the first value
        'GuardianFirstName': 'first',  # Keeps the first value
        'StudentString': ', '.join   # Concatenates the names
    }).reset_index()
    return consolidated_df

def fetch_assessment_data(engine):
    assessment_query = text("""
SELECT
    'Assessment2' AS AutomationStage,
    tblAssessments.InquiryID AS InquiryID,
    (SELECT TOP 1 FranchiesId FROM tblInquiry WHERE ID = tblAssessments.InquiryID) AS FranchiseID,
    tblAssessments.Date AS AssessmentDate,
    tblAssessments.Time AS AssessmentTime,
    (SELECT TOP 1 Email FROM tblInquiry WHERE ID = tblAssessments.InquiryID) AS AssessmentEmail,
    (SELECT TOP 1 ContactPhone FROM tblInquiry WHERE ID = tblAssessments.InquiryID) AS AssessmentPhone,
    tblAssessments.CFirstName AS GuardianFirstName,
    tblAssessments.SFirstName AS StudentString
FROM tblAssessments
WHERE InquiryID IN (
    Select ID
    FROM tblInquiry
    WHERE FranchiesId IN (57)
)
AND NOT EXISTS (
    SELECT 1
    FROM tblMeetings
    WHERE tblMeetings.InquiryID = tblAssessments.InquiryID
    AND tblMeetings.Time IS NOT NULL
    AND tblMeetings.Time <> '00:00:00.0000000'
    AND tblMeetings.Date = tblAssessments.Date
)
AND tblAssessments.Date > CAST(DATEADD(DAY, -1, GETDATE()) AS DATE)
AND tblAssessments.Date < CAST(DATEADD(DAY, 1, GETDATE()) AS DATE)
AND tblAssessments.IsDeleted = 0
AND tblAssessments.AssessmentCom = 0
AND tblAssessments.Time IS NOT NULL 
AND tblAssessments.Time <> '00:00:00.0000000';
""")
    #Initialize SQL Alchemy Session
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        result = session.execute(assessment_query)
        # Converting to DataFrame
        assessment_info_df = fetch_data(assessment_query, engine)
        session.commit()
        # Consolidate rows
        if not assessment_info_df.empty:
            assessment_info_df = consolidate_rows(assessment_info_df)
        return assessment_info_df
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
    df = fetch_assessment_data(engine)
    if not df.empty:
        print(df)
    else:
        print("No new assessments to process.")
