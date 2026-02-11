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
    database = "C:/path/to/ReportDatabase.db"
    ```

Direct Inquiry (Gmail)
----------------------

- Env: `InquiryAutoAPI` must contain the Gmail OAuth client JSON (as a string). First run will open a browser and write a token to `Legacy Files to Migrate and Implement/DirectToInquiryPackage/token.json` (configurable in `text_automation.toml`).
- Env: `ZapHookDirectInquiry` for outgoing Zapier webhook.
- Config: `text_automation.toml` holds `direct_inquiry.token_path`, `direct_inquiry.vegas_ids`, and the `[[franchises]]` table (id, name, url, director, email, timezone).
- CLI:
  - `uv run text-automation direct-inquiry process --mode auto --max 50` (recommended)
  - Modes: `auto` (Vegas after-hours only; others always), `all-day` (non-Vegas only; Vegas in-hours mark-as-read), `after-hours` (Vegas after-hours only)
  - `--dry-run` to avoid DB/Zapier/mark-as-read side effects

What I Did
----------

- Adopted uv for environment and dependency management:
  - Verified uv is installed: `uv --version` → 0.8.22.
  - Project already initialized; `pyproject.toml` present, so `uv init` not needed (uv reports already initialized).
  - Created local virtual environment: `uv venv --python 3.12` → `.venv/`.
  - Synced environment and generated lockfile: `uv sync` → `uv.lock` created and all deps installed.
  - Confirmed CLI works via uv: `uv run text-automation --help`.

- Dependency audit and alignment (via import scan under `src/`):
  - Third‑party imports detected: `pandas`, `sqlalchemy`, `pyodbc`, `PyPDF2`, `requests`, `beautifulsoup4` (`bs4`), `google-api-python-client`, `google-auth-oauthlib`, `tzdata`.
  - These already exist in `[project.dependencies]` of `pyproject.toml`; no missing packages to add.
  - Built‑ins used (no packages needed): `argparse`, `email`, `sqlite3`, `zoneinfo`, `smtplib`, etc.

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

To Do
-----

- Update or deprecate legacy DirectToInquiry scripts to call the new CLI; then remove legacy duplicates safely.
- Migrate remaining Assessment/Meeting flows into `src/text_automation/` and expose via CLI.
- Optional: add a processed Gmail label to avoid relying solely on mark-as-read.
- Expand business hours per-franchise via TOML if policies differ.
- Parameterize blacklist and grade mappings in TOML (currently in code).
- Improve logging (structured logs, log levels via CLI/config) and add error telemetry if needed.
- Add lightweight unit tests for parser/processor logic (dry-run paths), keeping external calls mocked.
