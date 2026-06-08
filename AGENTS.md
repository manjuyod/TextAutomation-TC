Agent Guide: Text Automation Repo
=================================

This document orients future agents to the project design, where things live, and how to make safe changes.

High-Level Overview
-------------------

- Package entrypoint: `text_automation.cli:main` (script name `text-automation`).
- Two main flows per entity type:
  - Assessments: Scheduled (Assessment1) and Morning-of (Assessment2)
  - Meetings: Scheduled (Meeting1) and Morning-of (Meeting2)
- Inquiry Follow-Up:
  - Quarterly-safe follow-up for older SQL records whose computed status is `Inquiry` or `Lead`
  - Uses a SQLite send-once cache and explicit CLI batching guardrails
- Sources:
  - SQL Server (reads/writes via `src/text_automation/db/sql.py`)
  - SQLite cache for scheduled idempotency in `text_automation.toml:[reporting].database`

Key Paths
---------

- CLI and command wiring: `src/text_automation/cli.py`
- Config loader: `src/text_automation/config.py` (reads `text_automation.toml`)
- Assessments:
  - Data queries: `src/text_automation/assessments/data.py`
  - Message composition: `src/text_automation/assessments/messages.py`
  - Cache ops: `src/text_automation/assessments/cache.py`
  - Orchestrator: `src/text_automation/assessments/runner.py`
- Meetings:
  - Data queries: `src/text_automation/meetings/data.py`
  - Message composition: `src/text_automation/meetings/messages.py`
  - Cache ops: `src/text_automation/meetings/cache.py`
  - Orchestrator: `src/text_automation/meetings/runner.py`
- Inquiry Follow-Up:
  - Data queries: `src/text_automation/inquiry_followup/sql.py`
  - Message composition: `src/text_automation/inquiry_followup/messages.py`
  - Cache ops: `src/text_automation/inquiry_followup/cache.py`
  - Orchestrator: `src/text_automation/inquiry_followup/runner.py`
- Reporting/SQLite helper: `src/text_automation/reporting/sqlite_db.py`
- Manual cache refresh utility: `src/text_automation/utility/refresh_cache.py`

Environment & Config
--------------------

- `text_automation.toml` controls runtime:
  - `[reporting].database` → path to SQLite DB (e.g. `src/text_automation/reporting/TextDatabase.db`)
  - `[direct_inquiry].token_path` & `[student_intake].token_path` → Gmail token files
  - `[[franchises]]` → per-franchise fields used for routing and message personalization
- Env vars:
  - SQL Server: `CRMSrvAddress`, `CRMSrvUs`, `CRMSrvPs`, `CRMSrvDb`
  - Zapier (webhooks): Assessments: `ZapHookAssessGilVeg`, `ZapHookAssessCali`; Meetings: `ZapHookMeetingGilVeg`, `ZapHookMeetingCali`
  - Inquiry Follow-Up: defaults to the meeting webhooks by franchise group unless `--webhook-env` points to an override env var
  - Gmail OAuth JSON: `InquiryAutoAPI` (and optional `StudentAutoAPI`)

Flows & Idempotency
-------------------

- Scheduled (Assessment1 / Meeting1)
  - Reads recent rows from SQL Server
  - Upserts into SQLite cache with send-once semantics:
    - New rows inserted with `IsText='No'`
    - If date/time changed (normalized), row updated and `IsText` reset to `'No'` (reschedule triggers new send)
    - Selection to send uses rows where `IsText='No'`, then marks `IsText='Yes'`
  - Safe monthly delete (day 1 only): deletes only rows with `IsText='Yes'` whose SQL PK is missing (AssessmentID/MeetingID)
- Morning-of (Assessment2 / Meeting2)
  - Direct read from SQL Server window; no local cache read/write
  - Duplicates are avoided by schedule/cadence, not a cache
- Inquiry Follow-Up
  - SQL query computes status, filters to `Inquiry` and `Lead`, and pages SQL Server reads.
  - Runner defensively filters again to only `Inquiry` and `Lead` before cache upsert/send.
  - Default CLI window is 7-90 days old: `--lookback-days 90`, `--min-age-days 7`.
  - `--since YYYY-MM-DD` overrides the lower bound for historical backfills.
  - Default centers are `--franchise-id 87,49`.
  - Live guardrails clamp `--batch-size` to 50, `--max-batches` to 4, and live `--sleep-seconds` to at least 3.
  - No `--dry-run` means live webhook sends.

Caches (SQLite)
---------------

- DB path from TOML: `[reporting].database`
- Tables expected (pre-existing or created externally): `AssessmentCache`, `MeetingCache`, `InquiryFollowupCache`
- Columns seen in production DBs:
  - AssessmentCache: `ID, AutomationStage, InquiryID, FranchiseID, AssessmentDate, AssessmentTime, AssessmentEmail, AssessmentPhone, GuardianFirstName, StudentString, IsText, (optional) AssessmentID`
  - MeetingCache:    `ID, AutomationStage, InquiryID, FranchiseID, MeetingID, MeetingDate, MeetingTime, AssessmentEmail, AssessmentPhone, CurrentDate, GuardianFirstName, StudentString, Grade, Parent1Name, Parent2Name, IsText`
  - InquiryFollowupCache: `ID, InquiryID, FranchiseID, InquiryDate, ContactFirstName, StudentFirstName, ContactPhone, ContactEmail, MessageVariant, IsText, TextedAtUtc, CreatedAt, UpdatedAt`
- Cache operations live in `assessments/cache.py` and `meetings/cache.py`:
  - `upsert_from_server(df)` → insert/update records; reset IsText on reschedule
  - `pending_to_text()` → select `IsText='No'`
  - `mark_text_sent(ids)` → set `IsText='Yes'`
  - `delete_missing_sent_by_pk(pks)` → monthly delete (day 1), sent rows only, missing by PK
- Inquiry follow-up cache operations live in `inquiry_followup/cache.py`:
  - New rows are inserted with `IsText='No'`.
  - Existing `Yes` rows stay sent; copy variants do not trigger another send.
  - Live send state is `No -> Sending -> Yes`; failures roll back to `No`.
  - Table naming convention is PascalCase: use `InquiryFollowupCache`, not `inquiry_followup_cache`.

Manual Cache Refresh
--------------------

- CLI: `text-automation reporting refresh-cache --scope assessments|meetings|all [--limit N] [--dry-run] [--no-mark-sent]`
  - Default seeds rows with `IsText='Yes'` to avoid re-sending on the next scheduled run
  - Pass `--no-mark-sent` to seed with `IsText='No'` (will send on next run)
  - Verbose logs print fetch/delete/write counts and columns

Message Composition
-------------------

- Assessments: `assessments/messages.py`
  - Stage-aware content; franchise 8 and 20 have tailored intros
  - Link block includes assessment/payment links; Assessment2 also includes a map/address line
  - Closing varies by stage and franchise group
- Meetings: `meetings/messages.py`
  - Stage-aware; Meeting1 has tailored content for franchises 8 (Huy) and 20 (Katie)
  - Meeting2 (morning) confirms “today at HH:MM” and conditionally adds a laptop/Chromebook note
  - Parent name resolution:
    - Inputs: `GuardianFirstName`, `Parent1Name`, `Parent2Name`
    - Helper: `meetings/runner.py:_resolve_parent_names`
    - Rules:
      - Trim names; extract first names for parents
      - Ignore invalid tokens: `n/a`, `na`, `not available`, `deceased`, `dead`
      - If both parent first names are identical → fall back to guardian
      - If guardian name is contained in a parent’s first name → that parent is primary; the other becomes ` and {Name}`
      - Otherwise default to guardian
    - The message builder capitalizes names consistently (and preserves “and” lowercasing)
- Inquiry Follow-Up: `inquiry_followup/messages.py`
  - Standard copy asks whether the contact is still interested in tutoring.
  - `--summer` uses a franchise-local time greeting and the TOML franchise name.
  - If the TOML name contains `Tutoring Club of`, use it as-is; otherwise say `Tutoring Club of {name}`.

Concurrency & Scheduling
------------------------

- Concurrency: scheduled flows implement an atomic claim → send → finalize sequence to prevent duplicates across overlapping runs.
  - State transitions: `No` → `Sending` → `Yes` (failure rolls back to `No`).
  - Prefer single-instance scheduling (Task Scheduler: set “Do not start a new instance”).
- Inquiry Follow-Up also uses the atomic `No -> Sending -> Yes` gate and should be scheduled as a single instance.

Windows Batch Helpers
---------------------

- Assessments:
  - `scripts/assessments_scheduled.bat`
  - `scripts/assessments_morning_57.bat`
  - `scripts/assessments_morning_rest.bat`
- Meetings:
  - `scripts/meetings_scheduled.bat`
  - `scripts/meetings_morning_57.bat`
  - `scripts/meetings_morning_rest.bat`
- Combined scheduled (assessments then meetings):
  - `scripts/combined_followup_workflow.bat` (forwards extra args like `--dry-run`)
- Inquiry Follow-Up:
  - `scripts/inquiry_followup_quarterly.bat` runs only `text-automation inquiry-followup run` and forwards all extra args with `%*`.
  - In Task Scheduler, put flags such as `--max-batches 4 --dry-run` in "Add arguments (optional)".
  - Leave `scripts/combined_followup_workflow.bat` unchanged for frequent scheduled jobs; do not wire quarterly follow-up into high-frequency runs.

Testing & Dry-Runs
------------------

- Safe preview (no network writes): add `--dry-run` to CLI commands
- Morning-of flows can be filtered:
  - `--franchise-id 1,57`, `--since YYYY-MM-DD`, `--until YYYY-MM-DD`, `--limit N`
- Inquiry Follow-Up SQL-only checks:
  - `uv run pytest -q tests/test_inquiry_followup_sql.py`
  - `uv run text-automation inquiry-followup run --help`
  - For live-data sanity checks, start with `--dry-run --max-batches 1`.

Known Gotchas / Notes
---------------------

- Assessments/Data uses `TOP ...`; ensure the selection covers all rows you intend to manage, especially on the 1st (monthly delete).
- Morning flows do not update any server “sent” flags; rely on cadence to avoid repeats.
- Time normalization removes fractional seconds to avoid false reschedule detection.
- If you alter cache schemas, adjust `_align_df_to_table` in `utility/refresh_cache.py` or update cache writers accordingly.
- Inquiry Follow-Up should never cache or send rows whose post-query status is not `Inquiry` or `Lead`.
- Do not directly edit or commit `src/text_automation/reporting/TextDatabase.db`; apply `scripts/sqlite_migrations.sql` to runtime DBs outside the commit.

Making Changes Safely
---------------------

1. Update TOML and confirm via `uv run text-automation info`.
2. For message copy changes, adjust only in `assessments/messages.py`, `meetings/messages.py`, or `inquiry_followup/messages.py` and test with small limits + `--dry-run`.
3. For cache logic, keep `IsText` semantics and monthly delete contract intact unless a policy change is intended.
4. For new franchises, add entries in TOML and (if necessary) widen IN-lists in SQL queries.
5. When in doubt, coordinate with maintainers and include a README note for operational impacts.

