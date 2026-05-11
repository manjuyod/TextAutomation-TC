from __future__ import annotations

import os
import re
import json
from typing import Any, Mapping

import requests


API_URL = "https://api.openphone.com/v1/messages"
API_KEY_ENV = "JAX_Quo"
FROM_ENV = "JAX_Quo_From"
USER_ID_ENV = "JAX_Quo_UserId"


def _first_present(data: Mapping[str, Any], names: tuple[str, ...]) -> str:
    for name in names:
        value = data.get(name)
        if value is not None:
            return str(value).strip()
    return ""


def normalize_phone_e164(phone: str | None) -> str | None:
    raw = str(phone or "").strip()
    if not raw:
        return None

    if raw.startswith("+"):
        candidate = "+" + re.sub(r"\D", "", raw[1:])
    else:
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 10:
            candidate = f"+1{digits}"
        elif len(digits) == 11 and digits.startswith("1"):
            candidate = f"+{digits}"
        else:
            return None

    if re.fullmatch(r"\+[1-9]\d{1,14}", candidate):
        return candidate
    return None


def _env_value(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def _settings() -> dict[str, str]:
    raw = _env_value(API_KEY_ENV)
    settings = {
        "api_key": raw,
        "from": "",
        "user_id": "",
    }

    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            print({"quo": {"send": "error", "reason": "invalid_json_env", "env": API_KEY_ENV, "error": str(e)}})
            return {"api_key": "", "from": "", "user_id": ""}
        if not isinstance(data, dict):
            print({"quo": {"send": "error", "reason": "invalid_json_env", "env": API_KEY_ENV}})
            return {"api_key": "", "from": "", "user_id": ""}
        settings["api_key"] = _first_present(data, ("api_key", "apiKey", "key", "token"))
        settings["from"] = _first_present(data, ("from", "from_id", "fromId", "phone_number_id", "phoneNumberId"))
        settings["user_id"] = _first_present(data, ("user_id", "userId"))

    from_override = _env_value(FROM_ENV)
    user_id_override = _env_value(USER_ID_ENV)
    if from_override:
        settings["from"] = from_override
    if user_id_override:
        settings["user_id"] = user_id_override
    return settings


def _build_body(message: str, phone: str) -> dict[str, Any] | None:
    settings = _settings()
    content = str(message or "").strip()
    to_number = normalize_phone_e164(phone)
    from_number_id = settings["from"]
    user_id = settings["user_id"]

    if not content:
        print({"quo": {"send": "error", "reason": "missing_message"}})
        return None
    if not to_number:
        print({"quo": {"send": "error", "reason": "invalid_phone", "phone": phone}})
        return None
    if not from_number_id or not from_number_id.startswith("PN"):
        print({"quo": {"send": "error", "reason": "missing_or_invalid_from", "env": FROM_ENV}})
        return None
    if user_id and not user_id.startswith("US"):
        print({"quo": {"send": "error", "reason": "invalid_user_id", "env": USER_ID_ENV}})
        return None

    body: dict[str, Any] = {
        "content": content,
        "from": from_number_id,
        "to": [to_number],
    }
    if user_id:
        body["userId"] = user_id
    return body


def send_text(message: str, phone: str, *, timeout: float = 10) -> bool:
    api_key = _settings()["api_key"]
    if not api_key:
        print({"quo": {"send": "error", "reason": "missing_api_key", "env": API_KEY_ENV}})
        return False

    body = _build_body(message, phone)
    if body is None:
        return False

    try:
        resp = requests.post(
            API_URL,
            headers={
                "Authorization": api_key,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=timeout,
        )
        if resp.status_code != 202:
            print(
                {
                    "quo": {
                        "send": "error",
                        "status_code": resp.status_code,
                        "response": getattr(resp, "text", ""),
                    }
                }
            )
            return False
        return True
    except Exception as e:
        print({"quo": {"send": "error", "error": str(e)}})
        return False


def send_payload(payload: Mapping[str, Any], *, timeout: float = 10) -> bool:
    message = str(payload.get("message") or "")
    phone = str(payload.get("AssessmentPhone") or payload.get("ContactPhone") or "")
    return send_text(message, phone, timeout=timeout)
