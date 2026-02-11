import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import unittest
from datetime import datetime

from text_automation.assessments.messages import generate_message


class TestAssessmentMessageWeekday(unittest.TestCase):
    def test_assessment_morning_template_weekday_default(self):
        dt = datetime(2025, 10, 6, 9, 0)  # Monday, naive
        time_str = dt.strftime("%I:%M %p")
        msg = generate_message(
            franchise_id=1,
            automation_stage="Assessment2",
            parent_first_name="Alex",
            student_names="Jordan",
            assessment_date=dt,
            assessment_time_str=time_str,
        )
        self.assertIn("on Monday,", msg)
        self.assertNotIn("monday", msg)

    def test_assessment_morning_template_weekday_franchise_20(self):
        dt = datetime(2025, 10, 6, 9, 0)  # Monday, naive
        time_str = dt.strftime("%I:%M %p")
        msg = generate_message(
            franchise_id=20,
            automation_stage="Assessment2",
            parent_first_name="Alex",
            student_names="Jordan",
            assessment_date=dt,
            assessment_time_str=time_str,
        )
        self.assertIn("visit with us Monday.", msg)
        self.assertNotIn("monday", msg)


if __name__ == "__main__":
    unittest.main()
