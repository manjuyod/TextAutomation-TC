import os
import sys
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.accounts.quo import client as quo_client
from text_automation.config import load_config


class _DummyResponse:
    status_code = 202
    text = ""


class TestQuoClient(unittest.TestCase):
    def test_normalize_phone_e164(self):
        self.assertEqual(quo_client.normalize_phone_e164("5551234567"), "+15551234567")
        self.assertEqual(quo_client.normalize_phone_e164("15551234567"), "+15551234567")
        self.assertEqual(quo_client.normalize_phone_e164("+15551234567"), "+15551234567")
        self.assertIsNone(quo_client.normalize_phone_e164(""))
        self.assertIsNone(quo_client.normalize_phone_e164("12345"))

    def test_send_text_posts_to_quo(self):
        env = {
            "JAX_Quo": "api-key",
            "JAX_Quo_From": "PN123abc",
            "JAX_Quo_UserId": "US123abc",
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("text_automation.accounts.quo.client.requests.post") as mock_post:
                mock_post.return_value = _DummyResponse()

                ok = quo_client.send_text("Hello", "5551234567")

        self.assertTrue(ok)
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "api-key")
        self.assertEqual(kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(kwargs["json"]["content"], "Hello")
        self.assertEqual(kwargs["json"]["from"], "PN123abc")
        self.assertEqual(kwargs["json"]["to"], ["+15551234567"])
        self.assertEqual(kwargs["json"]["userId"], "US123abc")

    def test_send_text_accepts_json_env(self):
        env = {
            "JAX_Quo": '{"api_key":"api-key","from":"PNjson","user_id":"USjson"}',
        }
        with patch.dict(os.environ, env, clear=True):
            with patch("text_automation.accounts.quo.client.requests.post") as mock_post:
                mock_post.return_value = _DummyResponse()

                ok = quo_client.send_text("Hello", "5551234567")

        self.assertTrue(ok)
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["headers"]["Authorization"], "api-key")
        self.assertEqual(kwargs["json"]["from"], "PNjson")
        self.assertEqual(kwargs["json"]["userId"], "USjson")

    def test_invalid_phone_does_not_post(self):
        env = {"JAX_Quo": "api-key", "JAX_Quo_From": "PN123abc"}
        with patch.dict(os.environ, env, clear=True):
            with patch("text_automation.accounts.quo.client.requests.post") as mock_post:
                ok = quo_client.send_text("Hello", "12345")

        self.assertFalse(ok)
        mock_post.assert_not_called()


class TestQuoRouting(unittest.TestCase):
    def test_assessment_franchises_62_and_95_are_gated(self):
        from text_automation.assessments import messages

        with patch("text_automation.assessments.messages.requests.post") as mock_post:
            ok_62 = messages.send_to_webhook(62, "Hello", "5551234567")
            ok_95 = messages.send_to_webhook(95, "Hello", "5551234567")

        self.assertTrue(ok_62)
        self.assertTrue(ok_95)
        mock_post.assert_not_called()

    def test_meeting_franchises_62_and_95_are_gated(self):
        from text_automation.meetings import messages

        with patch("text_automation.meetings.messages.requests.post") as mock_post:
            ok_62 = messages.send_to_webhook(62, "Hello", "5551234567")
            ok_95 = messages.send_to_webhook(95, "Hello", "5551234567")

        self.assertTrue(ok_62)
        self.assertTrue(ok_95)
        mock_post.assert_not_called()

    def test_inquiry_followup_franchises_62_and_95_are_gated(self):
        from text_automation.inquiry_followup import runner

        with patch("text_automation.inquiry_followup.runner.fetch_inquiries") as mock_fetch:
            with patch("text_automation.inquiry_followup.runner.requests.post") as mock_post:
                sent_62 = runner.run(franchise_id=62, dry_run=False)
                sent_95 = runner.run(franchise_id=95, dry_run=False)

        self.assertEqual(sent_62, 0)
        self.assertEqual(sent_95, 0)
        mock_fetch.assert_not_called()
        mock_post.assert_not_called()

    def test_east_q_does_not_fall_back_to_zapier(self):
        from text_automation.assessments import messages as assessment_messages
        from text_automation.meetings import messages as meeting_messages
        from text_automation.inquiry_followup import runner

        env = {
            "ZapHookAssessGilVeg": "https://example.test/assess-vegas",
            "ZapHookAssessCali": "https://example.test/assess-cali",
            "ZapHookMeetingGilVeg": "https://example.test/meeting-vegas",
            "ZapHookMeetingCali": "https://example.test/meeting-cali",
            "ZapHookOverride": "https://example.test/override",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertIsNone(assessment_messages._webhook_for_franchise(62))
            self.assertIsNone(assessment_messages._webhook_for_franchise(95))
            self.assertIsNone(meeting_messages._webhook_for_franchise(62))
            self.assertIsNone(meeting_messages._webhook_for_franchise(95))
            self.assertIsNone(runner._resolve_webhook(62, "ZapHookOverride"))
            self.assertIsNone(runner._resolve_webhook(95, "ZapHookOverride"))


class TestHodgesConfig(unittest.TestCase):
    def test_hodges_config_loads(self):
        cfg = load_config()
        hodges = next(f for f in cfg.franchises if f.id == 95)
        self.assertEqual(hodges.name, "Hodges")
        self.assertEqual(hodges.director, "Michele")
        self.assertEqual(hodges.email, "hodgesfl@tutoringclub.com")
        self.assertEqual(hodges.timezone, "America/New_York")
        self.assertEqual(hodges.assessment_form, "https://tutoringclub.com/hodgesfl/student-intake-form/")
        self.assertEqual(hodges.payment_form, "https://tutoringclub.com/hodgesfl/assessment-payment-form/")
        self.assertEqual(hodges.address, "13546 Beach Boulevard Jacksonville, FL 32224 US")
        self.assertEqual(hodges.assess_group, "east_q")

    def test_jacksonville_config_loads(self):
        cfg = load_config()
        jacksonville = next(f for f in cfg.franchises if f.id == 62)
        self.assertEqual(jacksonville.name, "Tutoring Club of Jacksonville")
        self.assertEqual(jacksonville.director, "Michele")
        self.assertEqual(jacksonville.email, "jacksonvillefl@tutoringclub.com")
        self.assertEqual(jacksonville.timezone, "America/New_York")
        self.assertEqual(jacksonville.assessment_form, "https://tutoringclub.com/jacksonvillefl/student-intake-form/")
        self.assertEqual(jacksonville.payment_form, "https://tutoringclub.com/jacksonvillefl/assessment-payment-form/")
        self.assertEqual(jacksonville.address, "13546 Beach Boulevard Jacksonville, FL 32224 US")
        self.assertEqual(jacksonville.assess_group, "east_q")


if __name__ == "__main__":
    unittest.main()
