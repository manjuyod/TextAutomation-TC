import base64
import json
from email import policy
from email import message_from_bytes
from pathlib import Path
import sys
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


SERVICE_ACCOUNT_INFO = {
    "type": "service_account",
    "project_id": "test-project",
    "private_key_id": "key-id",
    "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
    "client_email": "sender@test-project.iam.gserviceaccount.com",
    "client_id": "123",
    "token_uri": "https://oauth2.googleapis.com/token",
}


def _split_info_env() -> dict[str, str]:
    raw = json.dumps(SERVICE_ACCOUNT_INFO)
    midpoint = len(raw) // 2
    return {
        "sysadmin_gmail_send_DWD_1": raw[:midpoint],
        "sysadmin_gmail_send_DWD_2": raw[midpoint:],
    }


def test_service_account_info_reconstructs_split_env():
    from text_automation.accounts.gmail import client

    with patch.dict("os.environ", _split_info_env(), clear=True):
        info = client.service_account_info_from_env()

    assert info == SERVICE_ACCOUNT_INFO


def test_service_account_info_reconstructs_json_object_shards():
    from text_automation.accounts.gmail import client

    shard_1 = {
        "type": SERVICE_ACCOUNT_INFO["type"],
        "project_id": SERVICE_ACCOUNT_INFO["project_id"],
        "private_key_id": SERVICE_ACCOUNT_INFO["private_key_id"],
        "private_key": SERVICE_ACCOUNT_INFO["private_key"],
    }
    shard_2 = {
        "client_email": SERVICE_ACCOUNT_INFO["client_email"],
        "client_id": SERVICE_ACCOUNT_INFO["client_id"],
        "token_uri": SERVICE_ACCOUNT_INFO["token_uri"],
    }

    with patch.dict(
        "os.environ",
        {
            "sysadmin_gmail_send_DWD_1": json.dumps(shard_1),
            "sysadmin_gmail_send_DWD_2": json.dumps(shard_2),
        },
        clear=True,
    ):
        info = client.service_account_info_from_env()

    assert info == {**shard_1, **shard_2}


def test_service_account_info_rejects_missing_env_without_secret_output():
    from text_automation.accounts.gmail import client

    with patch.dict("os.environ", {"sysadmin_gmail_send_DWD_1": "abc"}, clear=True):
        try:
            client.service_account_info_from_env()
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected RuntimeError")

    assert "sysadmin_gmail_send_DWD_1" in message
    assert "sysadmin_gmail_send_DWD_2" in message
    assert "abc" not in message


def test_service_account_info_rejects_invalid_json_without_secret_output():
    from text_automation.accounts.gmail import client

    with patch.dict(
        "os.environ",
        {
            "sysadmin_gmail_send_DWD_1": '{"private_key":"secret",',
            "sysadmin_gmail_send_DWD_2": "}",
        },
        clear=True,
    ):
        try:
            client.service_account_info_from_env()
        except RuntimeError as exc:
            message = str(exc)
        else:
            raise AssertionError("expected RuntimeError")

    assert "valid JSON" in message
    assert "secret" not in message


def test_build_raw_message_sets_headers_and_body():
    from text_automation.accounts.gmail import client

    raw = client.build_raw_message(
        sender_email="jacksonvillefl@tutoringclub.com",
        recipients=["bmillares@tutoringclub.com"],
        subject="Bruh",
        body="bruh",
    )

    decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    msg = message_from_bytes(decoded, policy=policy.default)
    assert msg["From"] == "jacksonvillefl@tutoringclub.com"
    assert msg["To"] == "bmillares@tutoringclub.com"
    assert msg["Subject"] == "Bruh"
    assert msg.get_content().strip() == "bruh"


def test_credentials_delegate_to_sender_with_gmail_send_scope():
    from text_automation.accounts.gmail import client

    with patch("text_automation.accounts.gmail.client.service_account.Credentials") as creds_cls:
        base_creds = creds_cls.from_service_account_info.return_value
        delegated_creds = base_creds.with_subject.return_value

        creds = client.delegated_credentials_for_sender(
            "jacksonvillefl@tutoringclub.com",
            service_account_info=SERVICE_ACCOUNT_INFO,
        )

    creds_cls.from_service_account_info.assert_called_once_with(
        SERVICE_ACCOUNT_INFO,
        scopes=[client.GMAIL_SEND_SCOPE],
    )
    base_creds.with_subject.assert_called_once_with("jacksonvillefl@tutoringclub.com")
    assert creds is delegated_creds


def test_send_email_uses_delegated_gmail_send_api_shape():
    from text_automation.accounts.gmail import client

    with patch("text_automation.accounts.gmail.client.service_account_info_from_env", return_value=SERVICE_ACCOUNT_INFO):
        with patch("text_automation.accounts.gmail.client.delegated_credentials_for_sender", return_value="creds") as mock_creds:
            with patch("text_automation.accounts.gmail.client.build") as mock_build:
                send_execute = (
                    mock_build.return_value.users.return_value.messages.return_value.send.return_value.execute
                )
                send_execute.return_value = {"id": "message-id"}

                result = client.send_email(
                    sender_email="jacksonvillefl@tutoringclub.com",
                    recipients=["bmillares@tutoringclub.com"],
                    subject="Bruh",
                    body="bruh",
                )

    assert result == {"id": "message-id"}
    mock_creds.assert_called_once_with(
        "jacksonvillefl@tutoringclub.com",
        service_account_info=SERVICE_ACCOUNT_INFO,
    )
    mock_build.assert_called_once_with("gmail", "v1", credentials="creds")
    send_call = mock_build.return_value.users.return_value.messages.return_value.send
    send_call.assert_called_once()
    _, kwargs = send_call.call_args
    assert kwargs["userId"] == "me"
    assert set(kwargs["body"]) == {"raw"}
    assert isinstance(kwargs["body"]["raw"], str)


def test_smoke_helper_sends_for_jacksonville_and_hodges_from_config():
    from text_automation.accounts.gmail import client
    from text_automation.config import Franchise

    class FakeConfig:
        franchises = (
            Franchise(62, "Tutoring Club of Jacksonville", "", "", "jacksonvillefl@tutoringclub.com", "America/New_York"),
            Franchise(95, "Hodges", "", "", "hodgesfl@tutoringclub.com", "America/New_York"),
        )

    with patch("text_automation.accounts.gmail.client.load_config", return_value=FakeConfig()):
        with patch("text_automation.accounts.gmail.client.send_email") as mock_send:
            mock_send.side_effect = [{"id": "jax"}, {"id": "hodges"}]

            results = client.send_jacksonville_hodges_smoke()

    assert results == [
        {"franchise_id": 62, "sender_email": "jacksonvillefl@tutoringclub.com", "result": {"id": "jax"}},
        {"franchise_id": 95, "sender_email": "hodgesfl@tutoringclub.com", "result": {"id": "hodges"}},
    ]
    assert [call.kwargs["sender_email"] for call in mock_send.call_args_list] == [
        "jacksonvillefl@tutoringclub.com",
        "hodgesfl@tutoringclub.com",
    ]
    for call in mock_send.call_args_list:
        assert call.kwargs["recipients"] == ["bmillares@tutoringclub.com"]
        assert call.kwargs["subject"] == "Bruh"
        assert call.kwargs["body"] == "bruh"


def test_smoke_helper_can_filter_to_one_franchise():
    from text_automation.accounts.gmail import client
    from text_automation.config import Franchise

    class FakeConfig:
        franchises = (
            Franchise(62, "Tutoring Club of Jacksonville", "", "", "jacksonvillefl@tutoringclub.com", "America/New_York"),
            Franchise(95, "Hodges", "", "", "hodgesfl@tutoringclub.com", "America/New_York"),
        )

    with patch("text_automation.accounts.gmail.client.load_config", return_value=FakeConfig()):
        with patch("text_automation.accounts.gmail.client.send_email", return_value={"id": "hodges"}) as mock_send:
            results = client.send_jacksonville_hodges_smoke(franchise_ids=[95])

    assert results == [
        {"franchise_id": 95, "sender_email": "hodgesfl@tutoringclub.com", "result": {"id": "hodges"}},
    ]
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["sender_email"] == "hodgesfl@tutoringclub.com"


def test_direct_inquiry_body_without_booking_url_uses_no_link_fallback():
    from text_automation.accounts.gmail import client

    body = client.build_jacksonville_hodges_direct_inquiry_body(
        parent_first_name="alex",
        student_first_name="jordan",
        booking_url="",
    )

    assert body == (
        "Hi Alex,\n\n"
        "Thanks so much for reaching out to Tutoring Club about Jordan! I'm looking forward to learning more about what support would be most helpful.\n\n"
        "Please reply with a few times that work for a quick 15-minute call, and I'll confirm a time with you.\n\n"
        "Talk soon,\n"
        "Michele Tanner\n"
        "Tutoring Club"
    )


def test_direct_inquiry_body_with_booking_url_includes_link():
    from text_automation.accounts.gmail import client

    body = client.build_jacksonville_hodges_direct_inquiry_body(
        parent_first_name="alex",
        student_first_name="",
        booking_url="https://calendar.example/jax",
    )

    assert body == (
        "Hi Alex,\n\n"
        "Thanks so much for reaching out to Tutoring Club about your student! Please use the link below to book a quick 15-minute call with me so we can figure out the best next step for your child.\n\n"
        "https://calendar.example/jax\n\n"
        "Feel free to reply to this email with any questions.\n\n"
        "Talk soon,\n"
        "Michele Tanner\n"
        "Tutoring Club"
    )


def test_direct_inquiry_helper_uses_franchise_sender_subject_and_recipient():
    from text_automation.accounts.gmail import client
    from text_automation.config import Franchise

    class FakeConfig:
        franchises = (
            Franchise(
                62,
                "Tutoring Club of Jacksonville",
                "",
                "",
                "jacksonvillefl@tutoringclub.com",
                "America/New_York",
                direct_inquiry_booking_url="https://calendar.example/jax",
            ),
            Franchise(95, "Hodges", "", "", "hodgesfl@tutoringclub.com", "America/New_York"),
        )

    with patch("text_automation.accounts.gmail.client.load_config", return_value=FakeConfig()):
        with patch("text_automation.accounts.gmail.client.send_email", return_value={"id": "email-id"}) as mock_send:
            result = client.send_jacksonville_hodges_direct_inquiry_email(
                parent_first_name="alex",
                student_first_name="jordan",
                recipient_email="alex@example.com",
                franchise_id=62,
            )

    assert result == {
        "franchise_id": 62,
        "sender_email": "jacksonvillefl@tutoringclub.com",
        "recipient_email": "alex@example.com",
        "result": {"id": "email-id"},
    }
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["sender_email"] == "jacksonvillefl@tutoringclub.com"
    assert mock_send.call_args.kwargs["recipients"] == ["alex@example.com"]
    assert mock_send.call_args.kwargs["subject"] == "Thanks for contacting tutoring club!"
    assert "https://calendar.example/jax" in mock_send.call_args.kwargs["body"]
