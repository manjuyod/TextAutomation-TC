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

-- Inquiry follow-up cache with idempotent state tracking
CREATE TABLE IF NOT EXISTS InquiryFollowupCache (
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

CREATE INDEX IF NOT EXISTS idx_InquiryFollowupCache_istext
ON InquiryFollowupCache(IsText);

CREATE INDEX IF NOT EXISTS idx_InquiryFollowupCache_franchiseid
ON InquiryFollowupCache(FranchiseID);

CREATE INDEX IF NOT EXISTS idx_InquiryFollowupCache_inquirydate
ON InquiryFollowupCache(InquiryDate);

