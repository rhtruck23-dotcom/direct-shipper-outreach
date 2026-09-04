"""Sequence scheduling — who is due for email 1–4."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from .templates import SEQUENCE_SCHEDULE_DAYS


def next_action_for_lead(lead: dict, today: Optional[datetime] = None) -> Optional[int]:
    """Return sequence step 1–4 due today, or None."""
    if lead.get("status") in ("responded", "do_not_contact", "converted"):
        return None
    if not lead.get("active_sequence"):
        return None

    today = today or datetime.now()

    if lead.get("status") == "not_started" or int(lead.get("last_step_sent") or 0) == 0:
        return 1

    last_step = int(lead.get("last_step_sent") or 0)
    if last_step >= 4:
        return None

    next_step = last_step + 1
    days_required = SEQUENCE_SCHEDULE_DAYS.get(next_step)
    if days_required is None:
        return None

    first = lead.get("first_contacted")
    if not first:
        return next_step

    days_since_first = (today - datetime.fromisoformat(first)).days
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
    last_step = int(lead.get("last_step_sent") or 0)
    if last_step == 0:
        return 0
    if last_step >= 4:
        return None
    next_step = last_step + 1
    days_required = SEQUENCE_SCHEDULE_DAYS.get(next_step, 0)
    first = lead.get("first_contacted")
    if not first:
        return 0
    days_since = (today - datetime.fromisoformat(first)).days
    remaining = days_required - days_since
    return max(0, remaining)
