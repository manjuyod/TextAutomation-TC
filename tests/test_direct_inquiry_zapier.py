import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.general.zapier import send_direct_inquiry


class _DummyResponse:
    def raise_for_status(self):
        return None


class TestDirectInquiryZapierMessage(unittest.TestCase):
    def _message_for_franchise(self, franchise_id: int) -> str:
        with patch.dict(os.environ, {"ZapHookDirectInquiry": "https://example.test/hook"}, clear=False):
            with patch("text_automation.general.zapier._get_local_now", return_value=datetime(2026, 2, 10, 13, 0, tzinfo=timezone.utc)):
                with patch("text_automation.general.zapier._is_on_winter_break", return_value=False):
                    with patch("text_automation.general.zapier.requests.post") as mock_post:
                        mock_post.return_value = _DummyResponse()
                        send_direct_inquiry(
                            parent_first_name="alex",
                            student_first_name="jordan",
                            phone="5551231234",
                            franchise_id=franchise_id,
                            grade_string="3rd Grade",
                        )
                        self.assertTrue(mock_post.called)
                        payload = mock_post.call_args.kwargs["json"]
                        return payload["message"]

    def test_franchise_20_includes_clovis_hours(self):
        msg = self._message_for_franchise(20)
        self.assertIn("Monday through Thursday from 11 AM to 8 PM.", msg)
        self.assertNotIn("Saturday From 10 AM to 2 PM.", msg)

    def test_franchise_57_still_includes_existing_hours(self):
        msg = self._message_for_franchise(57)
        self.assertIn("Monday through Thursday From 10 AM to 7 PM, and Saturday From 10 AM to 2 PM.", msg)

    def test_generic_franchise_has_no_explicit_hours_line(self):
        msg = self._message_for_franchise(24)
        self.assertNotIn("Monday through Thursday from 11 AM to 8 PM.", msg)
        self.assertNotIn("Saturday From 10 AM to 2 PM.", msg)


if __name__ == "__main__":
    unittest.main()
