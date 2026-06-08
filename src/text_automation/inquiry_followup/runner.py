from __future__ import annotations

import os
import time
from datetime import date, timedelta
from typing import Optional

import pandas as pd

from .sql import fetch_inquiries
from .messages import build_message
from .cache import (
    mark_text_sent_by_row_ids,
    pending_to_text,
    revert_row_to_pending,
    upsert_from_server,
    claim_row_for_send,
)
from ..config import load_config

import requests


def _filter_rows_for_followup(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    if "Status" not in df.columns:
        return df, {}

    statuses = df["Status"].astype(str).str.strip()
    normalized = statuses.str.lower()
    keep = normalized.isin({"inquiry", "lead"})
    skipped = statuses.loc[~keep].str.strip().str.lower()
    skipped_statuses = skipped.value_counts().to_dict()
    return df.loc[keep], skipped_statuses


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

    if env_name:
        url = os.getenv(env_name)
        if url:
            return url

    if grp == "vegas":
        return os.getenv("ZapHookMeetingGilVeg")
    if grp == "cali":
        return os.getenv("ZapHookMeetingCali")
    return os.getenv("ZapHookMeetingGilVeg") or os.getenv("ZapHookMeetingCali")


def _post_to_webhook(webhook_url: str | None, phone: str, message: str, franchise_id: int | None = None) -> bool:
    if not webhook_url:
        print({"inquiry_followup": {"send": "missing_webhook", "franchise_id": franchise_id}})
        return False

    payload = {
        "message": message,
        "AssessmentPhone": phone,
        "ContactPhone": phone,
    }
    if franchise_id is not None:
        payload["FranchiseID"] = int(franchise_id)
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as ex:
        print({"inquiry_followup": {"send": "error", "error": str(ex)}})
        return False


def _build_bounds(since: str | None, lookback_days: int, min_age_days: int) -> tuple[str, str]:
    today = date.today()
    if since:
        lower = str(since)
    else:
        lower = (today - timedelta(days=int(lookback_days))).isoformat()
    upper = (today - timedelta(days=int(min_age_days))).isoformat()
    return lower, upper


def run(
    franchise_ids: list[int] | None = None,
    *,
    franchise_id: int | None = None,
    since: str | None = None,
    lookback_days: int = 90,
    min_age_days: int = 7,
    webhook_env: str | None = None,
    summer: bool = False,
    dry_run: bool = False,
    batch_size: int = 50,
    max_batches: int = 1,
    sleep_seconds: float = 3,
) -> int:
    ids = sorted(
        {
            int(x)
            for x in ((franchise_ids or []) + ([franchise_id] if franchise_id is not None else []))
        }
    )
    if not ids:
        ids = [87, 49]
    ids = [x for x in ids if x not in {62, 95}]
    if not ids:
        return 0

    batch_size = max(int(batch_size), 1)
    if batch_size > 50:
        batch_size = 50
    max_batches = max(int(max_batches), 1)
    if max_batches > 4:
        max_batches = 4

    if not dry_run and sleep_seconds < 3:
        sleep_seconds = 3

    lower_bound, upper_bound = _build_bounds(since=since, lookback_days=lookback_days, min_age_days=min_age_days)

    try:
        df_sql = fetch_inquiries(
            franchise_ids=ids,
            since=since,
            lookback_days=lookback_days,
            min_age_days=min_age_days,
        )
    except Exception as ex:
        print({"inquiry_followup": {"status": "error_fetching", "error": str(ex)}})
        return 0

    df_sql, skipped_statuses = _filter_rows_for_followup(df_sql)
    if skipped_statuses:
        print(
            {
                "inquiry_followup": {
                    "status_filter": "skipped",
                    "skipped": int(sum(skipped_statuses.values())),
                    "statuses": skipped_statuses,
                }
            }
        )

    if df_sql is None or df_sql.empty:
        print({
            "inquiry_followup": {
                "status": "no_rows",
                "franchise_ids": ids,
                "lookback_days": lookback_days,
                "min_age_days": min_age_days,
                "dry_run": dry_run,
            }
        })
        return 0

    df_sql = df_sql.copy()
    df_sql["MessageVariant"] = "summer" if summer else "standard"
    upsert_from_server(df_sql, message_variant="summer" if summer else "standard")

    df_cache = pending_to_text(
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        franchise_ids=ids,
    )

    if df_cache is None or df_cache.empty:
        print({"inquiry_followup": {"status": "no_pending", "franchise_ids": ids}})
        return 0

    sent = 0
    for batch_no in range(max_batches):
        batch = df_cache.iloc[batch_no * batch_size : (batch_no + 1) * batch_size]
        if batch.empty:
            break

        for _, row in batch.iterrows():
            row_id = int(row.get("ID") or 0)
            inquiry_id = int(row.get("InquiryID") or 0)
            franchise_id = int(row.get("FranchiseID") or 0)
            phone = str(row.get("ContactPhone") or "").strip()
            if not phone:
                continue

            contact_first = str(row.get("ContactFirstName") or "").strip()
            student_first = str(row.get("StudentFirstName") or "").strip()
            message = build_message(
                contact_first=contact_first,
                student_first=student_first,
                franchise_id=franchise_id,
                summer=summer,
            )

            if dry_run:
                print(
                    f"[inquiry_followup][dry-run] FID={franchise_id} InquiryID={inquiry_id} MessageVariant={row.get('MessageVariant') or 'standard'}"
                )
                continue

            if row_id and not claim_row_for_send(row_id):
                continue

            webhook = _resolve_webhook(franchise_id, webhook_env)
            ok = _post_to_webhook(webhook, phone=phone, message=message, franchise_id=franchise_id)
            if ok:
                mark_text_sent_by_row_ids([row_id])
                sent += 1
            else:
                revert_row_to_pending(row_id)
            time.sleep(sleep_seconds)

    return sent
