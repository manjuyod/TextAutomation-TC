import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from text_automation.common.dates import weekday_proper


class TestWeekdayProper(unittest.TestCase):
    def test_weekday_from_datetime(self):
        # 2025-10-06 is a Monday; 09:00 in LA
        dt = datetime(2025, 10, 6, 9, 0, tzinfo=ZoneInfo("America/Los_Angeles"))
        self.assertEqual(weekday_proper(dt), "Monday")

    def test_weekday_from_string_lower(self):
        self.assertEqual(weekday_proper("tuesday"), "Tuesday")


if __name__ == "__main__":
    unittest.main()
