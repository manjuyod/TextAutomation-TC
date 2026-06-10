import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def test_hodges_template_matches_pasted_visible_copy_and_branding():
    from text_automation.direct_inquiry.email import (
        BOOKING_URL,
        DIRECT_INQUIRY_SUBJECT,
        render_jacksonville_hodges_direct_inquiry_email,
    )

    rendered = render_jacksonville_hodges_direct_inquiry_email(
        parent_first_name="alex",
        franchise_id=95,
    )

    assert rendered.subject == DIRECT_INQUIRY_SUBJECT
    assert "Hi <span" in rendered.html_body
    assert "Alex" in rendered.html_body
    assert "[Parent Name]" not in rendered.html_body
    assert "Thank you so much for reaching out to Tutoring Club Jacksonville" in rendered.html_body
    assert "Michele Tanner, MA" in rendered.html_body
    assert "Admissions Director" in rendered.html_body
    assert "Tutoring Club Hodges" in rendered.html_body
    assert "Tutoring Club of Hodges" in rendered.html_body
    assert "13546 Beach Blvd. Unit #06" in rendered.html_body
    assert "Jacksonville, FL 32224" in rendered.html_body
    assert "(904) 268-8556" in rendered.html_body
    assert BOOKING_URL in rendered.html_body
    assert "Book Your Call Here" in rendered.html_body
    assert "background-color:rgb(64,180,229)" in rendered.html_body
    assert "https://www.tutoringclub.com/hodgesfl/" in rendered.html_body
    assert "https://www.facebook.com/TutoringClubJacksonville" in rendered.html_body
    assert "https://www.instagram.com/tutoringclubhodges/" in rendered.html_body
    assert 'src="cid:hodges-business-card"' in rendered.html_body
    assert "Michele Tanner business card" in rendered.html_body
    assert "googleusercontent.com/mail-sig" not in rendered.html_body
    assert "mail.google.com" not in rendered.html_body
    assert "data-saferedirecturl" not in rendered.html_body
    assert "multisend-unsubscribe" not in rendered.html_body
    assert len(rendered.inline_images) == 1
    assert rendered.inline_images[0].content_id == "hodges-business-card"
    assert rendered.inline_images[0].filename == "hodges_business_card.jpg"
    assert rendered.inline_images[0].content_type == "image/jpeg"
    assert rendered.inline_images[0].data.startswith(b"\xff\xd8\xff")

    assert "Hi Alex," in rendered.plain_text
    assert "Book Your Call Here:" in rendered.plain_text
    assert BOOKING_URL in rendered.plain_text
    assert "Tutoring Club of Hodges" in rendered.plain_text


def test_jacksonville_template_uses_jacksonville_branding():
    from text_automation.direct_inquiry.email import render_jacksonville_hodges_direct_inquiry_email

    rendered = render_jacksonville_hodges_direct_inquiry_email(
        parent_first_name="alex",
        franchise_id=62,
    )

    assert "Tutoring Club Jacksonville" in rendered.html_body
    assert "Tutoring Club of Hodges" not in rendered.html_body
    assert "Tutoring Club of Jacksonville / Mandarin, FL" in rendered.html_body
    assert "10131 San Jose Boulevard" in rendered.html_body
    assert "Suite 17" in rendered.html_body
    assert "Jacksonville, FL 32257" in rendered.html_body
    assert "https://www.tutoringclub.com/jacksonvillefl/" in rendered.html_body
    assert "https://www.instagram.com/tutoringclubjacksonville/" in rendered.html_body
    assert 'src="cid:jacksonville-business-card"' in rendered.html_body
    assert len(rendered.inline_images) == 1
    assert rendered.inline_images[0].content_id == "jacksonville-business-card"
    assert rendered.inline_images[0].filename == "jacksonville_business_card.png"
    assert rendered.inline_images[0].content_type == "image/png"
    assert rendered.inline_images[0].data.startswith(b"\x89PNG\r\n\x1a\n")
    assert "Tutoring Club of Jacksonville / Mandarin, FL" in rendered.plain_text


def test_template_escapes_parent_name_in_html_but_not_plain_text():
    from text_automation.direct_inquiry.email import render_jacksonville_hodges_direct_inquiry_email

    rendered = render_jacksonville_hodges_direct_inquiry_email(
        parent_first_name='alex <script>alert("x")</script>',
        franchise_id=95,
    )

    assert "<script>" not in rendered.html_body
    assert "&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;" in rendered.html_body
    assert 'Alex <script>alert("x")</script>' in rendered.plain_text


def test_direct_inquiry_email_send_uses_franchise_sender_and_html_body():
    from text_automation.config import Franchise
    from text_automation.direct_inquiry import email as di_email

    class FakeConfig:
        franchises = (
            Franchise(95, "Hodges", "", "", "hodgesfl@tutoringclub.com", "America/New_York"),
        )

    with patch("text_automation.direct_inquiry.email.load_config", return_value=FakeConfig()):
        with patch("text_automation.direct_inquiry.email.send_email", return_value={"id": "email-id"}) as mock_send:
            result = di_email.send_jacksonville_hodges_direct_inquiry_email(
                parent_first_name="alex",
                student_first_name="jordan",
                recipient_email="alex@example.com",
                franchise_id=95,
            )

    assert result == {
        "franchise_id": 95,
        "sender_email": "hodgesfl@tutoringclub.com",
        "recipient_email": "alex@example.com",
        "result": {"id": "email-id"},
    }
    mock_send.assert_called_once()
    assert mock_send.call_args.kwargs["sender_email"] == "hodgesfl@tutoringclub.com"
    assert mock_send.call_args.kwargs["recipients"] == ["alex@example.com"]
    assert mock_send.call_args.kwargs["subject"] == di_email.DIRECT_INQUIRY_SUBJECT
    assert "Hi Alex," in mock_send.call_args.kwargs["body"]
    assert "Book Your Call Here" in mock_send.call_args.kwargs["html_body"]
    assert mock_send.call_args.kwargs["inline_images"][0].content_id == "hodges-business-card"
