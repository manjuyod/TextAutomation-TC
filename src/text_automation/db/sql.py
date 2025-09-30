from __future__ import annotations

import os
from typing import Any, Mapping, Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool


def _build_conn_str() -> str:
    server = os.environ.get("CRMSrvAddress", "localhost")
    username = os.environ.get("CRMSrvUs")
    password = os.environ.get("CRMSrvPs")
    database = os.environ.get("CRMSrvDb")
    if not (username and password and database):
        raise RuntimeError(
            "Missing SQL Server credentials. Set CRMSrvUs, CRMSrvPs, CRMSrvDb (and CRMSrvAddress)."
        )
    return (
        f"mssql+pyodbc://{username}:{password}@{server}/{database}?driver=ODBC+Driver+17+for+SQL+Server"
    )


def get_engine(echo: bool = False):
    conn_str = _build_conn_str()
    return create_engine(
        conn_str,
        poolclass=QueuePool,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
        echo=echo,
    )


def get_db_data(query: str, params: Optional[Mapping[str, Any]] = None) -> pd.DataFrame:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            return pd.read_sql_query(text(query), conn, params=params)
    except Exception as ex:
        print(f"[db.sql] SQL error: {ex}")
        return pd.DataFrame()

