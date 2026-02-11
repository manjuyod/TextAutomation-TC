from __future__ import annotations

from ..config import load_config


def format_grade_phrase(grade: str) -> str:
    """Return a human-friendly grade phrase (e.g., "1st grader")."""
    cfg = load_config()
    di = cfg.direct_inquiry
    grade_dict = di.grade_phrase_map if (di and di.grade_phrase_map) else {
        "Kindergarten": "Kindergartener",
        "1st Grade": "1st grader",
        "2nd Grade": "2nd grader",
        "3rd Grade": "3rd grader",
        "4th Grade": "4th grader",
        "5th Grade": "5th grader",
        "6th Grade": "6th grader",
        "7th Grade": "7th grader",
        "8th Grade": "8th grader",
        "9th Grade": "9th grader",
        "10th Grade": "10th grader",
        "11th Grade": "11th grader",
        "12th Grade": "12th grader",
    }
    return grade_dict.get((grade or "").strip(), "student")

