from __future__ import annotations

import argparse
import json
import sys

from .client import (
    DEFAULT_SMOKE_BODY,
    DEFAULT_SMOKE_FRANCHISE_IDS,
    DEFAULT_SMOKE_RECIPIENT,
    DEFAULT_SMOKE_SUBJECT,
    send_jacksonville_hodges_smoke,
)


def _parse_franchise_ids(value: str | None) -> list[int] | None:
    if not value:
        return None
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gmail account sender helpers.")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Send the Jacksonville/Hodges Gmail DWD smoke email.",
    )
    parser.add_argument("--to", default=DEFAULT_SMOKE_RECIPIENT)
    parser.add_argument("--subject", default=DEFAULT_SMOKE_SUBJECT)
    parser.add_argument("--body", default=DEFAULT_SMOKE_BODY)
    parser.add_argument(
        "--franchise-id",
        default=",".join(str(fid) for fid in DEFAULT_SMOKE_FRANCHISE_IDS),
        help="Single ID or comma-separated list. Defaults to 62,95.",
    )
    args = parser.parse_args(argv)

    if not args.smoke:
        parser.print_help()
        return 2

    try:
        result = send_jacksonville_hodges_smoke(
            to=args.to,
            subject=args.subject,
            body=args.body,
            franchise_ids=_parse_franchise_ids(args.franchise_id),
        )
    except Exception as e:
        print(str(e), file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
