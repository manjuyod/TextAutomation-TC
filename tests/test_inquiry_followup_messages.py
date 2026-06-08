import sys
from datetime import datetime, timezone
from pathlib import Path
import unittest

from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.inquiry_followup.messages import build_message


class TestInquiryFollowupMessageCopy(unittest.TestCase):
    def test_standard_copy_uses_expected_phrase_and_student_phrase(self):
        msg = build_message(
            contact_first="alex",
            student_first="jordan",
            franchise_id=87,
        )

        self.assertIn(
            "Hey Alex, We haven't spoken in a while. Would you still be interested in some tutoring for Jordan?",
            msg,
        )
        self.assertIn("If this is something that interests you, I'd be happy to have a conversation.", msg)

    def test_standard_copy_without_student_has_base_phrase_only(self):
        msg = build_message(contact_first="Sam", student_first=None, franchise_id=87)

        self.assertIn(
            "Hey Sam, We haven't spoken in a while. Would you still be interested in some tutoring?",
            msg,
        )
        self.assertIn("If this is something that interests you, I'd be happy to have a conversation.", msg)

    def test_standard_copy_without_contact_uses_hello(self):
        msg = build_message(contact_first=None, student_first="Kai", franchise_id=87)
        self.assertIn(
            "Hello, We haven't spoken in a while. Would you still be interested in some tutoring for Kai?",
            msg,
        )

    def test_summer_copy_uses_franchise_specific_location_for_downey(self):
        now = datetime(2026, 6, 1, 21, 0, tzinfo=timezone.utc)  # 14:00 in America/Los_Angeles
        msg = build_message(
            contact_first="Sam",
            student_first=None,
            franchise_id=87,
            summer=True,
            now_utc=now,
        )

        self.assertIn("Good afternoon Sam,", msg)
        self.assertIn(
            "This is the Tutoring Club of Downey. You previously reached out to us about tutoring, and since summer is almost here, we wanted to reconnect.",
            msg,
        )
        self.assertIn(
            "We're currently offering a complimentary assessment if you schedule within the next two weeks. Summer is a great time to help students fill in learning gaps, preview next year's courses, or tackle SAT prep. It's also a fantastic way to keep their minds active and engaged (and give them a productive break from screen time!).",
            msg,
        )
        self.assertIn(
            "Let me know if you'd like to grab a spot on our calendar. Hope you're having a great week!",
            msg,
        )

    def test_summer_copy_preserves_tutoring_club_of_name(self):
        now = datetime(2026, 6, 1, 21, 0, tzinfo=timezone.utc)  # 14:00 in America/Los_Angeles
        msg = build_message(
            contact_first="Sam",
            student_first="Kai",
            franchise_id=49,
            summer=True,
            now_utc=now,
        )

        self.assertIn("Good afternoon Sam,", msg)
        self.assertIn("Tutoring Club of Bakersfield", msg)
        self.assertNotIn("This is the Tutoring Club of Tutoring Club of", msg)
        self.assertIn(
            "This is the Tutoring Club of Bakersfield. You previously reached out to us about tutoring, and since summer is almost here, we wanted to reconnect.",
            msg,
        )

    def test_summer_copy_uses_hello_without_contact(self):
        now = datetime(2026, 6, 1, 21, 0, tzinfo=timezone.utc)  # 14:00 in America/Los_Angeles
        msg = build_message(
            contact_first="",
            student_first=None,
            franchise_id=87,
            summer=True,
            now_utc=now,
        )

        self.assertIn("Good afternoon,", msg)


if __name__ == "__main__":
    unittest.main()
