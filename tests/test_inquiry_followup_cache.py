import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
import shutil

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.inquiry_followup import cache


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


def _run_with_temp_db(func):
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Path(tmpdir) / "TextDatabase.db"
        db.write_text("")
        _init_cache_db(db)
        func(str(db))


class TestInquiryFollowupCache(unittest.TestCase):
    def test_cache_table_constant(self):
        self.assertEqual(cache.TABLE, "InquiryFollowupCache")

    def _run(self, callback):
        tmpdir = tempfile.mkdtemp()
        try:
            db = Path(tmpdir) / "TextDatabase.db"
            db.write_text("")
            _init_cache_db(db)
            return callback(db)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_upsert_preserves_existing_yes_state(self):
        def _check(db_path: Path):
            with unittest.mock.patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": str(db_path)}):
                base = pd.DataFrame(
                    [
                        {
                            "InquiryID": 1001,
                            "FranchiseID": 87,
                            "InquiryDate": "2026-06-01",
                            "ContactFirstName": "Alex",
                            "StudentFirstName": "Jordan",
                            "ContactPhone": "5551234",
                            "MessageVariant": "standard",
                            "ContactEmail": "alex@example.com",
                        }
                    ]
                )
                cache.upsert_from_server(base, message_variant="standard")
                cache.mark_text_sent([1001])

                cache.upsert_from_server(base, message_variant="standard")
                rows = cache.select_cache()

                self.assertEqual(len(rows), 1)
                self.assertEqual(rows.loc[0, "IsText"], "Yes")
                self.assertEqual(rows.loc[0, "MessageVariant"], "standard")

        self._run(_check)

    def test_upsert_does_not_reset_yes_on_changes(self):
        def _check(db_path: Path):
            with unittest.mock.patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": str(db_path)}):
                cache.upsert_from_server(
                    pd.DataFrame(
                        [
                            {
                                "InquiryID": 2001,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-01-01",
                                "ContactFirstName": "Alex",
                                "ContactPhone": "111",
                                "MessageVariant": "standard",
                                "StudentFirstName": "Jordan",
                                "ContactEmail": "alex@example.com",
                            }
                        ]
                    )
                )
                cache.mark_text_sent([2001])

                cache.upsert_from_server(
                    pd.DataFrame(
                        [
                            {
                                "InquiryID": 2001,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-02-02",
                                "ContactFirstName": "Alex",
                                "ContactPhone": "222",
                                "MessageVariant": "summer",
                                "StudentFirstName": "Jordan",
                                "ContactEmail": "new@example.com",
                            }
                        ]
                    ),
                    message_variant="summer",
                )

                rows = cache.select_cache()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows.loc[0, "IsText"], "Yes")
                self.assertEqual(rows.loc[0, "ContactPhone"], "222")
                self.assertEqual(rows.loc[0, "InquiryDate"], "2026-02-02")
                self.assertEqual(rows.loc[0, "MessageVariant"], "summer")

        self._run(_check)

    def test_upsert_does_not_reset_sending_state(self):
        def _check(db_path: Path):
            with unittest.mock.patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": str(db_path)}):
                cache.upsert_from_server(
                    pd.DataFrame(
                        [
                            {
                                "InquiryID": 3001,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-01-01",
                                "ContactFirstName": "Sam",
                                "ContactPhone": "333",
                                "MessageVariant": "standard",
                                "StudentFirstName": "Jordan",
                                "ContactEmail": "sam@example.com",
                            }
                        ]
                    )
                )
                row_id = int(cache.select_cache().loc[0, "ID"])
                cache.claim_row_for_send(row_id)

                cache.upsert_from_server(
                    pd.DataFrame(
                        [
                            {
                                "InquiryID": 3001,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-03-03",
                                "ContactFirstName": "Sam",
                                "ContactPhone": "444",
                                "MessageVariant": "summer",
                                "StudentFirstName": "Jordan",
                                "ContactEmail": "sam2@example.com",
                            }
                        ]
                    ),
                    message_variant="summer",
                )
                rows = cache.select_cache()
                self.assertEqual(rows.loc[0, "IsText"], "Sending")

        self._run(_check)

    def test_upsert_uses_email_fallback(self):
        def _check(db_path: Path):
            with unittest.mock.patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": str(db_path)}):
                cache.upsert_from_server(
                    pd.DataFrame(
                        [
                            {
                                "InquiryID": 4001,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-04-04",
                                "ContactFirstName": "Lee",
                                "ContactPhone": "555",
                                "MessageVariant": "standard",
                                "StudentFirstName": "Jordan",
                                "Email": "sql-email@example.com",
                            }
                        ]
                    )
                )

                row = cache.select_cache().iloc[0]
                self.assertEqual(row["ContactEmail"], "sql-email@example.com")

        self._run(_check)

    def test_migration_text_uses_pascal_case_cache_table_name(self):
        migration_text = (ROOT / "scripts" / "sqlite_migrations.sql").read_text(encoding="utf-8")
        self.assertIn(
            "CREATE TABLE IF NOT EXISTS InquiryFollowupCache",
            migration_text,
        )
        self.assertIn(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_InquiryFollowupCache_inquiryid_unique",
            migration_text,
        )
        self.assertIn("ON InquiryFollowupCache(InquiryID)", migration_text)

    def test_pending_to_text_respects_date_window_and_status(self):
        def _check(db_path: Path):
            with unittest.mock.patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": str(db_path)}):
                cache.upsert_from_server(
                    pd.DataFrame(
                        [
                            {
                                "InquiryID": 1,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-05-01",
                                "ContactFirstName": "Alex",
                                "ContactPhone": "111",
                                "MessageVariant": "standard",
                                "ContactEmail": "a@x.com",
                            },
                            {
                                "InquiryID": 2,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-05-15",
                                "ContactFirstName": "Sam",
                                "ContactPhone": "222",
                                "MessageVariant": "standard",
                                "ContactEmail": "b@x.com",
                            },
                            {
                                "InquiryID": 3,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-05-12",
                                "ContactFirstName": "Jen",
                                "ContactPhone": "333",
                                "MessageVariant": "standard",
                                "ContactEmail": "c@x.com",
                            },
                        ]
                    )
                )
                cache.mark_text_sent([3])

                rows = cache.pending_to_text(lower_bound="2026-05-02", upper_bound="2026-05-20")
                inquiry_ids = set(int(x) for x in rows.get("InquiryID", []))

                self.assertEqual(inquiry_ids, {2})

        self._run(_check)

    def test_claim_send_revert_cycle(self):
        def _check(db_path: Path):
            with unittest.mock.patch.dict(os.environ, {"TEXT_AUTOMATION_REPORT_DB": str(db_path)}):
                cache.upsert_from_server(
                    pd.DataFrame(
                        [
                            {
                                "InquiryID": 7,
                                "FranchiseID": 87,
                                "InquiryDate": "2026-03-03",
                                "ContactFirstName": "Alex",
                                "StudentFirstName": "Jordan",
                                "ContactPhone": "999",
                                "MessageVariant": "standard",
                                "ContactEmail": "x@x.com",
                            }
                        ]
                    )
                )
                row_id = int(cache.select_cache().loc[0, "ID"])

                self.assertTrue(cache.claim_row_for_send(row_id))
                self.assertFalse(cache.claim_row_for_send(row_id))

                cache.mark_text_sent_by_row_ids([row_id])
                state = cache.select_cache().loc[0, "IsText"]
                self.assertEqual(state, "Yes")

                cache.revert_row_to_pending(row_id)
                state = cache.select_cache().loc[0, "IsText"]
                self.assertEqual(state, "No")

        self._run(_check)


if __name__ == "__main__":
    unittest.main()
