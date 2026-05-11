from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from .client import send_payload, send_text
except ImportError:  # pragma: no cover - supports direct file execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from text_automation.accounts.quo.client import send_payload, send_text


def _load_payload(path: str | None, inline: str | None) -> dict[str, Any]:
    if inline:
        return json.loads(inline)
    if path:
        with Path(path).open("r", encoding="utf-8") as f:
            return json.load(f)
    try:
        if not sys.stdin.isatty():
            data = sys.stdin.read().strip()
            if data:
                return json.loads(data)
    except Exception:
        pass
    return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a text through Quo.")
    parser.add_argument("--payload-file", help="Path to Zapier-style payload JSON.")
    parser.add_argument("--payload-json", help="Inline Zapier-style payload JSON.")
    parser.add_argument("--message", help="Message body for direct sends.")
    parser.add_argument("--phone", help="Recipient phone for direct sends.")
    args = parser.parse_args(argv)

    if args.message or args.phone:
        if not args.message or not args.phone:
            parser.error("--message and --phone must be supplied together")
        ok = send_text(args.message, args.phone)
    else:
        payload = _load_payload(args.payload_file, args.payload_json)
        if not payload:
            parser.error("provide --payload-file, --payload-json, stdin JSON, or --message/--phone")
        ok = send_payload(payload)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
