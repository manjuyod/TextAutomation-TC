import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.cli import build_parser, cmd_inquiry_followup_run


class TestInquiryFollowupCLI(unittest.TestCase):
    def test_run_parser_accepts_new_flags(self):
        parser = build_parser()

        args = parser.parse_args(
            [
                "inquiry-followup",
                "run",
                "--franchise-id",
                "87,49",
                "--dry-run",
                "--summer",
                "--lookback-days",
                "45",
                "--min-age-days",
                "10",
                "--batch-size",
                "25",
                "--max-batches",
                "3",
                "--sleep-seconds",
                "4.5",
            ]
        )

        self.assertEqual(args.if_cmd, "run")
        self.assertEqual(args.franchise_id, "87,49")
        self.assertTrue(args.summer)
        self.assertTrue(args.dry_run)
        self.assertEqual(args.lookback_days, 45)
        self.assertEqual(args.min_age_days, 10)
        self.assertEqual(args.batch_size, 25)
        self.assertEqual(args.max_batches, 3)
        self.assertAlmostEqual(args.sleep_seconds, 4.5)

    def test_defaults_for_inquiry_followup_run(self):
        parser = build_parser()

        args = parser.parse_args(["inquiry-followup", "run"])

        self.assertEqual(args.if_cmd, "run")
        self.assertEqual(args.franchise_id, "87,49")
        self.assertFalse(args.summer)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.lookback_days, 90)
        self.assertEqual(args.min_age_days, 7)
        self.assertEqual(args.batch_size, 50)
        self.assertEqual(args.max_batches, 1)
        self.assertEqual(args.sleep_seconds, 3)

    def test_cmd_inquiry_followup_run_wires_csv_to_list_and_all_flags(self):
        parser = build_parser()
        args = parser.parse_args(
            [
                "inquiry-followup",
                "run",
                "--franchise-id",
                "87,49",
                "--summer",
                "--since",
                "2026-01-01",
                "--batch-size",
                "25",
                "--max-batches",
                "2",
                "--sleep-seconds",
                "10",
            ]
        )

        with patch("text_automation.inquiry_followup.run") as mock_run:
            with patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": ":memory:"}):
                cmd_inquiry_followup_run(args)

        self.assertEqual(mock_run.call_count, 1)
        call_kwargs = mock_run.call_args.kwargs
        self.assertEqual(call_kwargs["franchise_ids"], [87, 49])
        self.assertTrue(call_kwargs["summer"])
        self.assertEqual(call_kwargs["since"], "2026-01-01")
        self.assertEqual(call_kwargs["batch_size"], 25)
        self.assertEqual(call_kwargs["max_batches"], 2)
        self.assertEqual(call_kwargs["sleep_seconds"], 10)
        self.assertFalse(call_kwargs["dry_run"])

    def test_cmd_inquiry_followup_run_wires_dry_run_flag(self):
        parser = build_parser()
        args = parser.parse_args(["inquiry-followup", "run", "--franchise-id", "87,49", "--dry-run"])

        with patch("text_automation.inquiry_followup.run") as mock_run:
            cmd_inquiry_followup_run(args)

        self.assertTrue(mock_run.call_args.kwargs["dry_run"])

    def test_cmd_inquiry_followup_run_defaults_live(self):
        parser = build_parser()
        args = parser.parse_args(["inquiry-followup", "run"])

        with patch("text_automation.inquiry_followup.run") as mock_run:
            cmd_inquiry_followup_run(args)

        self.assertFalse(mock_run.call_args.kwargs["dry_run"])


if __name__ == "__main__":
    unittest.main()
