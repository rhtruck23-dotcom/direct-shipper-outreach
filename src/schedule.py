"""Sequence scheduling — who is due for email 1–4."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .templates import SEQUENCE_SCHEDULE_DAYS


def parse_dt(value) -> Optional[datetime]:
    """Parse dates from ISO, Google Sheets, or loose strings. Never crash."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text or text.lower() in ("none", "null", "nan"):
        return None
    # Google Sheets / Excel sometimes return serial-looking numbers
    try:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # treat as unix-ish only if huge; otherwise skip
            return None
    except Exception:
        pass

    # Normalize common variants
    text = text.replace("Z", "+00:00")
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)

    for candidate in (text, text.split(".")[0], text[:19], text[:10]):
        try:
            return datetime.fromisoformat(candidate)
        except Exception:
            continue

    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%m/%d/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text[:19], fmt) if len(fmt) > 10 else datetime.strptime(text[:10], fmt)
        except Exception:
            continue
    return None


def next_action_for_lead(lead: dict, today: Optional[datetime] = None) -> Optional[int]:
    """Return sequence step 1–4 due today, or None."""
    if lead.get("status") in ("responded", "do_not_contact", "converted"):
        return None
    if not lead.get("active_sequence"):
        return None

    today = today or datetime.now()

    try:
        last_step = int(float(lead.get("last_step_sent") or 0))
    except Exception:
        last_step = 0

    if lead.get("status") == "not_started" or last_step == 0:
        return 1

    if last_step >= 4:
        return None

    next_step = last_step + 1
    days_required = SEQUENCE_SCHEDULE_DAYS.get(next_step)
    if days_required is None:
        return None

    first = parse_dt(lead.get("first_contacted"))
    if not first:
        return next_step

    days_since_first = (today - first.replace(tzinfo=None)).days
    if days_since_first >= days_required:
        return next_step
    return None


def days_until_next(lead: dict, today: Optional[datetime] = None) -> Optional[int]:
    """How many days until next email, or None if not in sequence / done."""
    if lead.get("status") in ("responded", "do_not_contact", "converted"):
        return None
    if not lead.get("active_sequence"):
        return None
    today = today or datetime.now()
    try:
        last_step = int(float(lead.get("last_step_sent") or 0))
    except Exception:
        last_step = 0
    if last_step == 0:
        return 0
    if last_step >= 4:
        return None
    next_step = last_step + 1
    days_required = SEQUENCE_SCHEDULE_DAYS.get(next_step, 0)
    first = parse_dt(lead.get("first_contacted"))
    if not first:
        return 0
    days_since = (today - first.replace(tzinfo=None)).days
    remaining = days_required - days_since
    return max(0, remaining)
