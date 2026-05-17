from __future__ import annotations

import sys
from email.message import EmailMessage
from unittest.mock import Mock, patch

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.config import Franchise
from text_automation.direct_inquiry import processor as di_processor
from text_automation.direct_inquiry import gravity_forms as di_gf


def _email_body(parent: str, student: str, phone: str, email: str, grade: str, source: str = "") -> str:
    def row(label: str, value: str) -> str:
        return f"<tr bgcolor=\"#EAF2FA\"><td>{label}</td></tr><tr><td>{value}</td></tr>"

    html = "<table>" + "".join(
        [
            row("Parent Name", parent),
            row("Student Name", student),
            row("Phone", phone),
            row("Email", email),
            row("Grade", grade),
            row("Some Other", source),
        ]
    ) + "</table>"
    return html


class _FakeGravityClient:
    def __init__(self, entries_by_form, forms_by_id):
        self.entries_by_form = entries_by_form
        self.forms_by_id = forms_by_id
        self.marked = []
        self.queries = []

    def entries(self, form_id, *, page_size=100, current_page=1, unread_only=False, search=None):
        self.queries.append(("entries", form_id, page_size, current_page, unread_only, search))
        return self.entries_by_form.get(form_id, [])

    def form(self, form_id):
        self.queries.append(("form", form_id))
        return self.forms_by_id[form_id]

    def mark_entry_read(self, entry_id):
        self.marked.append(str(entry_id))
        if hasattr(self, "mark_entry_read_fail") and self.mark_entry_read_fail:
            raise RuntimeError("mark failed")


class _PagedMutableGravityClient:
    def __init__(self, entries):
        self.unread = [dict(entry) for entry in entries]
        self.marked = []
        self.queries = []

    def entries(self, form_id, *, page_size=100, current_page=1, unread_only=False, search=None):
        self.queries.append(("entries", form_id, page_size, current_page, unread_only, search))
        start = (current_page - 1) * page_size
        end = start + page_size
        page = [entry for entry in self.unread if str(entry.get("form_id")) == str(form_id)][start:end]
        total = len([entry for entry in self.unread if str(entry.get("form_id")) == str(form_id)])
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return {"entries": page, "paging": {"total_pages": total_pages}}

    def mark_entry_read(self, entry_id):
        self.marked.append(str(entry_id))
        self.unread = [entry for entry in self.unread if str(entry.get("id")) != str(entry_id)]


def _message_with_html(html: str) -> tuple[Mock, EmailMessage]:
    msg = EmailMessage()
    msg["To"] = "gilbertaz@tutoringclub.com"
    msg["Date"] = "Mon, 16 May 2026 12:00:00 +0000"
    msg.set_content("plain text")
    msg.add_alternative(html, subtype="html")
    service = Mock()
    return service, msg


class FakeConfig:
    def __init__(self, franchises):
        self.franchises = franchises


class _FakeEngine:
    def __init__(self):
        self.executed = []

    def begin(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement):
        self.executed.append(getattr(statement, "text", str(statement)))


def test_gmail_no_location_no_mark_read_and_no_sql_text():
    service, msg = _message_with_html(_email_body("Alex Parent", "Jordan Student", "5551234567", "alex@example.com", "3rd Grade"))
    with patch("text_automation.direct_inquiry.processor.franchise_from_to_header", return_value=57), patch(
        "text_automation.direct_inquiry.processor._franchise_by_url_fragment", return_value=None
    ), patch("text_automation.direct_inquiry.processor.mark_as_read") as mark_as_read, patch(
        "text_automation.direct_inquiry.processor.send_message"
    ), patch("text_automation.direct_inquiry.processor.process_direct_inquiry_payload") as process_payload:
        result = di_processor._process_one(service, "msg-id", msg, "auto", False)

    assert result is None
    mark_as_read.assert_called_once_with(service, "msg-id")
    process_payload.assert_not_called()


def test_gmail_location_specific_path_still_processes():
    service, msg = _message_with_html(_email_body("Alex Parent", "Jordan Student", "5551234567", "alex@example.com", "3rd Grade"))
    with patch("text_automation.direct_inquiry.processor.franchise_from_to_header", return_value=57), patch(
        "text_automation.direct_inquiry.processor._franchise_by_url_fragment", return_value=57
    ), patch("text_automation.direct_inquiry.processor.mark_as_read") as mark_as_read, patch(
        "text_automation.direct_inquiry.processor.process_direct_inquiry_payload", return_value=True
    ) as process_payload:
        result = di_processor._process_one(service, "msg-id", msg, "auto", False)

    assert result is True
    mark_as_read.assert_called_once_with(service, "msg-id")
    process_payload.assert_called_once()


def test_gravity_forms_baseline_dry_run_does_not_mark_and_live_baseline_marks():
    entry = {
        "id": "100",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "5551234567",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Gilbert",
    }
    forms = {
        1: {
            "id": 1,
            "fields": [
                {"id": 1, "label": "Parent Name", "type": "name"},
                {"id": 2, "label": "Student Name", "type": "name"},
                {"id": 3, "label": "Phone", "type": "phone"},
                {"id": 4, "label": "Email", "type": "email"},
                {"id": 5, "label": "Grade", "type": "select"},
                {"id": 6, "label": "Preferred Club Location", "type": "select"},
            ],
        }
    }
    client = _FakeGravityClient({1: [entry]}, forms)

    dry_run = di_gf.baseline_direct_inquiry(client, form_ids=[1], limit=1, dry_run=True)
    assert dry_run["entries"] == 1
    assert dry_run["marked_read"] == 0
    assert client.marked == []

    live = di_gf.baseline_direct_inquiry(client, form_ids=[1], limit=1, dry_run=False)
    assert live["entries"] == 1
    assert live["marked_read"] == 1
    assert client.marked == ["100"]


def test_gravity_forms_baseline_limit_is_exact_and_rejects_non_target_forms():
    entries = [{"id": str(i), "form_id": "1"} for i in range(1, 4)]
    client = _FakeGravityClient({1: entries}, {1: {"id": 1, "fields": []}})

    result = di_gf.baseline_direct_inquiry(client, form_ids=[1], limit=1, dry_run=False)

    assert result["entries"] == 1
    assert result["marked_read"] == 1
    assert client.marked == ["1"]

    try:
        di_gf.baseline_direct_inquiry(client, form_ids=[99], dry_run=True)
    except ValueError as exc:
        assert "target forms" in str(exc)
    else:
        raise AssertionError("Expected non-target form_id to be rejected")


def test_gravity_forms_baseline_snapshots_pages_before_marking_read():
    entries = [{"id": str(i), "form_id": "1"} for i in range(1, 6)]
    client = _PagedMutableGravityClient(entries)

    result = di_gf.baseline_direct_inquiry(client, form_ids=[1], page_size=2, dry_run=False)

    assert result["entries"] == 5
    assert result["marked_read"] == 5
    assert result["errors"] == 0
    assert client.marked == ["1", "2", "3", "4", "5"]
    assert client.unread == []


def test_gravity_forms_process_marks_read_only_after_processing_success():
    entry = {
        "id": "101",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "5551234567",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Gilbert",
    }
    forms = {
        1: {
            "id": 1,
            "fields": [
                {"id": 1, "label": "Parent Name", "type": "name"},
                {"id": 2, "label": "Student Name", "type": "name"},
                {"id": 3, "label": "Phone", "type": "phone"},
                {"id": 4, "label": "Email", "type": "email"},
                {"id": 5, "label": "Grade", "type": "select"},
                {"id": 6, "label": "Preferred Club Location", "type": "select"},
            ],
        }
    }

    client = _FakeGravityClient({1: [entry]}, forms)
    franchises = (
        Franchise(
            id=57,
            name="Gilbert",
            url="https://tutoringclub.com/gilbertaz/",
            director="Ryan",
            email="gilbertaz@tutoringclub.com",
            timezone="America/Phoenix",
            preferred_locations=("gilbert",),
        ),
    )
    with patch("text_automation.direct_inquiry.gravity_forms.load_config", return_value=FakeConfig(franchises)):
        called = []

        def _process_ok(**kwargs):
            called.append(kwargs)
            return True

        result = di_gf.process_direct_inquiry(client, form_ids=[1], limit=1, dry_run=False, process_fn=_process_ok)
        assert result["processed"] == 1
        assert result["marked_read"] == 1
        assert client.marked == ["101"]
        assert len(called) == 1


def test_gravity_forms_normalizes_multi_input_name_fields_and_form_id_fallback():
    entry = {
        "id": "201",
        "_form_id": "14",
        "2.3": "Alex",
        "2.6": "Parent",
        "9.3": "Jordan",
        "9.6": "Student",
        "12": "5551234567",
        "1": "alex@example.com",
        "10": "3rd Grade",
        "13": "Gilbert",
    }
    forms = {
        14: {
            "id": 14,
            "fields": [
                {"id": 2, "label": "Parent Name", "type": "name", "inputs": [{"id": "2.3", "label": "First"}, {"id": "2.6", "label": "Last"}]},
                {"id": 9, "label": "Student Name", "type": "name", "inputs": [{"id": "9.3", "label": "First"}, {"id": "9.6", "label": "Last"}]},
                {"id": 12, "label": "Phone", "type": "phone"},
                {"id": 1, "label": "Email", "type": "email"},
                {"id": 10, "label": "Grade Level", "type": "select"},
                {"id": 13, "label": "Location", "type": "select"},
            ],
        }
    }
    client = _FakeGravityClient({}, forms)

    normalized = di_gf._normalize_entry(entry, client)

    assert normalized is not None
    assert normalized.form_id == 14
    assert normalized.parent_name == "Alex Parent"
    assert normalized.student_name == "Jordan Student"


def test_gravity_forms_process_sql_or_zapier_failure_keeps_entry_unread():
    entry = {
        "id": "102",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "5551234567",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Gilbert",
    }
    forms = {1: {"id": 1, "fields": [{"id": 1, "label": "Parent Name", "type": "name"}] + [
        {"id": 2, "label": "Student Name", "type": "name"},
        {"id": 3, "label": "Phone", "type": "phone"},
        {"id": 4, "label": "Email", "type": "email"},
        {"id": 5, "label": "Grade", "type": "select"},
        {"id": 6, "label": "Preferred Club Location", "type": "select"},
    ]}}
    client = _FakeGravityClient({1: [entry]}, forms)
    franchises = (
        Franchise(
            id=57,
            name="Gilbert",
            url="https://tutoringclub.com/gilbertaz/",
            director="Ryan",
            email="gilbertaz@tutoringclub.com",
            timezone="America/Phoenix",
            preferred_locations=("gilbert",),
        ),
    )

    with patch("text_automation.direct_inquiry.gravity_forms.load_config", return_value=FakeConfig(franchises)):
        result = di_gf.process_direct_inquiry(
            client,
            form_ids=[1],
            limit=1,
            dry_run=False,
            process_fn=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("SQL failure")),
        )

    assert result["errors"] == 1
    assert result["processed"] == 0
    assert client.marked == []


def test_direct_inquiry_payload_escapes_gravity_forms_phone_and_email_sql_literals():
    engine = _FakeEngine()

    with patch("text_automation.direct_inquiry.processor.get_engine", return_value=engine), patch(
        "text_automation.direct_inquiry.processor.send_message"
    ):
        processed = di_processor.process_direct_inquiry_payload(
            parent_name="Alex Parent",
            student_name="Jordan Student",
            phone="555'123",
            email_addr="alex'o@example.test",
            grade="3rd Grade",
            franchise_id=1,
            local_dt=None,
            dry_run=False,
        )

    assert processed is True
    assert "555''123" in engine.executed[0]
    assert "alex''o@example.test" in engine.executed[0]


def test_direct_inquiry_payload_dry_run_logs_header_and_sql_without_db_access():
    with patch("text_automation.direct_inquiry.processor.get_engine") as get_engine, patch(
        "text_automation.direct_inquiry.processor.send_message"
    ) as send_message:
        processed = di_processor.process_direct_inquiry_payload(
            parent_name="Alex Parent",
            student_name="Jordan Student",
            phone="5551234567",
            email_addr="alex@example.test",
            grade="3rd Grade",
            franchise_id=57,
            local_dt=None,
            dry_run=True,
        )

    assert processed is True
    get_engine.assert_not_called()
    assert send_message.call_count == 2
    header = send_message.call_args_list[0].args[0]
    sql_log = send_message.call_args_list[1].args[0]
    assert "[direct-inquiry] FID=57" in header
    assert "[dry-run]" in header
    assert "EXEC [dbo].[usp_CreateInquary]" in sql_log
    assert "@ContactFirstName = 'Alex'" in sql_log
    assert "@Email = 'alex@example.test'" in sql_log


def test_direct_inquiry_payload_live_logs_header_and_sql_before_execute():
    events = []

    class RecordingEngine(_FakeEngine):
        def execute(self, statement):
            events.append(("execute", getattr(statement, "text", str(statement))))
            super().execute(statement)

    engine = RecordingEngine()

    def record_message(message, *_args):
        events.append(("telegram", message))

    with patch("text_automation.direct_inquiry.processor.get_engine", return_value=engine), patch(
        "text_automation.direct_inquiry.processor.send_message", side_effect=record_message
    ):
        processed = di_processor.process_direct_inquiry_payload(
            parent_name="Alex Parent",
            student_name="Jordan Student",
            phone="5551234567",
            email_addr="alex@example.test",
            grade="3rd Grade",
            franchise_id=1,
            local_dt=None,
            dry_run=False,
        )

    assert processed is True
    assert len(events) >= 3
    assert events[0][0] == "telegram"
    assert "[direct-inquiry] FID=1" in events[0][1]
    assert events[1][0] == "telegram"
    assert "EXEC [dbo].[usp_CreateInquary]" in events[1][1]
    assert events[2][0] == "execute"
    assert "@Email = 'alex@example.test'" in events[1][1]


def test_gravity_forms_mark_read_failure_after_success_is_reported():
    entry = {
        "id": "103",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "5551234567",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Gilbert",
    }
    forms = {
        1: {
            "id": 1,
            "fields": [
                {"id": 1, "label": "Parent Name", "type": "name"},
                {"id": 2, "label": "Student Name", "type": "name"},
                {"id": 3, "label": "Phone", "type": "phone"},
                {"id": 4, "label": "Email", "type": "email"},
                {"id": 5, "label": "Grade", "type": "select"},
                {"id": 6, "label": "Preferred Club Location", "type": "select"},
            ],
        }
    }
    client = _FakeGravityClient({1: [entry]}, forms)
    client.mark_entry_read_fail = True
    franchises = (
        Franchise(
            id=57,
            name="Gilbert",
            url="https://tutoringclub.com/gilbertaz/",
            director="Ryan",
            email="gilbertaz@tutoringclub.com",
            timezone="America/Phoenix",
            preferred_locations=("gilbert",),
        ),
    )

    with patch("text_automation.direct_inquiry.gravity_forms.load_config", return_value=FakeConfig(franchises)):
        result = di_gf.process_direct_inquiry(
            client,
            form_ids=[1],
            limit=1,
            dry_run=False,
            process_fn=lambda **kwargs: True,
        )

    assert result["processed"] == 0
    assert result["errors"] == 1
    assert result["read_mark_fail"] == 1
    assert client.marked == ["103"]


def test_gravity_forms_unmatched_location_is_terminal_and_marked_read():
    entry = {
        "id": "104",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "5551234567",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Nowhere Land",
    }
    forms = {1: {"id": 1, "fields": [
        {"id": 1, "label": "Parent Name", "type": "name"},
        {"id": 2, "label": "Student Name", "type": "name"},
        {"id": 3, "label": "Phone", "type": "phone"},
        {"id": 4, "label": "Email", "type": "email"},
        {"id": 5, "label": "Grade", "type": "select"},
        {"id": 6, "label": "Preferred Club Location", "type": "select"},
    ]}}
    client = _FakeGravityClient({1: [entry]}, forms)
    process_fn = Mock(return_value=True)
    franchises = (
        Franchise(
            id=57,
            name="Gilbert",
            url="https://tutoringclub.com/gilbertaz/",
            director="Ryan",
            email="gilbertaz@tutoringclub.com",
            timezone="America/Phoenix",
            preferred_locations=("gilbert",),
        ),
    )

    with patch("text_automation.direct_inquiry.gravity_forms.load_config", return_value=FakeConfig(franchises)):
        result = di_gf.process_direct_inquiry(
            client,
            form_ids=[1],
            limit=1,
            dry_run=False,
            process_fn=process_fn,
        )

    assert result["unmatched"] == 1
    assert result["processed"] == 0
    assert result["marked_read"] == 1
    assert client.marked == ["104"]
    process_fn.assert_not_called()


def test_gravity_forms_unmatched_location_mark_read_failure_is_reported():
    entry = {
        "id": "106",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "5551234567",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Nowhere Land",
    }
    forms = {1: {"id": 1, "fields": [
        {"id": 1, "label": "Parent Name", "type": "name"},
        {"id": 2, "label": "Student Name", "type": "name"},
        {"id": 3, "label": "Phone", "type": "phone"},
        {"id": 4, "label": "Email", "type": "email"},
        {"id": 5, "label": "Grade", "type": "select"},
        {"id": 6, "label": "Preferred Club Location", "type": "select"},
    ]}}
    client = _FakeGravityClient({1: [entry]}, forms)
    client.mark_entry_read_fail = True
    process_fn = Mock(return_value=True)
    franchises = (
        Franchise(
            id=57,
            name="Gilbert",
            url="https://tutoringclub.com/gilbertaz/",
            director="Ryan",
            email="gilbertaz@tutoringclub.com",
            timezone="America/Phoenix",
            preferred_locations=("gilbert",),
        ),
    )

    with patch("text_automation.direct_inquiry.gravity_forms.load_config", return_value=FakeConfig(franchises)):
        result = di_gf.process_direct_inquiry(
            client,
            form_ids=[1],
            limit=1,
            dry_run=False,
            process_fn=process_fn,
        )

    assert result["unmatched"] == 1
    assert result["processed"] == 0
    assert result["marked_read"] == 0
    assert result["read_mark_fail"] == 1
    assert result["errors"] == 1
    assert client.marked == ["106"]
    process_fn.assert_not_called()


def test_gravity_forms_ambiguous_location_retries_without_marking_read_or_processing():
    entry = {
        "id": "107",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "5551234567",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Shared",
    }
    forms = {1: {"id": 1, "fields": [
        {"id": 1, "label": "Parent Name", "type": "name"},
        {"id": 2, "label": "Student Name", "type": "name"},
        {"id": 3, "label": "Phone", "type": "phone"},
        {"id": 4, "label": "Email", "type": "email"},
        {"id": 5, "label": "Grade", "type": "select"},
        {"id": 6, "label": "Preferred Club Location", "type": "select"},
    ]}}
    client = _FakeGravityClient({1: [entry]}, forms)
    process_fn = Mock(return_value=True)
    franchises = (
        Franchise(
            id=57,
            name="Gilbert",
            url="https://tutoringclub.com/gilbertaz/",
            director="Ryan",
            email="gilbertaz@tutoringclub.com",
            timezone="America/Phoenix",
            preferred_locations=("shared",),
        ),
        Franchise(
            id=20,
            name="Clovis",
            url="https://tutoringclub.com/clovisca/",
            director="Katie",
            email="clovisca@tutoringclub.com",
            timezone="America/Los_Angeles",
            preferred_locations=("shared",),
        ),
    )

    with patch("text_automation.direct_inquiry.gravity_forms.load_config", return_value=FakeConfig(franchises)):
        result = di_gf.process_direct_inquiry(
            client,
            form_ids=[1],
            limit=1,
            dry_run=False,
            process_fn=process_fn,
        )

    assert result["ambiguous"] == 1
    assert result["processed"] == 0
    assert result["marked_read"] == 0
    assert client.marked == []
    process_fn.assert_not_called()


def test_gravity_forms_blacklisted_phone_is_terminal_no_send_and_marked_read():
    entry = {
        "id": "105",
        "form_id": "1",
        "date_created": "2026-05-16 08:00:00",
        "1": "Alex Parent",
        "2": "Jordan Student",
        "3": "2499618600",
        "4": "alex@example.com",
        "5": "3rd Grade",
        "6": "Gilbert",
    }
    forms = {1: {"id": 1, "fields": [
        {"id": 1, "label": "Parent Name", "type": "name"},
        {"id": 2, "label": "Student Name", "type": "name"},
        {"id": 3, "label": "Phone", "type": "phone"},
        {"id": 4, "label": "Email", "type": "email"},
        {"id": 5, "label": "Grade", "type": "select"},
        {"id": 6, "label": "Preferred Club Location", "type": "select"},
    ]}}
    client = _FakeGravityClient({1: [entry]}, forms)
    process_fn = Mock(return_value=True)

    result = di_gf.process_direct_inquiry(client, form_ids=[1], limit=1, dry_run=False, process_fn=process_fn)

    assert result["terminal_skipped"] == 1
    assert result["processed"] == 0
    assert client.marked == ["105"]
    process_fn.assert_not_called()


def test_gravity_forms_location_matching_alias_name_email_slug():
    gilbert = Franchise(
        id=57,
        name="Gilbert",
        url="https://tutoringclub.com/gilbertaz/",
        director="Ryan",
        email="gilbertaz@tutoringclub.com",
        timezone="America/Phoenix",
        preferred_locations=("my-gilbert",),
    )
    clovis = Franchise(
        id=20,
        name="Clovis",
        url="https://tutoringclub.com/clovisca/",
        director="Katie",
        email="clovisca@tutoringclub.com",
        timezone="America/Los_Angeles",
        preferred_locations=("clovis",),
    )
    franchises = (gilbert, clovis)

    assert di_gf._resolve_franchise_id("my-gilbert", franchises)[0] == 57
    assert di_gf._resolve_franchise_id("Clovis", franchises)[0] == 20
    assert di_gf._resolve_franchise_id("clovisca@tutoringclub.com", franchises)[0] == 20
    assert di_gf._resolve_franchise_id("gilbertaz", franchises)[0] == 57
    assert di_gf._resolve_franchise_id("unknown location", franchises)[0] is None
    both = Franchise(
        id=99,
        name="Northwest Center",
        url="https://tutoringclub.com/northwest/",
        director="X",
        email="northwest@tc.com",
        timezone="America/Los_Angeles",
        preferred_locations=("shared",),
    )
    both2 = Franchise(
        id=98,
        name="West Center",
        url="https://tutoringclub.com/west/",
        director="Y",
        email="west@tc.com",
        timezone="America/Los_Angeles",
        preferred_locations=("shared",),
    )
    ambiguous = di_gf._resolve_franchise_id("shared", (gilbert, clovis, both, both2))
    assert ambiguous == (None, "ambiguous")
