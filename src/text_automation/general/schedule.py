from __future__ import annotations

from sqlalchemy import text

from ..db.sql import get_engine


def clear_null_master_students() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tblMasterSchedule WHERE StudentId1 IS NULL"))


def clear_null_session_students() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tblSessionSchedule WHERE StudentId1 IS NULL"))


def clear_all_null_students() -> None:
    clear_null_master_students()
    clear_null_session_students()
