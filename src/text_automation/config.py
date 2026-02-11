from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Franchise:
    id: int
    name: str
    url: str
    director: str
    email: str
    timezone: str
    # Optional, for assessments/meetings flows
    assessment_form: str = ""
    payment_form: str = ""
    address: str = ""
    assess_group: str = ""  # e.g., "vegas" or "cali"


@dataclass(frozen=True)
class DirectInquiryConfig:
    token_path: Path | None = None
    vegas_ids: tuple[int, ...] = (6, 11, 15, 16, 60)
    phone_blacklist: tuple[str, ...] = ()
    grade_phrase_map: dict[str, str] | None = None
    grade_sql_map: dict[str, str] | None = None


@dataclass(frozen=True)
class StudentIntakeConfig:
    token_path: Path | None = None


@dataclass(frozen=True)
class Config:
    env: str = "dev"
    legacy_root: Path | None = None
    reporting_db: Path | None = None
    direct_inquiry: DirectInquiryConfig | None = None
    student_intake: StudentIntakeConfig | None = None
    franchises: tuple[Franchise, ...] = ()


def _project_root() -> Path:
    # src/text_automation/config.py -> repo root is two parents up from src
    here = Path(__file__).resolve()
    return here.parents[3] if (len(here.parents) >= 4 and here.parents[2].name == "src") else here.parents[2]


def _load_toml(path: Path) -> Mapping[str, Any]:
    try:
        import tomllib  # py311+
    except Exception as e:  # pragma: no cover - py311 requirement noted
        raise RuntimeError("Python 3.11+ is required for tomllib") from e

    if not path.exists():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(config_file: Path | None = None) -> Config:
    root = _project_root()
    cfg_file = config_file or (root / "text_automation.toml")
    data = _load_toml(cfg_file) if cfg_file.exists() else {}

    env = os.getenv("TEXT_AUTOMATION_ENV", data.get("env", "dev"))
    legacy_root = data.get("legacy_root")
    legacy_path = Path(legacy_root) if legacy_root else (root / "Legacy Files to Migrate and Implement")

    # Optional reporting SQLite DB path
    reporting_cfg = data.get("reporting", {}) if isinstance(data, dict) else {}
    reporting_db = os.getenv("TEXT_AUTOMATION_REPORT_DB", reporting_cfg.get("database"))
    reporting_path = Path(reporting_db) if reporting_db else None

    # Direct Inquiry
    di_cfg = data.get("direct_inquiry", {}) if isinstance(data, dict) else {}
    token_path_str = di_cfg.get("token_path")
    token_path = Path(token_path_str) if token_path_str else (root / "Legacy Files to Migrate and Implement/DirectToInquiryPackage/token.json")
    vegas_ids = tuple(di_cfg.get("vegas_ids", [6, 11, 15, 16, 60]))
    phone_blacklist = tuple(str(x) for x in di_cfg.get("phone_blacklist", []))
    grade_phrase_map = di_cfg.get("grade_phrase_map") or None
    grade_sql_map = di_cfg.get("grade_sql_map") or None
    direct_inquiry = DirectInquiryConfig(
        token_path=token_path,
        vegas_ids=vegas_ids,
        phone_blacklist=phone_blacklist,
        grade_phrase_map=grade_phrase_map,
        grade_sql_map=grade_sql_map,
    )

    # Student Intake (separate Gmail token path)
    si_cfg = data.get("student_intake", {}) if isinstance(data, dict) else {}
    si_token_path_str = si_cfg.get("token_path")
    si_token_path = (
        Path(si_token_path_str)
        if si_token_path_str
        else (root / "Legacy Files to Migrate and Implement/StudentAutoToDB/token.json")
    )
    student_intake = StudentIntakeConfig(token_path=si_token_path)

    # Franchises list
    franchises_list = []
    for obj in (data.get("franchises") or []):
        try:
            franchises_list.append(
                Franchise(
                    id=int(obj["id"]),
                    name=str(obj.get("name", "")),
                    url=str(obj.get("url", "")),
                    director=str(obj.get("director", "")),
                    email=str(obj.get("email", "")),
                    timezone=str(obj.get("timezone", "America/Los_Angeles")),
                    assessment_form=str(obj.get("assessment_form", "")),
                    payment_form=str(obj.get("payment_form", "")),
                    address=str(obj.get("address", "")),
                    assess_group=str(obj.get("assess_group", "")),
                )
            )
        except Exception:
            continue

    # If none provided, seed with known defaults from legacy
    if not franchises_list:
        franchises_list = [
            Franchise(1, "Test", "https://tutoringclub.com/test/", "Daniel", "bmillares@tutoringclub.com", "America/Los_Angeles"),
            Franchise(57, "Gilbert", "https://tutoringclub.com/gilbertaz/", "Ryan", "gilbertaz@tutoringclub.com", "America/Phoenix"),
            Franchise(24, "North Fresno", "https://tutoringclub.com/gilbertaz/", "Ryan", "fresnoca@tutoringclub.com", "America/Los_Angeles"),
            Franchise(19, "Tutoring Club of Tustin", "https://tutoringclub.com/tustinca/", "Tim", "tustinca@tutoringclub.com", "America/Los_Angeles"),
            Franchise(8, "Fountain Valley CA", "https://tutoringclub.com/fountain-valley-ca/", "Huy", "fountainvalleyca@tutoringclub.com", "America/Los_Angeles"),
            Franchise(20, "Clovis", "https://tutoringclub.com/clovisca/", "Katie", "clovisca@tutoringclub.com", "America/Los_Angeles"),
            Franchise(87, "Downey", "https://tutoringclub.com/downeyca/", "David", "downeyca@tutoringclub.com", "America/Los_Angeles"),
            Franchise(15, "North Las Vegas", "https://tutoringclub.com/northlasvegasnv/", "Jessica", "northlasvegasnv@tutoringclub.com", "America/Los_Angeles"),
            Franchise(60, "Centennial", "https://tutoringclub.com/centennialnv/", "Jessica", "centennialnv@tutoringclub.com", "America/Los_Angeles"),
            Franchise(11, "Green Valley", "https://tutoringclub.com/hendersonnv/", "Shannon", "hendersonnv@tutoringclub.com", "America/Los_Angeles"),
            Franchise(6, "Anthem", "https://tutoringclub.com/anthemnv/", "Shannon", "anthemnv@tutoringclub.com", "America/Los_Angeles"),
            Franchise(16, "Rhodes Ranch", "https://tutoringclub.com/rhodesranchnv/", "Shannon", "rhodesranchnv@tutoringclub.com", "America/Los_Angeles"),
        ]

    return Config(
        env=env,
        legacy_root=legacy_path if legacy_path.exists() else None,
        reporting_db=reporting_path if (reporting_path and reporting_path.exists()) else None,
        direct_inquiry=direct_inquiry,
        student_intake=student_intake,
        franchises=tuple(franchises_list),
    )
