import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import shutil

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.inquiry_followup import cache
from text_automation.inquiry_followup import runner


def _init_cache_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE InquiryFollowupCache (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                InquiryID INTEGER NOT NULL,
                FranchiseID INTEGER NOT NULL,
                InquiryDate TEXT,
                ContactFirstName TEXT,
                StudentFirstName TEXT,
                ContactPhone TEXT,
                ContactEmail TEXT,
                MessageVariant TEXT NOT NULL DEFAULT 'standard',
                IsText TEXT NOT NULL DEFAULT 'No',
                TextedAtUtc TEXT,
                CreatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UpdatedAt TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_InquiryFollowupCache_inquiryid_unique
                ON InquiryFollowupCache(InquiryID);
            """
        )


def _row_df(
    inquiry_id: int,
    franchise_id: int = 87,
    phone: str = "5551112222",
    date_input: str = "2026-05-15",
    student: str = "Jordan",
    status: str = "Inquiry",
) -> dict:
    return {
        "InquiryID": inquiry_id,
        "FranchiseID": franchise_id,
        "DateInput": date_input,
        "ContactPhone": phone,
        "CFirstName": f"Parent {inquiry_id}",
        "StudentFirstName": student,
        "Email": f"parent{inquiry_id}@example.com",
        "Status": status,
    }


class TestInquiryFollowupRunner(unittest.TestCase):
    def _with_db(self):
        tmpdir = tempfile.mkdtemp()
        try:
            db = Path(tmpdir) / "TextDatabase.db"
            db.write_text("")
            _init_cache_db(db)
            with patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": str(db)}):
                yield str(db)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_run_dry_run_does_not_post_or_mark(self):
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame([_row_df(11)]),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook") as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=True, batch_size=50, max_batches=1)

            mock_post.assert_not_called()
            table = cache.select_cache()
            self.assertEqual(len(table), 1)
            self.assertEqual(table.loc[0, "IsText"], "No")
            self.assertEqual(sent, 0)
            break

    def test_run_filters_to_inquiry_or_lead_statuses(self):
        rows = [
            _row_df(1, status="Inquiry"),
            _row_df(2, status="Lead"),
            _row_df(3, status="Enrolled"),
            _row_df(4, status="Deleted"),
            _row_df(5, status="Meeting"),
            _row_df(6, status="Assessment"),
        ]
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame(rows),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=False, batch_size=50, max_batches=1, sleep_seconds=0)

            self.assertEqual(sent, 2)
            self.assertEqual(mock_post.call_count, 2)
            table = cache.select_cache()
            inquiry_ids = set(table["InquiryID"].astype(int).tolist())
            self.assertEqual(inquiry_ids, {1, 2})
            break

    def test_run_status_filter_is_case_insensitive_and_trimmed(self):
        rows = [
            _row_df(11, status=" inquiry "),
            _row_df(12, status="  LeaD  "),
            _row_df(13, status="eNaBled"),
            _row_df(14, status="  meeting  "),
        ]
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame(rows),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=False, batch_size=50, max_batches=1, sleep_seconds=0)

            self.assertEqual(sent, 2)
            self.assertEqual(mock_post.call_count, 2)
            table = cache.select_cache()
            inquiry_ids = set(table["InquiryID"].astype(int).tolist())
            self.assertEqual(inquiry_ids, {11, 12})
            break

    def test_run_prints_status_filter_summary(self):
        rows = [
            _row_df(21, status="Inquiry"),
            _row_df(22, status="Deleted"),
            _row_df(23, status="Assessment"),
            _row_df(24, status="Lead"),
            _row_df(25, status="Meeting"),
            _row_df(26, status=" Enrolled "),
        ]
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame(rows),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ), patch("builtins.print") as mock_print:
                sent = runner.run(dry_run=False, batch_size=50, max_batches=1, sleep_seconds=0)

            self.assertEqual(sent, 2)
            self.assertEqual(mock_post.call_count, 2)
            summary = next(
                (
                    entry.args[0]
                    for entry in mock_print.call_args_list
                    if isinstance(entry.args[0], dict)
                    and entry.args[0].get("inquiry_followup", {}).get("status_filter") == "skipped"
                ),
                None,
            )
            self.assertIsNotNone(summary)
            status_summary = summary["inquiry_followup"]
            self.assertEqual(status_summary["skipped"], 4)
            self.assertEqual(
                status_summary["statuses"],
                {"deleted": 1, "assessment": 1, "meeting": 1, "enrolled": 1},
            )
            self.assertIn("status_filter", status_summary)
            self.assertIn("skipped", status_summary)
            self.assertNotIn("InquiryID", status_summary["statuses"])
            break

    def test_existing_yes_is_skipped_for_eligible_statuses(self):
        rows = [_row_df(31, status="Inquiry"), _row_df(32, status="Lead")]
        for _tmp in self._with_db():
            cache.upsert_from_server(pd.DataFrame(rows))
            cache.mark_text_sent([31])

            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame(rows),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=False, batch_size=50, max_batches=1, sleep_seconds=0)

            self.assertEqual(sent, 1)
            self.assertEqual(mock_post.call_count, 1)
            table = cache.select_cache()
            yes_ids = set(table.loc[table["IsText"] == "Yes", "InquiryID"].astype(int).tolist())
            self.assertEqual(yes_ids, {31, 32})
            break

    def test_run_live_success_marks_yes(self):
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame([_row_df(21)]),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(
                    dry_run=False,
                    batch_size=50,
                    max_batches=1,
                    sleep_seconds=0,
                )

            self.assertEqual(sent, 1)
            self.assertEqual(mock_post.call_count, 1)
            table = cache.select_cache()
            self.assertEqual(table.loc[0, "IsText"], "Yes")
            break

    def test_run_live_failure_rolls_back_to_no(self):
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame([_row_df(31)]),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=False) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(
                    dry_run=False,
                    batch_size=50,
                    max_batches=1,
                    sleep_seconds=0,
                )

            self.assertEqual(sent, 0)
            self.assertEqual(mock_post.call_count, 1)
            table = cache.select_cache()
            self.assertEqual(table.loc[0, "IsText"], "No")
            break

    def test_existing_yes_is_skipped(self):
        for _tmp in self._with_db():
            cache.upsert_from_server(pd.DataFrame([_row_df(41)]))
            cache.mark_text_sent([41])

            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame([_row_df(41)]),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=False, batch_size=50, max_batches=1, sleep_seconds=0)

            self.assertEqual(sent, 0)
            self.assertEqual(mock_post.call_count, 0)
            self.assertEqual(cache.select_cache().loc[0, "IsText"], "Yes")
            break

    def test_runner_defaults_to_7_to_90_day_window(self):
        for _tmp in self._with_db():
            with patch("text_automation.inquiry_followup.runner.fetch_inquiries") as mock_fetch, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                mock_fetch.return_value = pd.DataFrame([_row_df(51)])
                runner.run(dry_run=True, batch_size=10, max_batches=1)

                self.assertEqual(mock_fetch.call_count, 1)
                args, kwargs = mock_fetch.call_args
                self.assertIn("lookback_days", kwargs)
                self.assertEqual(kwargs["lookback_days"], 90)
                self.assertIn("min_age_days", kwargs)
                self.assertEqual(kwargs["min_age_days"], 7)
                self.assertIsNone(kwargs.get("since"))
            break

    def test_max_batches_caps_sends(self):
        rows = [_row_df(i) for i in range(1, 6)]
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame(rows),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=False, batch_size=2, max_batches=1, sleep_seconds=0)

            self.assertEqual(sent, 2)
            self.assertEqual(mock_post.call_count, 2)
            table = cache.select_cache()
            yes_ids = set(table.loc[table["IsText"] == "Yes", "InquiryID"].astype(int).tolist())
            self.assertEqual(yes_ids, {1, 2})
            break

    def test_runner_defaults_to_max_batches_1(self):
        rows = [_row_df(i) for i in range(1, 6)]
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame(rows),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=False, batch_size=1, sleep_seconds=0)

            self.assertEqual(sent, 1)
            self.assertEqual(mock_post.call_count, 1)
            break

    def test_runner_caps_requested_max_batches_at_four(self):
        rows = [_row_df(i) for i in range(1, 10)]
        for _tmp in self._with_db():
            with patch(
                "text_automation.inquiry_followup.runner.fetch_inquiries",
                return_value=pd.DataFrame(rows),
            ), patch("text_automation.inquiry_followup.runner._post_to_webhook", return_value=True) as mock_post, patch(
                "text_automation.inquiry_followup.runner.time.sleep"
            ):
                sent = runner.run(dry_run=False, batch_size=1, max_batches=10, sleep_seconds=0)

            self.assertEqual(sent, 4)
            self.assertEqual(mock_post.call_count, 4)
            break

    def test_webhook_routing_uses_franchise_group_without_override(self):
        with patch.dict(
            os.environ,
            {
                "ZapHookMeetingGilVeg": "https://example.test/meeting-vegas",
                "ZapHookMeetingCali": "https://example.test/meeting-cali",
            },
            clear=False,
        ):
            from text_automation.inquiry_followup import runner

            self.assertEqual(
                runner._resolve_webhook(87, None),
                "https://example.test/meeting-cali",
            )
            self.assertEqual(
                runner._resolve_webhook(49, None),
                "https://example.test/meeting-cali",
            )

    def test_webhook_routing_uses_env_override_when_provided(self):
        with patch.dict(os.environ, {"ZapHookCustom": "https://override.example"}):
            from text_automation.inquiry_followup import runner

            self.assertEqual(
                runner._resolve_webhook(87, "ZapHookCustom"),
                "https://override.example",
            )


if __name__ == "__main__":
    unittest.main()
