from __future__ import annotations

from typing import Optional, List

import pandas as pd
from sqlalchemy import text

from ..assessments.data import fetch_assessment_data
from ..meetings.data import fetch_meeting_data
from ..reporting.sqlite_db import get_sqlite_engine


def _get_table_columns(table: str) -> List[str]:
    eng = get_sqlite_engine()
    with eng.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return [r[1] for r in rows] if rows else []


def _align_df_to_table(table: str, df: pd.DataFrame, default_istext: str) -> pd.DataFrame:
    cols = _get_table_columns(table)
    if not cols:
        # If table doesn't exist yet, return df with IsText enforced
        out = df.copy()
        out["IsText"] = default_istext
        return out
    out = pd.DataFrame()
    for c in cols:
        if c in df.columns:
            out[c] = df[c]
        elif c == "IsText":
            out[c] = default_istext
        else:
            out[c] = None
    return out


def _delete_all(table: str) -> int:
    eng = get_sqlite_engine()
    try:
        with eng.begin() as conn:
            res = conn.execute(text(f"DELETE FROM {table}"))
            try:
                return res.rowcount or 0
            except Exception:
                return 0
    except Exception:
        # Table may not exist yet; treat as zero deleted and allow writer to create it
        return 0


def _write_df(table: str, df: pd.DataFrame, default_istext: str = "No") -> int:
    if df.empty:
        return 0
    # Align to table schema and ensure IsText default
    df = _align_df_to_table(table, df, default_istext)
    eng = get_sqlite_engine()
    with eng.begin() as conn:
        # Verbose info
        try:
            url = str(eng.url)
        except Exception:
            url = "sqlite"
        print({"op": "write", "table": table, "rows": len(df), "columns": list(df.columns), "database": url})
        df.to_sql(table, con=conn, if_exists="append", index=False)
    return len(df)


def refresh_assessment_cache(
    limit: Optional[int] = None, dry_run: bool = False, mark_sent: bool = True
) -> tuple[int, int]:
    df = fetch_assessment_data()
    if limit:
        df = df.head(int(limit))
    deleted = 0
    written = 0
    print({"op": "fetch", "table": "AssessmentCache", "rows": len(df), "columns": list(df.columns)})
    if dry_run:
        print({"op": "delete", "table": "AssessmentCache", "skipped": True})
        print({"op": "write", "table": "AssessmentCache", "rows": len(df), "mark_sent": mark_sent, "skipped": True})
        return deleted, len(df)
    deleted = _delete_all("AssessmentCache")
    print({"op": "delete", "table": "AssessmentCache", "deleted": deleted})
    written = _write_df("AssessmentCache", df, default_istext=("Yes" if mark_sent else "No"))
    return deleted, written


def refresh_meeting_cache(
    limit: Optional[int] = None, dry_run: bool = False, mark_sent: bool = True
) -> tuple[int, int]:
    df = fetch_meeting_data()
    if limit:
        df = df.head(int(limit))
    deleted = 0
    written = 0
    print({"op": "fetch", "table": "MeetingCache", "rows": len(df), "columns": list(df.columns)})
    if dry_run:
        print({"op": "delete", "table": "MeetingCache", "skipped": True})
        print({"op": "write", "table": "MeetingCache", "rows": len(df), "mark_sent": mark_sent, "skipped": True})
        return deleted, len(df)
    deleted = _delete_all("MeetingCache")
    print({"op": "delete", "table": "MeetingCache", "deleted": deleted})
    written = _write_df("MeetingCache", df, default_istext=("Yes" if mark_sent else "No"))
    return deleted, written


def refresh_both(limit: Optional[int] = None, dry_run: bool = False, mark_sent: bool = True) -> dict:
    a_del, a_write = refresh_assessment_cache(limit=limit, dry_run=dry_run, mark_sent=mark_sent)
    m_del, m_write = refresh_meeting_cache(limit=limit, dry_run=dry_run, mark_sent=mark_sent)
    return {
        "assessment": {"deleted": a_del, "written": a_write},
        "meeting": {"deleted": m_del, "written": m_write},
        "dry_run": dry_run,
        "mark_sent": mark_sent,
    }
