-- SQLite partial unique indexes to enforce idempotent keys
-- Run with: sqlite3 src/text_automation/reporting/TextDatabase.db < scripts/sqlite_migrations.sql

-- Assessments: ensure one row per AssessmentID (when populated)
CREATE UNIQUE INDEX IF NOT EXISTS idx_assessmentcache_assessmentid_unique
ON AssessmentCache(AssessmentID)
WHERE AssessmentID IS NOT NULL;

-- Meetings: ensure one row per MeetingID (when populated)
CREATE UNIQUE INDEX IF NOT EXISTS idx_meetingcache_meetingid_unique
ON MeetingCache(MeetingID)
WHERE MeetingID IS NOT NULL;

