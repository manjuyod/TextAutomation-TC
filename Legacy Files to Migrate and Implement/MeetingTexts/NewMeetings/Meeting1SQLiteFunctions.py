"""
Meeting1SQLiteFunctions.py
Purpose: Provide CRUD operations on the 'MeetingCache' table in a local SQLite DB,
         using InquiryID as the unique identifier.
"""

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
        return obj.strftime("%H:%M:%S")
    raise TypeError("Type %s not serializable" % type(obj))

# Path to your local SQLite database
database = r"C:\Users\Administrator\Desktop\Scripts\reporting-v1\Assets\Database\ReportDatabase.db"

# Create the connection string for SQLAlchemy - for SQLite, just do sqlite:///<path>
connection_string = f"sqlite:///{database}"

# Create the engine
engine = create_engine(connection_string, echo=False)  # echo=True logs SQL statements for debugging

def fetch_data(query, engine, params=None):
    """Helper to return a DataFrame from a SQL query."""
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)
    except Exception as query_err:
        print(f"SQL execution error: {query_err}")
        return pd.DataFrame()

def select_meeting_cache(engine):
    """
    Returns all rows from the 'MeetingCache' table as a DataFrame.
    """
    query = text("SELECT * FROM MeetingCache;")
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        df = fetch_data(query, engine)
        session.commit()
        return df
    except SQLAlchemyError as e:
        session.rollback()
        print(f"An unexpected SQL error occurred (SELECT): {e}")
        return pd.DataFrame()
    finally:
        session.close()

def delete_meeting_cache(engine, inquiry_ids_to_delete):
    """
    Deletes rows from 'MeetingCache' where InquiryID is in inquiry_ids_to_delete.
    This loops one-by-one to avoid SQLite parameter binding issues with IN.
    """
    if not inquiry_ids_to_delete:
        return

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        for single_id in inquiry_ids_to_delete:
            delete_query = text("""
                DELETE FROM MeetingCache
                WHERE InquiryID = :id
            """)
            session.execute(delete_query, {"id": single_id})
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        print(f"An unexpected SQL error occurred (DELETE): {e}")
    finally:
        session.close()

def insert_meeting_cache(engine, new_rows_df):
    """
    Inserts new rows into 'MeetingCache'. The DataFrame columns should match the table's columns.
    If 'IsText' column is missing, default it to 'No'.
    """
    if new_rows_df.empty:
        return  # Nothing to insert

    # Ensure 'IsText' column exists
    if 'IsText' not in new_rows_df.columns:
        new_rows_df['IsText'] = 'No'

    # Remove duplicates just in case
    new_rows_df = new_rows_df.drop_duplicates(subset=['InquiryID'])

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        # Use pandas to_sql with if_exists='append'
        new_rows_df.to_sql('MeetingCache', con=engine, if_exists='append', index=False)
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        print(f"An unexpected SQL error occurred (INSERT): {e}")
    except Exception as e:
        session.rollback()
        print(f"Non-SQL error occurred (INSERT): {e}")
    finally:
        session.close()

def update_meeting_cache(engine, inquiry_ids_to_update):
    """
    Sets IsText = 'Yes' for the specified InquiryIDs in 'MeetingCache'.
    This loops one-by-one to avoid SQLite parameter binding issues with IN.
    """
    if not inquiry_ids_to_update:
        return

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        for single_id in inquiry_ids_to_update:
            update_query = text("""
                UPDATE MeetingCache
                   SET IsText = 'Yes'
                 WHERE InquiryID = :id
            """)
            session.execute(update_query, {"id": single_id})
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        print(f"An unexpected SQL error occurred (UPDATE): {e}")
    finally:
        session.close()

if __name__ == "__main__":
    # Quick test
    df_cache = select_meeting_cache(engine)
    print("MeetingCache contents:\n", df_cache)
