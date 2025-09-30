import sqlite3
from sqlite3 import Error
import pandas as pd
import datetime as dt

database = (
    r"C:\Users\Administrator\Desktop\Scripts\reporting-v1\Assets\Database\ReportDatabase.db"
)


def getDistroData(report, freq):
    conn = None
    try:
        conn = sqlite3.connect(database)
    except Error as e:
        print(e)

    df = pd.read_sql_query(
        "SELECT * FROM " + report + " WHERE Frequency like '%" + freq + "%'", conn
    )

    return df


def getLastAssessmentDate(table):
    conn = None
    try:
        conn = sqlite3.connect(database)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SubmissionDate FROM "
            + table
            + " WHERE SubmissionID = (SELECT MAX(SubmissionID) FROM "
            + table
            + ")"
        )
        date = cursor.fetchall()[0][0]
        return date

    except Error as e:
        print(e)

    finally:
        if conn:
            conn.close()


def getDbData(SqlStatement):
    conn = None
    try:
        conn = sqlite3.connect(database)
        cursor = conn.cursor()
        cursor.execute(SqlStatement)
        result = cursor.fetchall()
        return result

    except Error as e:
        print(e)

    finally:
        if conn:
            conn.close()


def insertDbRecord(paramSql, valueTuple):
    conn = None
    try:
        conn = sqlite3.connect(database)
        cursor = conn.cursor()
        cursor.execute(paramSql, valueTuple)
        conn.commit()
        cursor.close()

    except Error as e:
        print(e)

    finally:
        if conn:
            conn.close()
