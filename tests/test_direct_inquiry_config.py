import sys
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from text_automation.assessments.data import _configured_franchise_ids_sql as assessment_ids_sql
from text_automation.config import load_config
from text_automation.direct_inquiry.parser import franchise_from_to_header
from text_automation.direct_inquiry.processor import _franchise_by_url_fragment
from text_automation.meetings.data import _configured_franchise_ids_sql as meeting_ids_sql


def test_rancho_cucamonga_is_direct_inquiry_only():
    cfg = load_config()
    rancho = next(f for f in cfg.franchises if f.id == 107)

    assert rancho.name == "Rancho Cucamonga"
    assert rancho.url == "https://tutoringclub.com/ranchocucamongaca/"
    assert rancho.director == "Gaby"
    assert rancho.email == "cucamongaca@tutoringclub.com"
    assert rancho.direct_inquiry_only is True

    msg = EmailMessage()
    msg["To"] = "CucamongaCA@tutoringclub.com"
    assert franchise_from_to_header(msg) == 107
    assert _franchise_by_url_fragment("https://tutoringclub.com/ranchocucamongaca/") == 107

    assert "107" not in assessment_ids_sql().split(",")
    assert "107" not in {part.strip() for part in meeting_ids_sql().split(",")}
