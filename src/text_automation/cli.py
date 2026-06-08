from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_config
# Heavy modules are imported lazily inside command handlers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="text-automation",
        description="Modular text automation toolkit",
    )
    parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show version and exit",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # Placeholder commands to be wired to real functionality as we migrate code.
    p_info = subparsers.add_parser(
        "info", help="Show environment and project info"
    )
    p_info.set_defaults(func=cmd_info)

    # general group
    p_gen = subparsers.add_parser("general", help="General utilities")
    gen_sub = p_gen.add_subparsers(dest="general_cmd")

    # telegram
    p_tg = gen_sub.add_parser("telegram", help="Send a Telegram message")
    p_tg.add_argument("--message", required=True)
    p_tg.add_argument("--token")
    p_tg.add_argument("--chat")
    p_tg.set_defaults(func=cmd_general_telegram)

    # email
    p_email = gen_sub.add_parser("email", help="Email helpers")
    email_sub = p_email.add_subparsers(dest="email_cmd")

    p_email_text = email_sub.add_parser("text", help="Send text email")
    p_email_text.add_argument("--subject", required=True)
    p_email_text.add_argument("--to", nargs="+", required=True)
    p_email_text.add_argument("--body", required=True)
    p_email_text.set_defaults(func=cmd_email_text)

    p_email_att = email_sub.add_parser("attach", help="Send email with attachments")
    p_email_att.add_argument("--subject", required=True)
    p_email_att.add_argument("--to", nargs="+", required=True)
    p_email_att.add_argument("--body", required=True)
    p_email_att.add_argument("--base-path", required=True)
    p_email_att.add_argument("--files", nargs="+", required=True)
    p_email_att.set_defaults(func=cmd_email_attach)

    # files
    p_files = gen_sub.add_parser("files", help="File utilities")
    files_sub = p_files.add_subparsers(dest="files_cmd")
    p_merge = files_sub.add_parser("merge-pdf", help="Merge PDFs in a directory")
    p_merge.add_argument("--input", required=True, help="Input directory with PDFs")
    p_merge.add_argument("--output", required=True, help="Output PDF path")
    p_merge.add_argument("--pattern", default=None, help="Glob pattern (default: *.pdf)")
    p_merge.add_argument("--files", nargs="+", default=None, help="Explicit file list relative to --input")
    p_merge.set_defaults(func=cmd_files_merge_pdf)

    # schedule
    p_sched = gen_sub.add_parser("schedule", help="Schedule utilities")
    p_sched.add_argument(
        "--scope",
        choices=["master", "session", "all"],
        default="all",
        help="Which table(s) to clear null StudentId1 from",
    )
    p_sched.set_defaults(func=cmd_schedule_clear)

    # aggregate
    p_ag = gen_sub.add_parser("aggregate", help="Aggregations")
    ag_sub = p_ag.add_subparsers(dest="ag_cmd")
    p_acc = ag_sub.add_parser("account-balance", help="Aggregate account balance by franchise")
    p_acc.add_argument("--franchise-id", type=int, required=True)
    p_acc.add_argument("--batch-size", type=int, default=1000)
    p_acc.add_argument("--max-workers", type=int, default=3)
    p_acc.add_argument("--out", help="Optional CSV output path")
    p_acc.set_defaults(func=cmd_aggregate_account_balance)

    # direct inquiry
    p_di = subparsers.add_parser("direct-inquiry", help="Process direct inquiry emails")
    di_sub = p_di.add_subparsers(dest="di_cmd")
    p_di_proc = di_sub.add_parser("process", help="Process unread messages")
    p_di_proc.add_argument("--mode", choices=["auto", "all-day", "after-hours"], default="auto")
    p_di_proc.add_argument("--max", type=int, default=50)
    p_di_proc.add_argument("--dry-run", action="store_true")
    p_di_proc.set_defaults(func=cmd_direct_inquiry_process)

    # student intake
    p_si = subparsers.add_parser("student-intake", help="Process Student Intake Form emails")
    si_sub = p_si.add_subparsers(dest="si_cmd")
    p_si_proc = si_sub.add_parser("process", help="Process unread Student Intake messages")
    p_si_proc.add_argument("--max", type=int, default=10)
    p_si_proc.add_argument("--dry-run", action="store_true")
    p_si_proc.set_defaults(func=cmd_student_intake_process)

    # assessments flow
    p_as = subparsers.add_parser("assessments", help="Assessment notifications")
    as_sub = p_as.add_subparsers(dest="as_cmd")
    p_as_sched = as_sub.add_parser("scheduled", help="Notify for scheduled assessments (webhook)")
    p_as_sched.add_argument("--dry-run", action="store_true")
    p_as_sched.set_defaults(func=cmd_assessments_scheduled)
    p_as_morn = as_sub.add_parser("morning", help="Morning-of confirmations for assessments")
    p_as_morn.add_argument("--dry-run", action="store_true")
    p_as_morn.add_argument("--franchise-id", help="Single ID or comma-separated list")
    p_as_morn.add_argument("--since", help="ISO8601 lower bound override (server time)")
    p_as_morn.add_argument("--until", help="ISO8601 upper bound override (server time)")
    p_as_morn.add_argument("--limit", type=int, help="Max rows")
    p_as_morn.set_defaults(func=cmd_assessments_morning)

    # meetings flow
    p_me = subparsers.add_parser("meetings", help="Meeting notifications")
    me_sub = p_me.add_subparsers(dest="me_cmd")
    p_me_sched = me_sub.add_parser("scheduled", help="Notify for scheduled meetings (webhook)")
    p_me_sched.add_argument("--dry-run", action="store_true")
    p_me_sched.set_defaults(func=cmd_meetings_scheduled)
    p_me_morn = me_sub.add_parser("morning", help="Morning-of confirmations for meetings")
    p_me_morn.add_argument("--dry-run", action="store_true")
    p_me_morn.add_argument("--franchise-id", help="Single ID or comma-separated list")
    p_me_morn.add_argument("--since", help="ISO8601 lower bound override (server time)")
    p_me_morn.add_argument("--until", help="ISO8601 upper bound override (server time)")
    p_me_morn.add_argument("--limit", type=int, help="Max rows")
    p_me_morn.set_defaults(func=cmd_meetings_morning)

    # reporting flow
    p_rep = subparsers.add_parser("reporting", help="Reporting and cache utilities")
    rep_sub = p_rep.add_subparsers(dest="rep_cmd")
    p_rep_refresh = rep_sub.add_parser(
        "refresh-cache",
        help="Delete and repopulate AssessmentCache/MeetingCache from SQL Server",
    )
    p_rep_refresh.add_argument(
        "--scope",
        choices=["assessments", "meetings", "all"],
        default="all",
        help="Which cache(s) to refresh",
    )
    p_rep_refresh.add_argument("--limit", type=int, help="Limit rows inserted per table")
    p_rep_refresh.add_argument("--dry-run", action="store_true")
    # By default, mark rows as sent to avoid triggering sends. Use --no-mark-sent to opt out.
    p_rep_refresh.add_argument(
        "--no-mark-sent",
        action="store_false",
        dest="mark_sent",
        help="Write rows with IsText='No' instead of 'Yes'",
    )
    p_rep_refresh.set_defaults(mark_sent=True)
    p_rep_refresh.set_defaults(func=cmd_reporting_refresh_cache)

    # inquiry follow-up
    p_if = subparsers.add_parser(
        "inquiry-followup", help="Inquiry follow-up by last contact recency"
    )
    if_sub = p_if.add_subparsers(dest="if_cmd")
    p_if_run = if_sub.add_parser("run", help="Run follow-up selection and send")
    p_if_run.add_argument("--franchise-id", default="87,49")
    p_if_run.add_argument("--since", default=None, help="ISO8601 lower bound override (server date)")
    p_if_run.add_argument("--lookback-days", type=int, default=90, help="Search window lower bound in days")
    p_if_run.add_argument("--min-age-days", type=int, default=7, help="Max age in days to send")
    p_if_run.add_argument("--summer", action="store_true", help="Use summer message variant with local greeting")
    p_if_run.add_argument(
        "--webhook-env",
        type=str,
        default=None,
        help="Env var name for Zap webhook (e.g., ZapHookInquiryFollowup)",
    )
    p_if_run.add_argument("--dry-run", action="store_true", help="Skip webhook posts")
    p_if_run.add_argument("--batch-size", type=int, default=50, help="Per-batch send limit (max 50)")
    p_if_run.add_argument("--max-batches", type=int, default=1, help="Max number of batches to send in one run")
    p_if_run.add_argument("--sleep-seconds", type=float, default=3, help="Delay between sends when live")
    p_if_run.set_defaults(func=cmd_inquiry_followup_run)

    # wordpress / gravity forms shape study
    p_wp = subparsers.add_parser("wordpress", help="WordPress integrations")
    wp_sub = p_wp.add_subparsers(dest="wp_cmd")
    p_gf = wp_sub.add_parser("gravity-forms", help="Gravity Forms REST API utilities")
    gf_sub = p_gf.add_subparsers(dest="gf_cmd")
    p_gf_export = gf_sub.add_parser("export-shape", help="Export redacted Gravity Forms shape data")
    p_gf_export.add_argument("--profile", default="gravity_pull_main_tc")
    p_gf_export.add_argument("--limit", type=int, default=25)
    p_gf_export.add_argument("--out", required=True)
    p_gf_export.add_argument("--base-url", default="https://tutoringclub.com/")
    p_gf_export.add_argument("--auth-method", choices=["basic", "oauth1"], default="basic")
    p_gf_export.add_argument("--form-id", action="append", type=int, default=None)
    p_gf_export.set_defaults(func=cmd_wordpress_gravity_forms_export_shape)

    p_gf_baseline = gf_sub.add_parser(
        "baseline-direct-inquiry",
        help="Mark unread Gravity Forms direct-inquiry rows as read without processing",
    )
    p_gf_baseline.add_argument("--profile", default="gravity_pull_main_tc")
    p_gf_baseline.add_argument("--limit", type=int, default=None)
    p_gf_baseline.add_argument("--dry-run", action="store_true")
    p_gf_baseline.add_argument("--base-url", default="https://tutoringclub.com/")
    p_gf_baseline.add_argument("--auth-method", choices=["basic", "oauth1"], default="basic")
    p_gf_baseline.add_argument("--form-id", action="append", type=int, default=None)
    p_gf_baseline.set_defaults(func=cmd_wordpress_gravity_forms_baseline_direct_inquiry)

    p_gf_process = gf_sub.add_parser(
        "process-direct-inquiry",
        help="Normalize and process unread Gravity Forms direct-inquiry rows",
    )
    p_gf_process.add_argument("--profile", default="gravity_pull_main_tc")
    p_gf_process.add_argument("--limit", type=int, default=50)
    p_gf_process.add_argument("--form-id", action="append", type=int, default=None)
    p_gf_process.add_argument("--dry-run", action="store_true")
    p_gf_process.add_argument("--base-url", default="https://tutoringclub.com/")
    p_gf_process.add_argument("--auth-method", choices=["basic", "oauth1"], default="basic")
    p_gf_process.set_defaults(func=cmd_wordpress_gravity_forms_process_direct_inquiry)

    return parser


def cmd_info(_args: argparse.Namespace) -> int:
    cfg = load_config()
    print("text-automation")
    print(f"version: {__version__}")
    print(f"python: {sys.version.split()[0]}")
    print(f"env: {cfg.env}")
    print(f"legacy_root: {cfg.legacy_root or 'not found'}")
    return 0


def cmd_general_telegram(args: argparse.Namespace) -> int:
    from .general import telegram as telegram_mod

    telegram_mod.send_message(args.message, args.token, args.chat)
    print("sent")
    return 0


def cmd_email_text(args: argparse.Namespace) -> int:
    from .general import email as email_mod

    email_mod.send_text(subject=args.subject, recipients=args.to, body=args.body)
    print("sent")
    return 0


def cmd_email_attach(args: argparse.Namespace) -> int:
    from .general import email as email_mod

    email_mod.send_with_attachments(
        subject=args.subject,
        recipients=args.to,
        body=args.body,
        base_path=args.base_path,
        attachments=args.files,
    )
    print("sent")
    return 0


def cmd_files_merge_pdf(args: argparse.Namespace) -> int:
    from .general import files as files_mod

    files_mod.merge_pdfs(
        input_dir=args.input,
        output_file=args.output,
        pattern=args.pattern,
        explicit_files=args.files,
    )
    print(args.output)
    return 0


def cmd_schedule_clear(args: argparse.Namespace) -> int:
    from .general import schedule as schedule_mod

    scope = args.scope
    if scope == "master":
        schedule_mod.clear_null_master_students()
    elif scope == "session":
        schedule_mod.clear_null_session_students()
    else:
        schedule_mod.clear_all_null_students()
    print("cleared")
    return 0


def cmd_aggregate_account_balance(args: argparse.Namespace) -> int:
    from .general import aggregate as aggregate_mod

    df = aggregate_mod.aggregate_account_balance(
        franchise_id=args.franchise_id,
        batch_size=args.batch_size,
        max_workers=args.max_workers,
    )
    if args.out:
        import pandas as _pd

        out_path = args.out
        _pd.DataFrame(df).to_csv(out_path, index=False)
        print(out_path)
    else:
        print(len(df))
    return 0


def cmd_direct_inquiry_process(args: argparse.Namespace) -> int:
    from .direct_inquiry import processor as di_proc

    count = di_proc.process(mode=args.mode, max_results=args.max, dry_run=args.dry_run)
    print(count)
    return 0


def cmd_student_intake_process(args: argparse.Namespace) -> int:
    from .student_auto import processor as si_proc

    count = si_proc.process(max_results=args.max, dry_run=args.dry_run)
    print(count)
    return 0


def cmd_assessments_scheduled(args: argparse.Namespace) -> int:
    from .assessments import runner as as_runner

    count = as_runner.scheduled_to_webhook(dry_run=args.dry_run)
    print(count)
    return 0


def cmd_meetings_scheduled(args: argparse.Namespace) -> int:
    from .meetings import runner as me_runner

    count = me_runner.scheduled_to_webhook(dry_run=args.dry_run)
    print(count)
    return 0


def _parse_id_list(val: str | None) -> list[int] | None:
    if not val:
        return None
    try:
        return [int(x.strip()) for x in val.split(",") if x.strip()]
    except Exception:
        return None


def cmd_assessments_morning(args: argparse.Namespace) -> int:
    from .assessments import runner as as_runner

    fids = _parse_id_list(args.franchise_id)
    count = as_runner.morning_to_webhook(
        dry_run=args.dry_run,
        franchise_ids=fids,
        since=args.since,
        until=args.until,
        limit=args.limit,
    )
    print(count)
    return 0


def cmd_meetings_morning(args: argparse.Namespace) -> int:
    from .meetings import runner as me_runner

    fids = _parse_id_list(args.franchise_id)
    count = me_runner.morning_to_webhook(
        dry_run=args.dry_run,
        franchise_ids=fids,
        since=args.since,
        until=args.until,
        limit=args.limit,
    )
    print(count)
    return 0


def cmd_reporting_refresh_cache(args: argparse.Namespace) -> int:
    from .utility import refresh_cache as rc

    scope = args.scope
    limit = args.limit
    dry = args.dry_run
    mark_sent = getattr(args, "mark_sent", False)
    if scope == "assessments":
        deleted, written = rc.refresh_assessment_cache(limit=limit, dry_run=dry, mark_sent=mark_sent)
        print({"table": "AssessmentCache", "deleted": deleted, "written": written, "dry_run": dry, "mark_sent": mark_sent})
    elif scope == "meetings":
        deleted, written = rc.refresh_meeting_cache(limit=limit, dry_run=dry, mark_sent=mark_sent)
        print({"table": "MeetingCache", "deleted": deleted, "written": written, "dry_run": dry, "mark_sent": mark_sent})
    else:
        res = rc.refresh_both(limit=limit, dry_run=dry, mark_sent=mark_sent)
        print(res)
    return 0


def cmd_inquiry_followup_run(args: argparse.Namespace) -> int:
    from .inquiry_followup import run as if_run

    count = if_run(
        franchise_ids=_parse_id_list(args.franchise_id),
        since=args.since,
        lookback_days=args.lookback_days,
        min_age_days=args.min_age_days,
        summer=args.summer,
        webhook_env=args.webhook_env,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        sleep_seconds=args.sleep_seconds,
        dry_run=args.dry_run,
    )
    print(count)
    return 0


def cmd_wordpress_gravity_forms_export_shape(args: argparse.Namespace) -> int:
    from .wordpress.gravity_forms import (
        GravityFormsClient,
        GravityFormsError,
        credentials_from_env,
        export_shape_to_file,
    )

    try:
        creds = credentials_from_env(args.profile)
        client = GravityFormsClient(
            base_url=args.base_url,
            consumer_key=creds.consumer_key,
            consumer_secret=creds.consumer_secret,
            auth_method=args.auth_method,
        )
        out_path = export_shape_to_file(
            client,
            args.out,
            profile=args.profile,
            limit=args.limit,
            base_url=args.base_url,
            form_ids=args.form_id,
        )
    except GravityFormsError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(out_path)
    return 0


def _build_gravity_forms_client(args: argparse.Namespace):
    from .wordpress.gravity_forms import credentials_from_env, GravityFormsClient

    creds = credentials_from_env(args.profile)
    return GravityFormsClient(
        base_url=args.base_url,
        consumer_key=creds.consumer_key,
        consumer_secret=creds.consumer_secret,
        auth_method=args.auth_method,
    )


def cmd_wordpress_gravity_forms_baseline_direct_inquiry(args: argparse.Namespace) -> int:
    from .wordpress.gravity_forms import GravityFormsError
    from .direct_inquiry import gravity_forms as di_gf

    try:
        client = _build_gravity_forms_client(args)
        result = di_gf.baseline_direct_inquiry(
            client,
            form_ids=args.form_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except GravityFormsError as e:
        print(str(e), file=sys.stderr)
        return 1
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(result)
    return 1 if result.get("errors", 0) else 0


def cmd_wordpress_gravity_forms_process_direct_inquiry(args: argparse.Namespace) -> int:
    from .wordpress.gravity_forms import GravityFormsError
    from .direct_inquiry import gravity_forms as di_gf

    try:
        client = _build_gravity_forms_client(args)
        result = di_gf.process_direct_inquiry(
            client,
            form_ids=args.form_id,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    except GravityFormsError as e:
        print(str(e), file=sys.stderr)
        return 1
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(result)
    return 1 if result.get("read_mark_fail", 0) or result.get("errors", 0) else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return int(args.func(args))
