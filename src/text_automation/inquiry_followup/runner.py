from __future__ import annotations

import os
from typing import Optional

import requests

from .sql import fetch_inquiries
from .messages import build_message
from ..config import load_config
# from ..accounts.quo import send_payload as send_to_quo


# QUO_FRANCHISE_IDS = {95}


def _assess_group(fid: int) -> str:
    cfg = load_config()
    for f in cfg.franchises:
        if f.id == fid:
            return (f.assess_group or "").lower()
    return ""


def _resolve_webhook(franchise_id: int, env_name: Optional[str]) -> Optional[str]:
    grp = _assess_group(franchise_id)
    if grp == "east_q":
        return None

    # Allow explicit override via env var name if provided and set
    if env_name:
        url = os.getenv(env_name)
        if url:
            return url
    # Default to meetings webhooks by assess_group
    if grp == "vegas":
        return os.getenv("ZapHookMeetingGilVeg")
    if grp == "cali":
        return os.getenv("ZapHookMeetingCali")
    return os.getenv("ZapHookMeetingGilVeg") or os.getenv("ZapHookMeetingCali")


def _post_to_webhook(webhook_url: str, phone: str, message: str, franchise_id: int | None = None) -> bool:
    payload = {
        "message": message,
        # Mirror existing payload shape used elsewhere for compatibility
        "AssessmentPhone": phone,
        "ContactPhone": phone,
    }
    if franchise_id is not None:
        payload["FranchiseID"] = int(franchise_id)
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print({"inquiry_followup": {"send": "error", "error": str(e)}})
        return False


def _post_to_quo(phone: str, message: str, franchise_id: int | None = None) -> bool:
    payload = {
        "message": message,
        "AssessmentPhone": phone,
        "ContactPhone": phone,
    }
    if franchise_id is not None:
        payload["FranchiseID"] = int(franchise_id)
    # return send_to_quo(payload)
    return False


def run(
    franchise_id: int = 87,
    limit: int | None = None,
    webhook_env: str | None = None,
    dry_run: bool = True,
) -> int:
    if int(franchise_id) in (62, 95):
        print({"inquiry_followup": {"send": "skipped", "reason": "franchise_gate", "franchise_id": int(franchise_id)}})
        return 0

    # Fetch data (default 3 months back)
    try:
        df = fetch_inquiries(franchise_id=franchise_id, limit=limit)
    except Exception as ex:
        print({
            "inquiry_followup": {
                "status": "error_fetching",
                "error": str(ex),
                "fallback": "dry_run_noop",
            }
        })
        return 0
    if df is None or df.empty:
        print({
            "inquiry_followup": {
                "status": "no_rows",
                "franchise_id": franchise_id,
                "months_back": 3,
                "limit": limit,
                "dry_run": dry_run,
            }
        })
        return 0

    # Resolve webhook URL; if absent, we will operate in dry-run mode
    # use_quo = int(franchise_id) in QUO_FRANCHISE_IDS
    # hook_url = None if use_quo else _resolve_webhook(franchise_id, webhook_env)
    # live_mode = (not dry_run) and (use_quo or bool(hook_url))
    hook_url = _resolve_webhook(franchise_id, webhook_env)
    live_mode = (not dry_run) and bool(hook_url)
    if not hook_url and not dry_run:
        print({"inquiry_followup": {"warning": "webhook_missing", "env": (webhook_env or 'ZapHookInquiryFollowup')}})

    sent = 0
    for _, row in df.iterrows():
        phone = str(row.get("ContactPhone") or "").strip()
        if not phone:
            continue
        contact_first = str(row.get("CFirstName") or "").strip()
        student_first = str(row.get("StudentFirstName") or "").strip()
        msg = build_message(contact_first, student_first)

        header = f"[inquiry_followup] FID={int(franchise_id)} InquiryID={int(row.get('InquiryID') or 0)}"
        if live_mode:
            # if use_quo:
            #     ok = _post_to_quo(phone=phone, message=msg, franchise_id=franchise_id)
            # else:
            #     ok = _post_to_webhook(hook_url, phone=phone, message=msg, franchise_id=franchise_id)
            ok = _post_to_webhook(hook_url, phone=phone, message=msg, franchise_id=franchise_id)
            if ok:
                sent += 1
        else:
            # Dry-run: print only (no network calls)
            print(f"[inquiry_followup][dry-run] to={phone} body={msg}")

    print({"inquiry_followup": {"completed": True, "sent": sent, "dry_run": (not live_mode)}})
    return sent
