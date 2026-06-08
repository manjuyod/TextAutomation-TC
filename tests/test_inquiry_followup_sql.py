import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.inquiry_followup import sql


class TestInquiryFollowupSql(unittest.TestCase):
    def test_sql_includes_franchise_id_alias(self):
        self.assertIn("tblInquiry.FranchiesId AS [FranchiseID]", sql.INQUIRY_SQL)

    def test_sql_includes_inquiry_and_lead_status_filter(self):
        self.assertIn("WHERE SubQuery.Status IN ('Inquiry', 'Lead')", sql.INQUIRY_SQL)

    def test_sql_selects_email_for_contact_email_fallback(self):
        self.assertIn("tblInquiry.Email AS [Email]", sql.INQUIRY_SQL)


if __name__ == "__main__":
    unittest.main()
