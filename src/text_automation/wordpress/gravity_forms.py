from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urljoin

import requests
from requests_oauthlib import OAuth1


DEFAULT_BASE_URL = "https://tutoringclub.com/"

ENTRY_METADATA_KEEP = {
    "id",
    "form_id",
    "post_id",
    "date_created",
    "date_updated",
    "is_starred",
    "is_read",
    "currency",
    "payment_status",
    "payment_date",
    "payment_amount",
    "payment_method",
    "transaction_id",
    "is_fulfilled",
    "created_by",
    "transaction_type",
    "status",
    "source_url",
}

ENTRY_METADATA_REDACT = {
    "ip": "[redacted:ip]",
    "user_agent": "[redacted:user_agent]",
}

DIRECT_INQUIRY_CANDIDATE_KEYS = (
    "parent_name",
    "student_name",
    "phone",
    "email",
    "grade",
    "preferred_location",
    "ideal_location_tag",
    "source_url",
    "created_date",
)

HTTP_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) text-automation/0.1 GravityFormsShapeStudy",
}


class GravityFormsError(RuntimeError):
    """Base error for read-only Gravity Forms shape export failures."""


class CredentialError(GravityFormsError):
    """Raised when the configured credential profile is missing secrets."""


class ForbiddenFormsError(GravityFormsError):
    """Raised when Gravity Forms refuses a read-only request."""


@dataclass(frozen=True)
class GravityFormsCredentials:
    profile: str
    consumer_key: str
    consumer_secret: str


def _env_prefix_for_profile(profile: str) -> str:
    prefix = re.sub(r"[^A-Za-z0-9]+", "_", profile.strip()).strip("_").upper()
    return re.sub(r"_+", "_", prefix)


def credentials_from_env(profile: str, environ: Mapping[str, str] | None = None) -> GravityFormsCredentials:
    env = environ if environ is not None else os.environ
    prefix = _env_prefix_for_profile(profile)
    profile_json = _get_env_value(env, profile, prefix)
    if profile_json is None and environ is None:
        profile_json = _windows_user_env_value(profile) or _windows_user_env_value(prefix)
    if profile_json:
        return _credentials_from_profile_json(profile, profile_json)

    key_name = f"{prefix}_CONSUMER_KEY"
    secret_name = f"{prefix}_CONSUMER_SECRET"
    consumer_key = (_get_env_value(env, key_name) or "").strip()
    consumer_secret = (_get_env_value(env, secret_name) or "").strip()
    if environ is None:
        consumer_key = consumer_key or (_windows_user_env_value(key_name) or "").strip()
        consumer_secret = consumer_secret or (_windows_user_env_value(secret_name) or "").strip()
    if not consumer_key or not consumer_secret:
        missing = [name for name, value in ((key_name, consumer_key), (secret_name, consumer_secret)) if not value]
        raise CredentialError(
            f"Missing Gravity Forms credentials for profile '{profile}'. "
            f"Set {profile} as JSON or set {', '.join(missing)}."
        )
    return GravityFormsCredentials(profile=profile, consumer_key=consumer_key, consumer_secret=consumer_secret)


def _credentials_from_profile_json(profile: str, raw: str) -> GravityFormsCredentials:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise CredentialError(
            f"Environment variable '{profile}' must be JSON with consumer key and consumer secret fields."
        ) from e
    if not isinstance(data, dict):
        raise CredentialError(f"Environment variable '{profile}' must contain a JSON object.")

    normalized = {_normalize_secret_key(str(key)): value for key, value in data.items()}
    consumer_key = str(
        normalized.get("consumerkey")
        or normalized.get("key")
        or normalized.get("apikey")
        or ""
    ).strip()
    consumer_secret = str(
        normalized.get("consumersecret")
        or normalized.get("secret")
        or normalized.get("apisecret")
        or ""
    ).strip()
    if not consumer_key or not consumer_secret:
        raise CredentialError(
            f"Environment variable '{profile}' JSON must include consumerkey/consumer_key "
            "and consumer_secret/consumersecret."
        )
    return GravityFormsCredentials(profile=profile, consumer_key=consumer_key, consumer_secret=consumer_secret)


def _normalize_secret_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.lower())


def _get_env_value(env: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = env.get(name)
        if value is not None:
            return value
    lower_names = {name.lower() for name in names}
    for key, value in env.items():
        if key.lower() in lower_names:
            return value
    return None


def _windows_user_env_value(name: str) -> str | None:
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            try:
                value, _ = winreg.QueryValueEx(key, name)
                return str(value)
            except FileNotFoundError:
                _, value_count, _ = winreg.QueryInfoKey(key)
                for index in range(value_count):
                    value_name, value, _ = winreg.EnumValue(key, index)
                    if value_name.lower() == name.lower():
                        return str(value)
    except OSError:
        return None
    return None


class GravityFormsClient:
    """Small read-only client for Gravity Forms REST API v2."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        consumer_key: str,
        consumer_secret: str,
        session: requests.Session | None = None,
        timeout: int = 30,
        auth_method: str = "basic",
    ) -> None:
        self.base_url = _normalize_base_url(base_url)
        self.session = session or requests.Session()
        self.timeout = timeout
        if auth_method not in {"basic", "oauth1"}:
            raise ValueError("auth_method must be 'basic' or 'oauth1'")
        self.auth_method = auth_method
        self.basic_auth = (consumer_key, consumer_secret)
        self.oauth1_auth = OAuth1(consumer_key, client_secret=consumer_secret, signature_method="HMAC-SHA1")

    def discovery(self) -> dict[str, Any]:
        return self._get("wp-json/", auth=False)

    def forms(self) -> list[dict[str, Any]]:
        data = self._get("wp-json/gf/v2/forms", label="/gf/v2/forms")
        return _normalize_forms_response(data)

    def form(self, form_id: int) -> dict[str, Any]:
        return self._get(f"wp-json/gf/v2/forms/{int(form_id)}", label=f"/gf/v2/forms/{int(form_id)}")

    def entries(
        self,
        form_id: int,
        page_size: int = 25,
        current_page: int = 1,
        unread_only: bool = False,
        search: str | Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        params = {
            "paging[page_size]": max(1, int(page_size)),
            "paging[current_page]": max(1, int(current_page)),
            "sorting[key]": "date_created",
            "sorting[direction]": "DESC",
        }
        search_payload: str | Mapping[str, Any] | None = search
        if unread_only:
            unread_filter = {"key": "is_read", "value": "0"}
            if isinstance(search_payload, Mapping):
                payload_copy = dict(search_payload)
                filters = list(payload_copy.get("field_filters") or [])
                filters.append(unread_filter)
                payload_copy["field_filters"] = filters
                search_payload = payload_copy
            elif search_payload:
                raise GravityFormsError("Cannot combine unread_only with a pre-encoded search string.")
            else:
                search_payload = {"field_filters": [unread_filter]}
        if search_payload:
            params["search"] = json.dumps(search_payload) if isinstance(search_payload, Mapping) else search_payload
        data = self._get(
            f"wp-json/gf/v2/forms/{int(form_id)}/entries",
            params=params,
            label=f"/gf/v2/forms/{int(form_id)}/entries",
        )
        if isinstance(data, dict):
            entries = data.get("entries", [])
        else:
            entries = data
        return [entry for entry in entries if isinstance(entry, dict)]

    def entry(self, entry_id: int | str) -> dict[str, Any]:
        data = self._get(
            f"wp-json/gf/v2/entries/{int(entry_id)}",
            label=f"/gf/v2/entries/{int(entry_id)}",
        )
        if not isinstance(data, dict):
            raise GravityFormsError(f"Entry response for {entry_id} was not a JSON object.")
        return data

    def update_entry(self, entry_id: int | str, entry: Mapping[str, Any]) -> dict[str, Any]:
        payload = dict(entry)
        data = self._put(
            f"wp-json/gf/v2/entries/{int(entry_id)}",
            payload=payload,
            label=f"/gf/v2/entries/{int(entry_id)}",
        )
        if isinstance(data, dict):
            return data
        return {}

    def mark_entry_read(self, entry_id: int | str) -> dict[str, Any]:
        full_entry = self.entry(entry_id)
        full_entry["is_read"] = "1"
        return self.update_entry(entry_id, full_entry)

    def _get(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        label: str | None = None,
        auth: bool = True,
    ) -> Any:
        url = urljoin(self.base_url, path)
        response = self.session.get(
            url,
            auth=self._auth() if auth else None,
            headers=HTTP_HEADERS,
            params=params,
            timeout=self.timeout,
        )
        if response.status_code in (401, 403):
            raise ForbiddenFormsError(_format_forbidden_message(label or path, response))
        if response.status_code >= 400:
            raise GravityFormsError(_format_http_error(label or path, response))
        try:
            return response.json()
        except ValueError as e:
            raise GravityFormsError(f"GET {label or path} did not return JSON.") from e

    def _put(
        self,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        label: str | None = None,
        auth: bool = True,
    ) -> Any:
        url = urljoin(self.base_url, path)
        response = self.session.put(
            url,
            auth=self._auth() if auth else None,
            headers=HTTP_HEADERS,
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code in (401, 403):
            raise ForbiddenFormsError(_format_forbidden_message(label or path, response, method="PUT"))
        if response.status_code >= 400:
            raise GravityFormsError(_format_http_error(label or path, response, method="PUT"))
        try:
            return response.json()
        except ValueError:
            return {}

    def _auth(self) -> Any:
        if self.auth_method == "basic":
            return self.basic_auth
        return self.oauth1_auth


def build_shape_export(
    client: GravityFormsClient,
    *,
    profile: str,
    limit: int = 25,
    base_url: str = DEFAULT_BASE_URL,
    form_ids: Sequence[int] | None = None,
) -> dict[str, Any]:
    discovery = client.discovery()
    namespaces = _extract_namespaces(discovery)
    if "gf/v2" not in namespaces:
        raise GravityFormsError("WordPress REST discovery did not advertise the gf/v2 namespace.")

    forms = _fetch_forms_for_shape(client, form_ids=form_ids)
    export_forms: list[dict[str, Any]] = []
    report_forms: list[dict[str, Any]] = []
    safe_limit = max(1, int(limit))

    for form_summary in forms:
        form_id = int(form_summary.get("id") or form_summary.get("form_id"))
        form = form_summary if form_summary.get("fields") else client.form(form_id)
        fields = _summarize_fields(form)
        raw_entries = client.entries(form_id, safe_limit)
        redacted_entries = [redact_entry(entry, form) for entry in raw_entries[:safe_limit]]
        export_forms.append(
            {
                "id": form_id,
                "title": form.get("title", ""),
                "fields": fields,
                "entry_count_exported": len(redacted_entries),
                "entries": redacted_entries,
            }
        )
        report_forms.append(
            {
                "form_id": form_id,
                "title": form.get("title", ""),
                "candidates": mapping_candidates_for_form(form, raw_entries),
            }
        )

    return {
        "profile": profile,
        "base_url": _normalize_base_url(base_url),
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "api": {"wordpress_namespace": "wp/v2", "gravity_forms_namespace": "gf/v2"},
        "discovery": {"namespaces": sorted(namespaces)},
        "forms": export_forms,
        "mapping_report": {"forms": report_forms},
    }


def export_shape_to_file(
    client: GravityFormsClient,
    out: str | Path,
    *,
    profile: str,
    limit: int = 25,
    base_url: str = DEFAULT_BASE_URL,
    form_ids: Sequence[int] | None = None,
) -> Path:
    export = build_shape_export(client, profile=profile, limit=limit, base_url=base_url, form_ids=form_ids)
    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(export, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out_path


def redact_entry(entry: Mapping[str, Any], form: Mapping[str, Any]) -> dict[str, Any]:
    field_lookup = _field_lookup(form)
    redacted: dict[str, Any] = {}
    for key, value in entry.items():
        key_str = str(key)
        key_l = key_str.lower()
        if key_str in ENTRY_METADATA_KEEP:
            redacted[key_str] = value
            continue
        if key_l in ENTRY_METADATA_REDACT:
            redacted[key_str] = ENTRY_METADATA_REDACT[key_l]
            continue
        if key_str == "_labels":
            redacted[key_str] = value
            continue

        field = field_lookup.get(key_str, {})
        classification = _classify_value_context(field.get("label", ""), field.get("type", ""), key_str)
        redacted[key_str] = _redact_value(value, classification)
    return redacted


def mapping_candidates_for_form(form: Mapping[str, Any], entries: Sequence[Mapping[str, Any]] | None = None) -> dict[str, list[dict[str, str]]]:
    candidates: dict[str, list[dict[str, str]]] = {key: [] for key in DIRECT_INQUIRY_CANDIDATE_KEYS}
    for field in _iter_field_contexts(form):
        label = str(field.get("label", ""))
        field_type = str(field.get("type", ""))
        haystack = _normalize_text(" ".join(str(field.get(k, "")) for k in ("label", "adminLabel", "type", "placeholder")))
        field_id = str(field.get("id", ""))
        if not field_id:
            continue
        candidate = {"field_id": field_id, "label": label, "type": field_type}
        if _is_parent_name_candidate(haystack, field_type):
            candidates["parent_name"].append(candidate)
        if _is_student_name_candidate(haystack):
            candidates["student_name"].append(candidate)
        if _is_phone_candidate(haystack, field_type):
            candidates["phone"].append(candidate)
        if _is_email_candidate(haystack, field_type):
            candidates["email"].append(candidate)
        if _is_grade_context(haystack, field_type):
            candidates["grade"].append(candidate)
        if _is_preferred_location_context(haystack, field_type):
            candidates["preferred_location"].append(candidate)
        if _is_ideal_location_tag_context(haystack, field_type):
            candidates["ideal_location_tag"].append(candidate)

    candidates["source_url"].append({"field_id": "source_url", "label": "Entry source URL", "type": "entry_property"})
    candidates["created_date"].append({"field_id": "date_created", "label": "Entry created date", "type": "entry_property"})
    return {key: value for key, value in candidates.items() if value}


def _fetch_forms_for_shape(client: GravityFormsClient, *, form_ids: Sequence[int] | None = None) -> list[dict[str, Any]]:
    if form_ids:
        return [client.form(int(form_id)) for form_id in form_ids]
    try:
        return client.forms()
    except ForbiddenFormsError as e:
        raise ForbiddenFormsError(
            "Fetching /gf/v2/forms was forbidden. The credential profile needs broader Gravity Forms read capability, "
            "or rerun with explicit --form-id values if this user can read known forms."
        ) from e


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/"


def _extract_namespaces(discovery: Mapping[str, Any]) -> set[str]:
    namespaces = discovery.get("namespaces", [])
    if isinstance(namespaces, list):
        return {str(ns) for ns in namespaces}
    if isinstance(namespaces, dict):
        return {str(ns) for ns in namespaces}
    routes = discovery.get("routes", {})
    if isinstance(routes, dict):
        found = set()
        for route in routes:
            match = re.match(r"^/([^/]+/v\d+)", str(route).lstrip("/"))
            if match:
                found.add(match.group(1))
        return found
    return set()


def _normalize_forms_response(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [form for form in data if isinstance(form, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("forms"), list):
            return [form for form in data["forms"] if isinstance(form, dict)]
        return [form for form in data.values() if isinstance(form, dict)]
    return []


def _summarize_fields(form: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = []
    for field in form.get("fields", []) or []:
        if not isinstance(field, dict):
            continue
        summary = {
            "id": str(field.get("id", "")),
            "label": field.get("label", ""),
            "adminLabel": field.get("adminLabel", ""),
            "type": field.get("type", ""),
            "inputType": field.get("inputType", ""),
            "visibility": field.get("visibility", ""),
            "choices": _summarize_choices(field.get("choices", [])),
            "inputs": _summarize_inputs(field.get("inputs", [])),
        }
        fields.append(summary)
    return fields


def _summarize_choices(choices: Any) -> list[dict[str, Any]]:
    if not isinstance(choices, list):
        return []
    summarized = []
    for choice in choices:
        if isinstance(choice, dict):
            summarized.append(
                {
                    "text": choice.get("text", ""),
                    "value": choice.get("value", ""),
                    "isSelected": choice.get("isSelected", False),
                }
            )
    return summarized


def _summarize_inputs(inputs: Any) -> list[dict[str, Any]]:
    if not isinstance(inputs, list):
        return []
    summarized = []
    for input_item in inputs:
        if isinstance(input_item, dict):
            summarized.append(
                {
                    "id": str(input_item.get("id", "")),
                    "label": input_item.get("label", ""),
                    "name": input_item.get("name", ""),
                }
            )
    return summarized


def _field_lookup(form: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for field in _iter_field_contexts(form):
        field_id = str(field.get("id", ""))
        if field_id:
            lookup[field_id] = field
    return lookup


def _iter_field_contexts(form: Mapping[str, Any]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    for field in form.get("fields", []) or []:
        if not isinstance(field, dict):
            continue
        field_id = str(field.get("id", ""))
        label = str(field.get("label", ""))
        base_context = {
            "id": field_id,
            "label": label,
            "adminLabel": field.get("adminLabel", ""),
            "type": field.get("type", ""),
            "placeholder": field.get("placeholder", ""),
        }
        contexts.append(base_context)
        for input_item in field.get("inputs", []) or []:
            if not isinstance(input_item, dict):
                continue
            input_id = str(input_item.get("id", ""))
            if input_id:
                contexts.append(
                    {
                        "id": input_id,
                        "label": " ".join(part for part in (label, str(input_item.get("label", ""))) if part),
                        "adminLabel": field.get("adminLabel", ""),
                        "type": field.get("type", ""),
                        "placeholder": field.get("placeholder", ""),
                    }
                )
    return contexts


def _classify_value_context(label: str, field_type: str, key: str) -> str:
    haystack = _normalize_text(f"{label} {field_type} {key}")
    if _is_email_candidate(haystack, field_type):
        return "email"
    if _is_phone_candidate(haystack, field_type):
        return "phone"
    if _is_grade_context(haystack, field_type):
        return "preserve"
    if _is_preferred_location_context(haystack, field_type):
        return "preserve"
    if _is_ideal_location_tag_context(haystack, field_type):
        return "preserve"
    if _is_name_context(haystack, field_type):
        return "name"
    return "text"


def _redact_value(value: Any, classification: str) -> Any:
    if value in (None, ""):
        return value
    if classification == "preserve":
        return value
    if classification in {"email", "phone", "name"}:
        return f"[redacted:{classification}]"
    if isinstance(value, (int, float, bool)):
        return "[redacted:text]"
    if isinstance(value, list):
        return ["[redacted:text]" if item not in (None, "") else item for item in value]
    if isinstance(value, dict):
        return {str(key): "[redacted:text]" if val not in (None, "") else val for key, val in value.items()}
    text = str(value)
    if _looks_like_email(text):
        return "[redacted:email]"
    if _looks_like_phone(text):
        return "[redacted:phone]"
    return "[redacted:text]"


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _is_parent_name_candidate(haystack: str, field_type: str) -> bool:
    return ("student" not in haystack and any(token in haystack for token in ("parent", "guardian", "contact", "your name"))) or (
        field_type == "name" and "student" not in haystack
    )


def _is_student_name_candidate(haystack: str) -> bool:
    return "student" in haystack and "name" in haystack


def _is_phone_candidate(haystack: str, field_type: str) -> bool:
    return field_type == "phone" or "phone" in haystack or "mobile" in haystack or "cell" in haystack


def _is_email_candidate(haystack: str, field_type: str) -> bool:
    return field_type == "email" or "email" in haystack


def _is_grade_context(haystack: str, _field_type: str) -> bool:
    return "grade" in haystack


def _is_preferred_location_context(haystack: str, _field_type: str) -> bool:
    return "location" in haystack or "center" in haystack or "centre" in haystack or "club" in haystack


def _is_ideal_location_tag_context(haystack: str, field_type: str) -> bool:
    return ("ideal" in haystack and ("location" in haystack or "tag" in haystack)) or (
        "tag" in haystack and field_type in {"hidden", "text", "select"}
    )


def _is_name_context(haystack: str, field_type: str) -> bool:
    return field_type == "name" or "name" in haystack or "parent" in haystack or "student" in haystack or "guardian" in haystack


def _looks_like_email(value: str) -> bool:
    return bool(re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value))


def _looks_like_phone(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    return len(digits) >= 10


def _format_forbidden_message(label: str, response: requests.Response, method: str = "GET") -> str:
    return f"{method} {label} was forbidden ({response.status_code}): {_response_message(response)}"


def _format_http_error(label: str, response: requests.Response, method: str = "GET") -> str:
    return f"{method} {label} failed ({response.status_code}): {_response_message(response)}"


def _response_message(response: requests.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text[:300]
    if isinstance(data, dict):
        return str(data.get("message") or data.get("code") or data)
    return str(data)
