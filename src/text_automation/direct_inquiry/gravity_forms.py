from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlparse

from ..config import Franchise, load_config
from ..direct_inquiry.business_hours import in_business_window, localize_timestamp
from ..direct_inquiry.processor import is_phone_blacklisted, process_direct_inquiry_payload
from ..general.telegram import LOG_BOT, LOG_CHAT, send_message
from ..wordpress.gravity_forms import GravityFormsClient


TARGET_DIRECT_INQUIRY_FORM_IDS = (1, 2, 3, 5, 6, 7, 9, 10, 13, 14, 18, 19)
TARGET_DIRECT_INQUIRY_FORM_ID_SET = frozenset(TARGET_DIRECT_INQUIRY_FORM_IDS)


@dataclass(frozen=True)
class NormalizedDirectInquiry:
    form_id: int
    entry_id: str
    parent_name: str
    student_name: str
    phone: str
    email: str
    grade: str
    location_value: str
    created_dt: datetime | None


def baseline_direct_inquiry(
    client: GravityFormsClient,
    *,
    form_ids: Sequence[int] | None = None,
    page_size: int = 100,
    limit: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    stats = {"entries": 0, "marked_read": 0, "errors": 0, "dry_run": 1 if dry_run else 0}
    entries = list(_iter_unread_entries(
        client,
        form_ids=form_ids,
        page_size=page_size,
        limit=limit,
    ))
    for entry in entries:
        stats["entries"] += 1
        if dry_run:
            continue
        try:
            client.mark_entry_read(entry["id"])
            stats["marked_read"] += 1
        except Exception:
            stats["errors"] += 1
    return stats


def process_direct_inquiry(
    client: GravityFormsClient,
    *,
    form_ids: Sequence[int] | None = None,
    page_size: int = 100,
    limit: int | None = None,
    dry_run: bool = False,
    process_fn=process_direct_inquiry_payload,
) -> dict[str, int]:
    stats = {
        "entries": 0,
        "processed": 0,
        "marked_read": 0,
        "unmatched": 0,
        "ambiguous": 0,
        "invalid": 0,
        "terminal_skipped": 0,
        "in_hours_skipped": 0,
        "errors": 0,
        "read_mark_fail": 0,
        "dry_run": 1 if dry_run else 0,
    }

    cfg = load_config()
    franchises = cfg.franchises
    di_cfg = getattr(cfg, "direct_inquiry", None)
    vegas_ids = tuple(getattr(di_cfg, "vegas_ids", ()) or (6, 11, 15, 16, 60, 110))

    entries = list(_iter_unread_entries(
        client,
        form_ids=form_ids,
        page_size=page_size,
        limit=limit,
    ))
    for entry in entries:
        stats["entries"] += 1

        normalized = _normalize_entry(entry, client)
        if not normalized:
            stats["invalid"] += 1
            continue

        if is_phone_blacklisted(normalized.phone):
            stats["terminal_skipped"] += 1
            if dry_run:
                continue
            try:
                client.mark_entry_read(normalized.entry_id)
                stats["marked_read"] += 1
            except Exception:
                stats["read_mark_fail"] += 1
                stats["errors"] += 1
                _log_warning(
                    f"[direct-inquiry][gf] Skipped entry {normalized.entry_id} but could not mark read; will retry.",
                    dry_run=dry_run,
                )
            continue

        fid, state = _resolve_franchise_id(normalized.location_value, franchises)
        if not fid:
            stats[state] += 1
            if state == "unmatched":
                _log_warning(
                    f"[direct-inquiry][gf] Location resolution unmatched for entry {normalized.entry_id}; "
                    "marking read without processing.",
                    dry_run=dry_run,
                )
                if dry_run:
                    continue
                try:
                    client.mark_entry_read(normalized.entry_id)
                    stats["marked_read"] += 1
                except Exception:
                    stats["read_mark_fail"] += 1
                    stats["errors"] += 1
                    _log_warning(
                        f"[direct-inquiry][gf] Unmatched entry {normalized.entry_id} could not be marked read; will retry.",
                        dry_run=dry_run,
                    )
                continue
            _log_warning(
                f"[direct-inquiry][gf] Location resolution {state} for entry {normalized.entry_id}; retry needed.",
                dry_run=dry_run,
            )
            continue

        local_dt = localize_timestamp(_coerce_local_dt(normalized.created_dt), fid) if normalized.created_dt else None
        if not local_dt:
            local_dt = datetime.now(timezone.utc)

        if int(fid) in vegas_ids and in_business_window(local_dt):
            stats["in_hours_skipped"] += 1
            stats["terminal_skipped"] += 1
            if dry_run:
                continue
            try:
                client.mark_entry_read(normalized.entry_id)
                stats["marked_read"] += 1
            except Exception:
                stats["read_mark_fail"] += 1
                stats["errors"] += 1
                _log_warning(
                    f"[direct-inquiry][gf] In-hours Vegas entry {normalized.entry_id} could not be marked read; will retry.",
                    dry_run=dry_run,
                )
            continue

        try:
            processed = process_fn(
                parent_name=normalized.parent_name,
                student_name=normalized.student_name,
                phone=normalized.phone,
                email_addr=normalized.email,
                grade=normalized.grade,
                franchise_id=fid,
                local_dt=local_dt,
                dry_run=dry_run,
            )
        except Exception:
            stats["errors"] += 1
            _log_warning(
                f"[direct-inquiry][gf] Processing failed for entry {normalized.entry_id}; retry needed.",
                dry_run=dry_run,
            )
            continue

        if not processed:
            stats["invalid"] += 1
            continue

        if dry_run:
            stats["processed"] += 1
            continue

        try:
            client.mark_entry_read(normalized.entry_id)
            stats["marked_read"] += 1
            stats["processed"] += 1
        except Exception:
            stats["read_mark_fail"] += 1
            stats["errors"] += 1
            _log_warning(
                f"[direct-inquiry][gf] Processed entry {normalized.entry_id} but could not mark read; will retry.",
                dry_run=dry_run,
            )

    return stats


def _iter_unread_entries(
    client: GravityFormsClient,
    *,
    form_ids: Sequence[int] | None,
    page_size: int,
    limit: int | None = None,
) -> Iterable[dict[str, Any]]:
    normalized_ids = _target_form_ids(form_ids)
    yielded = 0
    for form_id in normalized_ids:
        current_page = 1
        while True:
            entries = client.entries(
                form_id,
                page_size=page_size,
                current_page=current_page,
                unread_only=True,
            )
            batch: list[dict[str, Any]] = _extract_entries_from_response(entries)
            if not batch:
                break

            for entry in batch:
                if limit is not None and yielded >= max(0, int(limit)):
                    return
                if isinstance(entry, dict):
                    yielded += 1
                    yield {**entry, "_form_id": str(form_id)}

            if isinstance(entries, dict):
                paging = entries.get("paging", {}) or entries.get("pagination", {})
                total_pages = int(paging.get("total_pages", 0) or 0)
                if total_pages and current_page >= total_pages:
                    break
            if len(batch) < page_size:
                break
            current_page += 1


def _target_form_ids(form_ids: Sequence[int] | None) -> tuple[int, ...]:
    if not form_ids:
        return TARGET_DIRECT_INQUIRY_FORM_IDS
    normalized = tuple(sorted({int(form_id) for form_id in form_ids}))
    unexpected = [form_id for form_id in normalized if form_id not in TARGET_DIRECT_INQUIRY_FORM_ID_SET]
    if unexpected:
        raise ValueError(
            "Gravity Forms direct-inquiry processing is limited to target forms: "
            f"{', '.join(str(form_id) for form_id in TARGET_DIRECT_INQUIRY_FORM_IDS)}. "
            f"Unsupported form_id: {', '.join(str(form_id) for form_id in unexpected)}."
        )
    return normalized


def _extract_entries_from_response(response: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(response, list):
        return [entry for entry in response if isinstance(entry, dict)]
    if not isinstance(response, dict):
        return []
    items = response.get("entries", [])
    if isinstance(items, list):
        return [entry for entry in items if isinstance(entry, dict)]
    return []


def _normalize_entry(entry: Mapping[str, Any], client: GravityFormsClient) -> NormalizedDirectInquiry | None:
    if not isinstance(entry, Mapping):
        return None
    form_id = int(entry.get("form_id") or entry.get("_form_id") or 0)
    fields = _fetch_form_fields(client, form_id)
    if not fields:
        return None

    field_ids = _field_ids_by_role(fields)
    parent_name = _extract_value(entry, field_ids.get("parent_name"))
    student_name = _extract_value(entry, field_ids.get("student_name"))
    phone = _extract_value(entry, field_ids.get("phone"))
    email = _extract_value(entry, field_ids.get("email"))
    grade = _extract_value(entry, field_ids.get("grade"))
    location = _extract_value(entry, field_ids.get("preferred_location")) or _extract_value(entry, field_ids.get("ideal_location_tag"))

    if not all((parent_name, student_name, phone, email)):
        return None

    created_dt = _parse_datetime(entry.get("date_created")) or _parse_datetime(entry.get("created_date"))
    entry_id = str(entry.get("id") or "")
    if not entry_id:
        return None

    return NormalizedDirectInquiry(
        form_id=form_id,
        entry_id=entry_id,
        parent_name=parent_name,
        student_name=student_name,
        phone=phone,
        email=email,
        grade=grade,
        location_value=location,
        created_dt=created_dt,
    )


def _fetch_form_fields(client: GravityFormsClient, form_id: int) -> list[dict[str, Any]]:
    if form_id <= 0:
        return []
    try:
        form = client.form(form_id)
    except Exception:
        return []
    return form.get("fields", []) if isinstance(form.get("fields"), list) else []


def _field_ids_by_role(fields: Sequence[dict[str, Any]]) -> dict[str, str]:
    role_to_field: dict[str, str] = {}
    role_scores: dict[str, int] = {}
    for ctx in _iter_field_contexts(fields):
        label = _normalize_text(str(ctx.get("label", "")))
        field_type = str(ctx.get("type", "")).lower()
        field_id = str(ctx.get("id", ""))
        if not field_id:
            continue

        if _is_parent_field(label, field_type):
            _set_role(role_to_field, role_scores, "parent_name", field_id, _parent_field_score(label, field_type))
        if _is_student_field(label, field_type):
            _set_role(role_to_field, role_scores, "student_name", field_id, 10)
        if _is_phone_field(label, field_type):
            _set_role(role_to_field, role_scores, "phone", field_id, 10)
        if _is_email_field(label, field_type):
            _set_role(role_to_field, role_scores, "email", field_id, 10)
        if _is_grade_field(label, field_type):
            _set_role(role_to_field, role_scores, "grade", field_id, 10)
        if _is_location_field(label, field_type):
            _set_role(role_to_field, role_scores, "preferred_location", field_id, _location_field_score(label))
        if _is_location_field(label, field_type) and "ideal" in label:
            _set_role(role_to_field, role_scores, "ideal_location_tag", field_id, 10)
    return role_to_field


def _set_role(
    role_to_field: dict[str, str],
    role_scores: dict[str, int],
    role: str,
    field_id: str,
    score: int,
) -> None:
    if score > role_scores.get(role, -1):
        role_scores[role] = score
        role_to_field[role] = field_id


def _parent_field_score(label: str, field_type: str) -> int:
    if "parent" in label or "guardian" in label:
        return 30
    if "your name" in label:
        return 20
    if field_type == "name":
        return 10
    if "contact" in label:
        return 1
    return 0


def _location_field_score(label: str) -> int:
    if "preferred" in label:
        return 30
    if "club" in label or "center" in label or "centre" in label:
        return 20
    if "location" in label:
        return 10
    return 0


def _iter_field_contexts(fields: Sequence[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    for field in fields:
        if not isinstance(field, dict):
            continue
        field_id = str(field.get("id", ""))
        label = str(field.get("label", ""))
        field_ctx = {
            "id": field_id,
            "label": label,
            "type": field.get("type", ""),
            "adminLabel": field.get("adminLabel", ""),
            "placeholder": field.get("placeholder", ""),
        }
        yield field_ctx
        for input_item in field.get("inputs", []) or []:
            if not isinstance(input_item, dict):
                continue
            input_id = str(input_item.get("id", ""))
            if not input_id:
                continue
            yield {
                "id": input_id,
                "label": " ".join(part for part in (label, str(input_item.get("label", ""))) if part),
                "type": field.get("type", ""),
                "adminLabel": field.get("adminLabel", ""),
                "placeholder": field.get("placeholder", ""),
            }


def _extract_value(entry: Mapping[str, Any], field_id: str | None) -> str:
    if not field_id:
        return ""
    value = entry.get(field_id)
    if value is None and "." not in field_id:
        prefix = f"{field_id}."
        value = [
            entry[key]
            for key in sorted(entry, key=str)
            if str(key).startswith(prefix) and entry.get(key) not in (None, "")
        ]
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        parts = [str(v) for v in value.values() if isinstance(v, (str, int, float))]
        return " ".join(part.strip() for part in parts if part.strip())
    if isinstance(value, list):
        return " ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip()


def _parse_datetime(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = raw.strip().replace(" ", "T")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(candidate, fmt)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(raw.strip())
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except Exception:
        return None


def _coerce_local_dt(raw_dt: datetime | None) -> datetime:
    if raw_dt is None:
        return datetime.now(timezone.utc)
    return raw_dt.astimezone(timezone.utc)


def _resolve_franchise_id(location_value: str, franchises: Sequence[Franchise]) -> tuple[int | None, str]:
    if not location_value:
        return None, "unmatched"
    normalized = _normalize_token(location_value)
    matches: list[int] = []
    for f in franchises:
        if _match_token(normalized, _franchise_tokens(f)):
            matches.append(f.id)

    if len(matches) == 1:
        return matches[0], "matched"
    if len(matches) > 1:
        return None, "ambiguous"
    return None, "unmatched"


def _franchise_tokens(f: Franchise) -> list[str]:
    tokens = []
    for loc in f.preferred_locations:
        tokens.append(_normalize_token(loc))
    if f.name:
        tokens.append(_normalize_token(f.name))
    if f.email:
        tokens.append(_normalize_token(f.email))
    if f.url:
        slug = _extract_url_slug(f.url)
        if slug:
            tokens.append(_normalize_token(slug))
    return [token for token in tokens if token]


def _match_token(value: str, candidates: Sequence[str]) -> bool:
    if not value or not candidates:
        return False
    for candidate in candidates:
        if not candidate:
            continue
        if value == candidate or value in candidate or candidate in value:
            return True
    return False


def _extract_url_slug(url: str) -> str:
    parsed = urlparse(url or "")
    for fragment in filter(None, parsed.path.split("/")):
        return fragment
    return ""


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _is_parent_field(haystack: str, field_type: str) -> bool:
    return ("student" not in haystack and ("parent" in haystack or "guardian" in haystack or "contact" in haystack or "your name" in haystack)) or (
        field_type == "name" and "student" not in haystack
    )


def _is_student_field(haystack: str, _field_type: str) -> bool:
    return "student" in haystack


def _is_phone_field(haystack: str, _field_type: str) -> bool:
    return "phone" in haystack or "mobile" in haystack or "cell" in haystack


def _is_email_field(haystack: str, _field_type: str) -> bool:
    return "email" in haystack


def _is_grade_field(haystack: str, _field_type: str) -> bool:
    return "grade" in haystack


def _is_location_field(haystack: str, _field_type: str) -> bool:
    return "location" in haystack or "center" in haystack or "centre" in haystack or "club" in haystack


def _log_warning(message: str, *, dry_run: bool) -> None:
    if dry_run:
        print(message)
        return
    send_message(message, LOG_BOT, LOG_CHAT)
