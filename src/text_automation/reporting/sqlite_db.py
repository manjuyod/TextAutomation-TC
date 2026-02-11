from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Iterable, Sequence

import pandas as pd
from sqlalchemy import create_engine

from ..config import load_config


def _db_path() -> Path:
    cfg = load_config()
    if cfg.reporting_db:
        return cfg.reporting_db
    # Fallback: env var handled in load_config; if still None, raise
    raise RuntimeError(
        "Reporting database path not configured. Set TEXT_AUTOMATION_REPORT_DB or text_automation.toml [reporting].database"
    )


def get_distro_data(report: str, freq: str) -> pd.DataFrame:
    path = _db_path()
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query(
            f"SELECT * FROM {report} WHERE Frequency like ?", conn, params=[f"%{freq}%"]
        )


def get_last_assessment_date(table: str) -> Any:
    path = _db_path()
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT SubmissionDate FROM {table} WHERE SubmissionID = (SELECT MAX(SubmissionID) FROM {table})"
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_db_data(sql: str) -> list[tuple]:
    path = _db_path()
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        cur.execute(sql)
        return cur.fetchall()


def insert_db_record(param_sql: str, values: Sequence[Any]) -> None:
    path = _db_path()
    with sqlite3.connect(path) as conn:
        cur = conn.cursor()
        cur.execute(param_sql, values)
        conn.commit()


def get_sqlite_engine(echo: bool = False):
    """Return a SQLAlchemy engine bound to the configured SQLite DB."""
    path = _db_path()
    return create_engine(f"sqlite:///{path}", echo=echo)
