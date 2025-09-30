import os
import pandas as pd
from sqlalchemy import create_engine, text

def get_engine():
    server   = os.environ['CRMSrvAddress']
    username = os.environ['CRMSrvUs']
    password = os.environ['CRMSrvPs']
    database = os.environ['CRMSrvDb']
    conn_str = (
        f"mssql+pyodbc://{username}:{password}@{server}/{database}"
        "?driver=ODBC+Driver+17+for+SQL+Server"
    )
    return create_engine(conn_str)

def get_db_data(query: str, params: dict = None) -> pd.DataFrame:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(text(query), conn, params=params)
    except Exception as ex:
        print(f"[db_utils] SQL error: {ex}")
        return pd.DataFrame()
