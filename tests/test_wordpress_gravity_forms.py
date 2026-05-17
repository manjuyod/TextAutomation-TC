import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from text_automation.wordpress.gravity_forms import (
    CredentialError,
    ForbiddenFormsError,
    GravityFormsClient,
    _env_prefix_for_profile,
    build_shape_export,
    credentials_from_env,
    export_shape_to_file,
    redact_entry,
)
from text_automation import cli as cli_mod
from text_automation.cli import build_parser


class _FakeClient:
    def __init__(self, *, discovery=None, forms=None, entries=None, form_by_id=None, forms_error=None):
        self._discovery = discovery or {"namespaces": ["wp/v2", "gf/v2"]}
        self._forms = forms or []
        self._entries = entries or {}
        self._form_by_id = form_by_id or {}
        self._forms_error = forms_error
        self.calls = []

    def discovery(self):
        self.calls.append(("discovery",))
        return self._discovery

    def forms(self):
        self.calls.append(("forms",))
        if self._forms_error:
            raise self._forms_error
        return self._forms

    def form(self, form_id):
        self.calls.append(("form", form_id))
        return self._form_by_id[form_id]

    def entries(
        self,
        form_id,
        page_size=25,
        current_page=1,
        unread_only=False,
        search=None,
    ):
        self.calls.append(("entries", form_id, page_size, current_page, unread_only, search))
        return self._entries.get(form_id, [])


class _OkResponse:
    status_code = 200
    text = ""

    def json(self):
        return {"namespaces": ["wp/v2", "gf/v2"]}


class _EntryResponse:
    status_code = 200
    text = ""

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _BadResponse:
    status_code = 500
    text = "server err"

    def json(self):
        return {"message": "server err"}


class _RecordingSession:
    def __init__(self, payloads: dict[str, Any] | None = None):
        self._payloads = payloads or {}
        self.calls = []

    def get(self, *args, **kwargs):
        url = args[0]
        self.calls.append(("GET", url, kwargs))
        if "entries" in url and "entry" in self._payloads:
            return self._payloads["entry"]
        if "entries" in url and "entries" in self._payloads:
            return self._payloads["entries"]
        return self._payloads.get("get", _OkResponse())

    def put(self, *args, **kwargs):
        url = args[0]
        self.calls.append(("PUT", url, kwargs.get("json")))
        return self._payloads.get("put", _OkResponse())


class GravityFormsShapeStudyTests(unittest.TestCase):
    def test_profile_env_names_are_normalized(self):
        self.assertEqual(_env_prefix_for_profile("gravity_pull_main_tc"), "GRAVITY_PULL_MAIN_TC")
        self.assertEqual(_env_prefix_for_profile("Gravity Pull-Main TC"), "GRAVITY_PULL_MAIN_TC")

    def test_credentials_from_env_requires_key_and_secret(self):
        with self.assertRaises(CredentialError) as ctx:
            credentials_from_env("gravity_pull_main_tc", environ={})

        msg = str(ctx.exception)
        self.assertIn("GRAVITY_PULL_MAIN_TC_CONSUMER_KEY", msg)
        self.assertIn("GRAVITY_PULL_MAIN_TC_CONSUMER_SECRET", msg)

    def test_credentials_from_env_accepts_profile_json_variable(self):
        env = {
            "gravity_pull_main_tc": json.dumps(
                {"consumerkey": "ck_profile", "consumer_secret": "cs_profile"}
            )
        }

        creds = credentials_from_env("gravity_pull_main_tc", environ=env)

        self.assertEqual(creds.profile, "gravity_pull_main_tc")
        self.assertEqual(creds.consumer_key, "ck_profile")
        self.assertEqual(creds.consumer_secret, "cs_profile")

    def test_client_sends_descriptive_user_agent(self):
        session = _RecordingSession()
        client = GravityFormsClient(
            consumer_key="ck",
            consumer_secret="cs",
            session=session,
        )

        client.discovery()

        headers = session.calls[0][2]["headers"]
        self.assertEqual(headers["Accept"], "application/json")
        self.assertIn("User-Agent", headers)
        self.assertNotIn("python-requests", headers["User-Agent"].lower())
        self.assertIn("text-automation", headers["User-Agent"])

    def test_client_uses_basic_auth_by_default(self):
        session = _RecordingSession()
        client = GravityFormsClient(
            consumer_key="ck",
            consumer_secret="cs",
            session=session,
        )

        client.forms()

        self.assertEqual(session.calls[0][2]["auth"], ("ck", "cs"))

    def test_redact_entry_masks_pii_but_preserves_location_grade_and_operational_fields(self):
        form = {
            "id": 1,
            "fields": [
                {"id": 1, "label": "Parent Name", "type": "name"},
                {"id": 2, "label": "Phone", "type": "phone"},
                {"id": 3, "label": "Email", "type": "email"},
                {"id": 4, "label": "Grade", "type": "select"},
                {"id": 5, "label": "Preferred Club Location", "type": "select"},
                {"id": 6, "label": "Ideal Location Tag", "type": "hidden"},
                {"id": 7, "label": "Comments", "type": "textarea"},
                {"id": 8, "label": "Postal Code", "type": "text"},
            ],
        }
        entry = {
            "id": "123",
            "form_id": "1",
            "date_created": "2026-05-16 10:25:00",
            "status": "active",
            "ip": "198.51.100.12",
            "source_url": "https://tutoringclub.com/?gf_page=preview&id=1",
            "user_agent": "Mozilla/5.0",
            "1": "Alex Parent",
            "2": "(555) 123-4567",
            "3": "alex@example.com",
            "4": "3rd Grade",
            "5": "Gilbert",
            "6": "ideal_gilbertaz",
            "7": "Needs help with fractions",
            "8": 90210,
        }

        redacted = redact_entry(entry, form)

        self.assertEqual(redacted["id"], "123")
        self.assertEqual(redacted["date_created"], "2026-05-16 10:25:00")
        self.assertEqual(redacted["status"], "active")
        self.assertEqual(redacted["source_url"], "https://tutoringclub.com/?gf_page=preview&id=1")
        self.assertEqual(redacted["4"], "3rd Grade")
        self.assertEqual(redacted["5"], "Gilbert")
        self.assertEqual(redacted["6"], "ideal_gilbertaz")
        self.assertEqual(redacted["1"], "[redacted:name]")
        self.assertEqual(redacted["2"], "[redacted:phone]")
        self.assertEqual(redacted["3"], "[redacted:email]")
        self.assertEqual(redacted["ip"], "[redacted:ip]")
        self.assertEqual(redacted["user_agent"], "[redacted:user_agent]")
        self.assertEqual(redacted["7"], "[redacted:text]")
        self.assertEqual(redacted["8"], "[redacted:text]")

    def test_build_shape_export_uses_discovery_forms_entries_and_mapping_candidates(self):
        form = {
            "id": 1,
            "title": "Main Direct Inquiry",
            "fields": [
                {"id": 1, "label": "Parent Name", "type": "name"},
                {"id": 2, "label": "Student Name", "type": "text"},
                {"id": 3, "label": "Phone", "type": "phone"},
                {"id": 4, "label": "Email", "type": "email"},
                {"id": 5, "label": "Grade", "type": "select"},
                {"id": 6, "label": "Preferred Club Location", "type": "select"},
                {"id": 7, "label": "Ideal Location Tag", "type": "hidden"},
            ],
        }
        entry = {
            "id": "321",
            "form_id": "1",
            "date_created": "2026-05-16 12:01:00",
            "status": "active",
            "1": "Alex Parent",
            "2": "Jordan Student",
            "3": "5551234567",
            "4": "alex@example.com",
            "5": "3rd Grade",
            "6": "Gilbert",
            "7": "ideal_gilbertaz",
        }
        client = _FakeClient(forms=[form], entries={1: [entry]})

        export = build_shape_export(client, profile="gravity_pull_main_tc", limit=25)

        self.assertEqual(export["profile"], "gravity_pull_main_tc")
        self.assertEqual(export["base_url"], "https://tutoringclub.com/")
        self.assertEqual(export["forms"][0]["id"], 1)
        self.assertEqual(export["forms"][0]["entries"][0]["1"], "[redacted:name]")
        self.assertEqual(export["forms"][0]["entries"][0]["7"], "ideal_gilbertaz")
        candidates = export["mapping_report"]["forms"][0]["candidates"]
        self.assertEqual(candidates["parent_name"][0]["field_id"], "1")
        self.assertEqual(candidates["student_name"][0]["field_id"], "2")
        self.assertEqual(candidates["phone"][0]["field_id"], "3")
        self.assertEqual(candidates["email"][0]["field_id"], "4")
        self.assertEqual(candidates["grade"][0]["field_id"], "5")
        self.assertEqual(candidates["preferred_location"][0]["field_id"], "6")
        self.assertEqual(candidates["ideal_location_tag"][0]["field_id"], "7")
        self.assertEqual(candidates["created_date"][0]["field_id"], "date_created")
        self.assertEqual(client.calls, [("discovery",), ("forms",), ("entries", 1, 25, 1, False, None)])

    def test_build_shape_export_fetches_detail_for_form_summaries(self):
        summary = {"id": 21, "title": "Summary Only", "entries": "https://example.test/entries"}
        detail = {
            "id": 21,
            "title": "Detailed Form",
            "fields": [{"id": 3, "label": "Email", "type": "email"}],
        }
        client = _FakeClient(forms=[summary], form_by_id={21: detail}, entries={21: []})

        export = build_shape_export(client, profile="gravity_pull_main_tc", limit=1)

        self.assertEqual(export["forms"][0]["title"], "Detailed Form")
        self.assertEqual(export["forms"][0]["fields"][0]["id"], "3")
        self.assertEqual(client.calls, [("discovery",), ("forms",), ("form", 21), ("entries", 21, 1, 1, False, None)])

    def test_forbidden_forms_without_form_ids_has_actionable_message(self):
        client = _FakeClient(forms_error=ForbiddenFormsError("forms forbidden"))

        with self.assertRaises(ForbiddenFormsError) as ctx:
            build_shape_export(client, profile="gravity_pull_main_tc", limit=25)

        self.assertIn("broader Gravity Forms read capability", str(ctx.exception))
        self.assertIn("--form-id", str(ctx.exception))

    def test_export_shape_to_file_writes_redacted_json(self):
        form = {
            "id": 2,
            "title": "Direct Inquiry",
            "fields": [{"id": 1, "label": "Email", "type": "email"}],
        }
        entry = {"id": "1", "form_id": "2", "date_created": "2026-05-16 10:00:00", "1": "alex@example.com"}
        client = _FakeClient(forms=[form], entries={2: [entry]})

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "shape.json"
            result = export_shape_to_file(client, out, profile="gravity_pull_main_tc", limit=1)

            self.assertEqual(result, out)
            text = out.read_text(encoding="utf-8")
            self.assertIn('"[redacted:email]"', text)
            self.assertNotIn("alex@example.com", text)

    def test_cli_wires_wordpress_gravity_forms_export_shape(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "wordpress",
                "gravity-forms",
                "export-shape",
                "--profile",
                "gravity_pull_main_tc",
                "--limit",
                "25",
                "--out",
                "exports/gravity_pull_main_tc_shape.json",
                "--form-id",
                "1",
                "--form-id",
                "2",
            ]
        )

        self.assertEqual(args.wp_cmd, "gravity-forms")
        self.assertEqual(args.gf_cmd, "export-shape")
        self.assertEqual(args.profile, "gravity_pull_main_tc")
        self.assertEqual(args.limit, 25)
        self.assertEqual(args.out, "exports/gravity_pull_main_tc_shape.json")
        self.assertEqual(args.form_id, [1, 2])
        self.assertEqual(args.auth_method, "basic")
        self.assertEqual(args.func.__name__, "cmd_wordpress_gravity_forms_export_shape")

    def test_client_mark_entry_read_fetches_full_entry_and_preserves_other_fields(self):
        full_entry = {"id": "321", "is_read": "0", "parent": "Alex Parent", "phone": "555-123", "meta": {"k": "v"}}
        session = _RecordingSession(
            payloads={
                "entry": _EntryResponse(full_entry),
                "put": _OkResponse(),
            }
        )
        client = GravityFormsClient(consumer_key="ck", consumer_secret="cs", session=session)

        client.mark_entry_read("321")

        self.assertEqual(session.calls[0][0], "GET")
        self.assertEqual(session.calls[1][0], "PUT")
        put_payload = session.calls[1][2]
        self.assertEqual(put_payload["is_read"], "1")
        self.assertEqual(put_payload["parent"], "Alex Parent")
        self.assertEqual(put_payload["phone"], "555-123")
        self.assertEqual(put_payload["meta"]["k"], "v")

    def test_client_entries_reads_filter_params_for_unread(self):
        session = _RecordingSession()
        client = GravityFormsClient(consumer_key="ck", consumer_secret="cs", session=session)

        client.entries(7, page_size=10, current_page=3, unread_only=True)

        request_args = session.calls[0]
        params = request_args[2]["params"]
        self.assertEqual(request_args[1], "https://tutoringclub.com/wp-json/gf/v2/forms/7/entries")
        self.assertEqual(params["paging[page_size]"], 10)
        self.assertEqual(params["paging[current_page]"], 3)
        self.assertEqual(
            json.loads(params["search"]),
            {"field_filters": [{"key": "is_read", "value": "0"}]},
        )

    def test_client_entries_rejects_preencoded_search_with_unread_filter(self):
        client = GravityFormsClient(consumer_key="ck", consumer_secret="cs", session=_RecordingSession())

        with self.assertRaises(Exception):
            client.entries(7, unread_only=True, search="abc")

    def test_cli_wires_wordpress_gravity_forms_direct_inquiry_commands(self):
        parser = build_parser()

        baseline = parser.parse_args(
            [
                "wordpress",
                "gravity-forms",
                "baseline-direct-inquiry",
                "--profile",
                "gravity_pull_main_tc",
                "--form-id",
                "7",
                "--dry-run",
            ]
        )
        self.assertEqual(baseline.wp_cmd, "gravity-forms")
        self.assertEqual(baseline.gf_cmd, "baseline-direct-inquiry")
        self.assertEqual(baseline.form_id, [7])
        self.assertTrue(baseline.dry_run)
        self.assertEqual(baseline.func.__name__, "cmd_wordpress_gravity_forms_baseline_direct_inquiry")

        process = parser.parse_args(
            [
                "wordpress",
                "gravity-forms",
                "process-direct-inquiry",
                "--profile",
                "gravity_pull_main_tc",
                "--form-id",
                "7",
                "--limit",
                "10",
                "--dry-run",
            ]
        )
        self.assertEqual(process.gf_cmd, "process-direct-inquiry")
        self.assertEqual(process.form_id, [7])
        self.assertEqual(process.limit, 10)
        self.assertEqual(process.func.__name__, "cmd_wordpress_gravity_forms_process_direct_inquiry")

    def test_direct_inquiry_gravity_forms_baseline_helper_uses_baseline_command(self):
        script = ROOT / "scripts" / "direct_inquiry_gravity_forms_baseline.bat"

        body = script.read_text(encoding="utf-8")

        self.assertIn(
            "uv run text-automation wordpress gravity-forms baseline-direct-inquiry",
            body,
        )
        self.assertIn("%EXTRA_ARGS%", body)
        self.assertIn("exit /b %EXIT_CODE%", body)
        self.assertNotIn("process-direct-inquiry", body)

    def test_cli_process_direct_inquiry_returns_failure_on_read_mark_error(self):
        parser = build_parser()
        args = parser.parse_args(["wordpress", "gravity-forms", "process-direct-inquiry"])

        with patch("text_automation.cli._build_gravity_forms_client", return_value=object()), patch(
            "text_automation.direct_inquiry.gravity_forms.process_direct_inquiry",
            return_value={"processed": 0, "errors": 1, "read_mark_fail": 1},
        ):
            exit_code = cli_mod.cmd_wordpress_gravity_forms_process_direct_inquiry(args)

        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
