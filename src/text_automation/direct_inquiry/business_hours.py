from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Optional

from ..config import load_config


@dataclass(frozen=True)
class Hours:
    open: time
    close: time


DEFAULT_WEEKDAY_HOURS = Hours(time(10, 0, 0), time(19, 0, 0))  # Mon-Thu
DEFAULT_SATURDAY_HOURS = Hours(time(10, 0, 0), time(14, 0, 0))  # Sat


def franchise_timezone(franchise_id: int) -> ZoneInfo:
    cfg = load_config()
    tz_name = next((f.timezone for f in cfg.franchises if f.id == franchise_id), "America/Los_Angeles")
    try:
        return ZoneInfo(tz_name)
    except Exception:
        return ZoneInfo("America/Los_Angeles")


def localize_timestamp(utc_dt: datetime, franchise_id: int) -> Optional[datetime]:
    if not utc_dt:
        return None
    try:
        tz = franchise_timezone(franchise_id)
        # utc_dt expected to be timezone-aware in UTC
        return utc_dt.astimezone(tz)
    except Exception:
        return None


def in_business_window(local_dt: Optional[datetime]) -> bool:
    if local_dt is None:
        return False
    dow = local_dt.weekday()  # Mon=0 ... Sun=6
    t = local_dt.time()
    if 0 <= dow <= 3:
        return DEFAULT_WEEKDAY_HOURS.open <= t <= DEFAULT_WEEKDAY_HOURS.close
    #if dow == 5:
        #return DEFAULT_SATURDAY_HOURS.open <= t <= DEFAULT_SATURDAY_HOURS.close
    return False

