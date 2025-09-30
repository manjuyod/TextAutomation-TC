import pymssql
import os

##Connection Function----------------------------------------------------------------------------------------------------------------------

def getDbData(q):
    server = 'localhost'
    user = os.environ.get("CRMSrvUs")
    password = os.environ.get("CRMSrvPs")
    database = os.environ.get("CRMSrvDb")
    conn = pymssql.connect(server, user, password, database)
    cursor = conn.cursor()
    cursor.execute(q)
    conn.commit()
    conn.close()

##Franchise Listing Function----------------------------------------------------------------------------------------------------------------------


def clearNullMasterStudents():
    sessionNulls = getDbData(
        """DELETE FROM tblMasterSchedule WHERE StudentId1 IS NULL;"""
    )


def clearNullSessionStudents():
    sessionNulls = getDbData(
        """DELETE FROM tblSessionSchedule WHERE StudentId1 IS NULL;"""
    )


clearNullMasterStudents()
clearNullSessionStudents()
