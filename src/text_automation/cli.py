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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 2
    return int(args.func(args))
