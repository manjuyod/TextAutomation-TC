text-automation
===============

Modular text automation toolkit. This repository is being modernized to a clean, modular Python package with a CLI, managed by `uv`.

Quickstart (uv)
---------------

- Install uv (one-time): https://docs.astral.sh/uv/
- Ensure Python 3.11+ is available (uv can manage this for you)

Commands:

```
# From repo root
uv venv --python 3.12
uv run text-automation --help
uv run text-automation info
```

Development
-----------

- Project metadata and dependencies live in `pyproject.toml`.
- Source is under `src/text_automation`.
- Console entrypoint: `text-automation` (also `python -m text_automation`).

Migration Plan
--------------

- Keep existing scripts under `Legacy Files to Migrate and Implement/` intact.
- Gradually port functions into modular packages under `src/text_automation/`.
- Wire new CLI subcommands to the migrated modules as they land.

Packaging
---------

This project uses PEP 621 metadata with Hatchling for builds. You can build a wheel or sdist as needed, e.g. `uv build` (if uv has build tooling available) or `python -m build` if you have `build` installed.

General Use Utilities
---------------------

- Telegram
  - Env: `TCAutoBotToken`/`TCAutoChatID` or `TCLogBotToken`/`TCLogBotChatID`
  - Run: `uv run text-automation general telegram --message "Hello"`

- Email (Gmail SMTP)
  - Env: `AutoEmAd`, `AutoEmPs`
  - Text: `uv run text-automation general email text --subject "Hi" --to a@b.com --body "Message"`
  - Attach: `uv run text-automation general email attach --subject "Files" --to a@b.com --body "See attached" --base-path ./out --files file1.pdf file2.csv`

- Files (PDF merge)
  - `uv run text-automation general files merge-pdf --input ./pdfs --output ./merged.pdf`
  - With pattern: `--pattern "report-*.pdf"`
  - With explicit order: `--files 1.pdf 2.pdf 10.pdf`

- Schedule cleanup (SQL Server)
  - Env: `CRMSrvAddress`, `CRMSrvUs`, `CRMSrvPs`, `CRMSrvDb`
  - `uv run text-automation general schedule --scope all`

- Aggregate account balance (SQL Server)
  - Env: same as above
  - `uv run text-automation general aggregate account-balance --franchise-id 87 --out balances.csv`

- Reporting SQLite DB
  - Env: `TEXT_AUTOMATION_REPORT_DB` or add `text_automation.toml` with:
    
    ```toml
    [reporting]
    database = "src/text_automation/reporting/TextDatabase.db"
    ```

Direct Inquiry (Gravity Forms + Gmail)
--------------------------------------

- Main-site direct inquiries are pulled from Gravity Forms API v2. Gravity Forms `is_read` is the source of truth.
- Env: `gravity_pull_main_tc` should contain the Gravity Forms credential JSON (`consumerkey` and `consumer_secret`), or set `GRAVITY_PULL_MAIN_TC_CONSUMER_KEY` and `GRAVITY_PULL_MAIN_TC_CONSUMER_SECRET`.
- One-time baseline before scheduling live pulls:
  - `uv run text-automation wordpress gravity-forms baseline-direct-inquiry --dry-run`
  - `uv run text-automation wordpress gravity-forms baseline-direct-inquiry`
  - Windows helper: `scripts/direct_inquiry_gravity_forms_baseline.bat --dry-run`, then `scripts/direct_inquiry_gravity_forms_baseline.bat`
- Live pull:
  - `uv run text-automation wordpress gravity-forms process-direct-inquiry --limit 50 --dry-run`
  - Remove `--dry-run` to execute SQL/Zapier and mark Gravity Forms entries read after success.
  - Vegas Gravity Forms entries submitted during business hours are marked read without SQL/Zapier; after-hours entries still process.
  - Entries with no configured location match are terminal-skipped and marked read without SQL/Zapier; ambiguous matches and processing failures stay unread for retry/investigation.
- Gmail remains for location-specific notification emails only.
- Env: `InquiryAutoAPI` must contain the Gmail OAuth client JSON (as a string). First run opens a browser and writes a token to `src/text_automation/direct_inquiry/token.json` (configurable in `text_automation.toml`).
- Env: `ZapHookDirectInquiry` for outgoing Zapier webhook.
- Config: `text_automation.toml` holds `direct_inquiry.token_path`, `direct_inquiry.vegas_ids`, and the `[[franchises]]` table (id, name, url, director, email, timezone, preferred_locations).
- CLI:
  - `uv run text-automation direct-inquiry process --mode auto --max 50`
  - Modes: `auto` (Vegas after-hours only; others always), `all-day` (non-Vegas only; Vegas in-hours mark-as-read), `after-hours` (Vegas after-hours only)
  - `--dry-run` to avoid DB/Zapier/mark-as-read side effects

Student Intake (Gmail)
----------------------

- Purpose: Ingest Student Intake Form submission emails and upsert into `dpinket_TC_QA.dbo.tblTempStudentAuto` via stored procedures (`USP_InsertTempStudentAuto`/`USP_UpdateTempStudentAuto`).
- Env:
  - Uses the same Gmail OAuth client JSON format as Direct Inquiry: set `InquiryAutoAPI` (or legacy `StudentAutoAPI`).
  - SQL Server credentials: `CRMSrvAddress`, `CRMSrvUs`, `CRMSrvPs`, `CRMSrvDb`.
- Config: separate token path from Direct Inquiry to keep workflows isolated: `student_intake.token_path` (defaults to `src/text_automation/student_auto/token.json`).
- Routing:
  - Franchise is detected by matching the `student-intake-form` link against franchise `assessment_form` in `text_automation.toml`.
- CLI:
  - `uv run text-automation student-intake process --max 50 --dry-run`
  - Remove `--dry-run` to execute the stored procedure and mark the Gmail message as read.

Assessments and Meetings
------------------------

- Env: Zapier webhooks for messages
  - Assessments: `ZapHookAssessGilVeg` (vegas group), `ZapHookAssessCali` (cali group)
  - Meetings: `ZapHookMeetingGilVeg` (vegas group), `ZapHookMeetingCali` (cali group)
- Config: per-franchise fields in `text_automation.toml` used in messages and routing:
  - `assessment_form`, `payment_form`, `address`, `assess_group` (vegas/cali)
- CLI:
  - `uv run text-automation assessments scheduled --dry-run`
  - `uv run text-automation meetings scheduled --dry-run`
  - `uv run text-automation assessments morning --dry-run`
  - `uv run text-automation meetings morning --dry-run`
  - remove `--dry-run` to actually POST to Zapier
  - Scheduled flow uses local SQLite caches (`AssessmentCache`, `MeetingCache`) to detect reschedules and send once; morning-of flow uses no local cache.

- Meetings parent name resolution
  - Inputs: `GuardianFirstName`, `Parent1Name`, `Parent2Name` (from SQL)
  - Resolved to: `guardian_default`, `primary_parent`, `secondary_parent`
  - Rules:
    - Trim values; use only first names of parents
    - Invalid tokens `{n/a, na, not available, deceased, dead}` are ignored
    - If both parent first names are identical → fall back to guardian
    - If guardian name is contained in a parent’s first name → that parent becomes primary; the other becomes ` and {Name}`
    - Otherwise default to guardian
  - Implemented in: `src/text_automation/meetings/runner.py:_resolve_parent_names`

Inquiry Follow-Up
-----------------

- Purpose: Send a conservative follow-up text to older SQL Server records whose computed status is `Inquiry` or `Lead`.
- SQL Server env: `CRMSrvAddress`, `CRMSrvUs`, `CRMSrvPs`, `CRMSrvDb`
- Zapier routing:
  - Defaults to meeting webhook routing by franchise `assess_group`: `ZapHookMeetingGilVeg` for vegas, `ZapHookMeetingCali` for cali.
  - Override per run with `--webhook-env SomeEnvVar` if a dedicated inquiry follow-up webhook is needed.
- Cache:
  - Uses SQLite table `InquiryFollowupCache` from `[reporting].database`.
  - Apply `scripts/sqlite_migrations.sql` before first live use; do not directly edit or commit the SQLite DB binary.
  - Sends once per `InquiryID`. State moves `No -> Sending -> Yes`; failed live sends roll back to `No`.
- Eligibility:
  - Default centers are `87,49`.
  - Default date window is inquiries from 7 to 90 days old.
  - Use `--since YYYY-MM-DD` for an explicit historical backfill lower bound.
  - SQL filters to `Status IN ('Inquiry', 'Lead')`, and the runner repeats the same status guard before caching or sending.
  - Non-follow-up statuses such as `Enrolled`, `Deleted`, `Meeting`, `Meeting Follow Up`, `Assessment`, and `Other` are skipped and summarized without PII.
- CLI:
  - Dry-run preview: `uv run text-automation inquiry-followup run --dry-run`
  - Standard live run: `uv run text-automation inquiry-followup run`
  - Summer copy preview: `uv run text-automation inquiry-followup run --summer --dry-run`
  - Explicit centers and window: `uv run text-automation inquiry-followup run --franchise-id 87,49 --lookback-days 90 --min-age-days 7 --dry-run`
  - Historical backfill preview: `uv run text-automation inquiry-followup run --since 2026-01-01 --dry-run`
- Live guardrails:
  - `--batch-size` is capped at 50.
  - `--max-batches` is capped at 4, for a practical max of 200 live sends per run.
  - Live `--sleep-seconds` is forced to at least 3 seconds between sends.
  - No `--dry-run` means live webhook posts.

Windows Helpers
---------------

- Batch files under `scripts/` for quick usage or Task Scheduler setup:
  - scripts/assessments_scheduled.bat  runs Assessment1 scheduled flow
  - scripts/assessments_morning_57.bat  runs Assessment2 for franchise 57
  - scripts/assessments_morning_rest.bat  runs Assessment2 for all other configured franchises
  - scripts/meetings_scheduled.bat  runs Meeting1 scheduled flow
  - scripts/meetings_morning_57.bat  runs Meeting2 for franchise 57
  - scripts/meetings_morning_rest.bat  runs Meeting2 for all other configured franchises
  - scripts/combined_followup_workflow.bat - runs Gravity Forms Direct Inquiry, location-specific Gmail Direct Inquiry, Assessment1 scheduled, Meeting1 scheduled, and Student Intake (passes through extra args like --dry-run)
  - scripts/inquiry_followup_quarterly.bat - runs only Inquiry Follow-Up and forwards all extra args with `%*`, e.g. `scripts\inquiry_followup_quarterly.bat --max-batches 4 --dry-run`
  - scripts/direct_inquiry_gravity_forms_baseline.bat - marks unread main-site Gravity Forms Direct Inquiry entries read without SQL/Zapier. Run with --dry-run first.
  - scripts/direct_inquiry_auto.bat - runs Gravity Forms Direct Inquiry first, then location-specific Gmail Direct Inquiry. Pass --dry-run to avoid DB/Zapier/mark-as-read.
  - scripts/student_intake_auto.bat  runs Student Intake (max=50). Pass --dry-run to preview; note: dry-run still marks Gmail messages as read.

- For Task Scheduler, put the script path in "Program/script" and pass inquiry follow-up flags through "Add arguments (optional)"; the quarterly BAT forwards those flags directly to the CLI.

For Maintainers
---------------

- See `AGENTS.md` for an architectural overview, cache/idempotency policy, manual refresh behavior, and guidance for safe changes.

High-Frequency Runs
-------------------

- Running scheduled every 2 minutes is supported. Keep in mind:
  - DB load: frequent SQL queries; ensure your selection window and `TOP` limit cover needed rows.
  - Concurrency: avoid overlapping instances (Task Scheduler: set â€œDo not start a new instanceâ€).
  - Monthly delete: runs on day 1, deletes only sent rows missing by PK. Consider off-peak hours with a larger selection.
  - Reschedules: date/time changes reset `IsText='No'` and will re-send on the next run by design.

Poll vs Morning-Of
-------------------

- Scheduled (poll) flow uses local SQLite caches to enforce send-once semantics. It syncs from SQL Server, detects reschedules, and only sends for rows where `IsText='No'`.
- Morning-of flow targets "today" slices; no local SQLite cache.
- A single inquiry may receive both messages across the two flows without duplication within each flow.

Scheduling
----------

- Poll jobs (business hours):
  - `*/5 9-19 * * 1-6 uv run text-automation assessments scheduled`
  - `*/5 9-19 * * 1-6 uv run text-automation meetings scheduled`
- Morning-of jobs (early local time):
  - `15 7 * * 1-6 uv run text-automation assessments morning`
  - `20 7 * * 1-6 uv run text-automation meetings morning`

Idempotency
-----------

- Scheduled flow: local SQLite caches (`AssessmentCache`, `MeetingCache`) store the latest scheduled rows and mark `IsText = 'Yes'` after sending. Reschedules are detected by date/time changes and refreshed.
- Atomic send gate: each scheduled send performs an atomic claim `No → Sending → Yes`. Failures roll back to `No`, preventing tight loops and duplicate sends across overlapping runs.
- Morning-of flow: no local cache; selection is driven by SQL filters (e.g., only unsent/qualifying rows).

Reporting Utilities
-------------------

- Refresh caches from SQL Server (wipe + repopulate):
  - `uv run text-automation reporting refresh-cache --scope assessments|meetings|all [--limit N] [--dry-run] [--mark-sent]`
  - Behavior:
    - Deletes all rows from the selected cache table(s) and writes the current SQL selection.
    - By default, rows are written with `IsText='No'` (would trigger sends on the next scheduled run).
    - Add `--mark-sent` to write rows with `IsText='Yes'` so the next scheduled run does NOT re-send unless something changes (e.g., reschedule).
  - Recommended usage (end of day):
    - `uv run text-automation reporting refresh-cache --scope all --mark-sent`
    - Subsequent twoâ€‘minute scheduled runs will only send for genuinely new items or true reschedules.
  - Notes:
    - Scheduled upsert resets `IsText` to `'No'` when date/time changes.
- Monthly delete (day 1) only removes rows with `IsText='Yes'` that are missing by primary key (AssessmentID/MeetingID).
 - Partial unique indexes on server PKs (AssessmentID/MeetingID) prevent duplicate rows in caches. Apply with `sqlite3 src/text_automation/reporting/TextDatabase.db < scripts/sqlite_migrations.sql`.
- The same migration file creates `InquiryFollowupCache` and its indexes for inquiry follow-up idempotency. If a local environment already created the old lowercase table name, rename it once with `ALTER TABLE inquiry_followup_cache RENAME TO InquiryFollowupCache;`, then rerun the migration SQL.

Telegram Logging
----------------

- All workflows log to Telegram for remote visibility (uses `TCLogBotToken`/`TCLogBotChatID` and/or `TCAutoBotToken`/`TCAutoChatID`):
  - Direct Inquiry: header + generated SQL on dry-run and before live execute; `[ok]` or `[error]` summary after.
  - Student Intake: header + generated SQL on dry-run and before live execute; `[ok]` or `[error]` summary after.
  - Assessments: `[assessment][scheduled|morning]` headers per send (also on dry-run).
  - Meetings: `[meeting][scheduled|morning]` headers per send (also on dry-run).
  - Set `TCLogBotToken`/`TCLogBotChatID` for detailed logs, and `TCAutoBotToken`/`TCAutoChatID` for success/error summaries.

Config Requirements
--------------------

- SQL Server env: `CRMSrvAddress`, `CRMSrvUs`, `CRMSrvPs`, `CRMSrvDb`
- Reporting DB: `TEXT_AUTOMATION_REPORT_DB` or `[reporting].database` in TOML
- Zapier hooks: `ZapHookAssessGilVeg`, `ZapHookAssessCali`, `ZapHookMeetingGilVeg`, `ZapHookMeetingCali`
- Inquiry Follow-Up uses `ZapHookMeetingGilVeg`/`ZapHookMeetingCali` by default unless `--webhook-env` points to another webhook env var.
- Optional: extend business hours via TOML later and wire into `direct_inquiry/business_hours.py`.

What I Did
----------

- Adopted uv for environment and dependency management:
  - Verified uv is installed: `uv --version` â†’ 0.8.22.
  - Project already initialized; `pyproject.toml` present, so `uv init` not needed (uv reports already initialized).
  - Created local virtual environment: `uv venv --python 3.12` â†’ `.venv/`.
  - Synced environment and generated lockfile: `uv sync` â†’ `uv.lock` created and all deps installed.
  - Confirmed CLI works via uv: `uv run text-automation --help`.

- Dependency audit and alignment (via import scan under `src/`):
  - Thirdâ€‘party imports detected: `pandas`, `sqlalchemy`, `pyodbc`, `PyPDF2`, `requests`, `beautifulsoup4` (`bs4`), `google-api-python-client`, `google-auth-oauthlib`, `tzdata`.
  - These already exist in `[project.dependencies]` of `pyproject.toml`; no missing packages to add.
  - Builtâ€‘ins used (no packages needed): `argparse`, `email`, `sqlite3`, `zoneinfo`, `smtplib`, etc.

- Modern scaffold: `pyproject.toml`, Hatchling, `src/` layout, CLI entrypoint.
- Config system: `text_automation.toml` + loader (`src/text_automation/config.py`).
- Migrated GeneralUseScripts to modules with CLI:
  - DB engine + helpers (`db/sql.py`), query store (`db/queries.py`).
  - Telegram utility with constants (`general/telegram.py`).
  - Email senders (`general/email.py`).
  - PDF merge (`general/files.py`).
  - Schedule cleanup (`general/schedule.py`).
  - Account balance aggregation (`general/aggregate.py`).
  - Reporting SQLite helpers (`reporting/sqlite_db.py`).
- Unified DirectToInquiry:
  - Gmail API OAuth via `InquiryAutoAPI`, token stored at `direct_inquiry.token_path`.
  - Robust business-hours with `zoneinfo`; Vegas IDs configurable.
  - Non-overlapping modes (auto/all-day/after-hours) and Vegas in-hours auto mark-as-read.
  - HTML parsing + normalization migrated; raw SQL insert preserved.
  - Zapier send moved to `general/zapier.py` and reused.
- CLI commands: `general ...` and `direct-inquiry process` wired and lazy-imported.

- Migrated Student Intake ingestion:
  - Added module `student_auto.processor` to parse Student Intake emails and execute the appropriate stored procedure.
  - Reuses Gmail OAuth/token path from Direct Inquiry (supports `InquiryAutoAPI` or `StudentAutoAPI`).
  - Added CLI: `student-intake process` with `--max` and `--dry-run`.

- Migrated Assessments/Meetings flows:
  - Added modules: `assessments` and `meetings` with data, cache, messaging, and runner orchestration.
  - New CLI:
    - `uv run text-automation assessments scheduled [--dry-run]`
    - `uv run text-automation meetings scheduled [--dry-run]`
    - `uv run text-automation assessments morning [--dry-run] [--franchise-id 6,11] [--since 2025-09-30] [--until 2025-10-01] [--limit 200]`
    - `uv run text-automation meetings morning [--dry-run] [--franchise-id 6,11] [--since 2025-09-30] [--until 2025-10-01] [--limit 200]`
- Scheduled runs maintain a local SQLite cache (`AssessmentCache`, `MeetingCache`) and mark `IsText='Yes'` after successful sends. Reschedules (normalized date/time changes) reset to `IsText='No'`.
  - Morning-of flow: no local cache; rely on SQL selection.

- Config and TOML updates:
  - Per-franchise fields in `text_automation.toml`: `assessment_form`, `payment_form`, `address`, and `assess_group` (vegas/cali) used to route webhooks and personalize messages.
  - Direct Inquiry now reads `phone_blacklist`, `grade_phrase_map`, and `grade_sql_map` from TOML (with sensible defaults).

To Do
-----

- Update or deprecate legacy DirectToInquiry scripts and StudentAutoToDB script to call the new CLI; then remove legacy duplicates safely.
- Optional: add a processed Gmail label to avoid relying solely on mark-as-read.
- Expand business hours per-franchise via TOML if policies differ.
- Improve logging (structured logs, log levels via CLI/config) and add error telemetry if needed.
- Add lightweight unit tests for parser/processor logic (dry-run paths), keeping external calls mocked.

Assessment Morning Dedupe (Assessment2)
---------------------------------------

- Problem: Morning-of assessments could send multiple texts for the same `InquiryID` when SQL returned multiple rows (e.g., one per student). The runner iterated per-row and reused the row-level `StudentString`.
- Fix: Group the morning selection by `InquiryID`, aggregate student names, and send exactly once per inquiry.
- Implementation:
  - New utility: `src/text_automation/general/student_names.py`
    - `parse_student_names(raw)` splits on commas/semicolons/“and”/&/slashes/pipes/plus/newlines, extracts first names, preserves order, and de-duplicates.
    - `format_student_names(first_names, max_names=4)` produces natural strings with Oxford-style “and”.
  - Morning runner (`src/text_automation/assessments/runner.py:morning_to_webhook`):
    - `df.groupby("InquiryID")` then aggregate `StudentString` across the group; use the first row’s franchise/guardian/phone/date/time as representative.
    - In-process guard: `seen_inquiries` set ensures one attempt per InquiryID per run.
    - DEBUG log per InquiryID with `inquiry_id`, formatted names, and `phone`.
- Validation:
  - `uv run text-automation assessments morning --dry-run --limit 50`
  - Expect one DEBUG and one send attempt per InquiryID per run.
  - Check the greeting shows only first names with proper punctuation and “and” rules.
- Idempotency: Morning-of flow remains cache-less; dedupe is enforced by SQL window + grouping. Re-running within the same window produces the same one-per-inquiry attempts.
- Rollback: Remove the import of `general.student_names` and revert the grouping loop in `assessments/runner.py` to the prior row-wise iteration.
