from __future__ import annotations

from text_automation.general.student_names import parse_student_names, format_student_names


def build_message(contact_first: str | None, student_first: str | None) -> str:
    contact = (contact_first or "").strip()

    # Student phrase (optional)
    phrase = ""
    if student_first and student_first.strip():
        firsts = format_student_names(parse_student_names(student_first))
        if firsts:
            phrase = f" for {firsts}"

    salutation = f"Hey {contact}," if contact else "Hello,"
    body = (
        f"{salutation} We haven't spoken in a while. Would you still be interested in some tutoring{phrase}? "
        "If this is something that interests you, I'd be happy to have a conversation."
    )
    return body

