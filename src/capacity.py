"""
Shared daily send capacity for campaign due-emails + autonomy pass.

When autopilot is on and live sending is enabled, both pipelines respect the
same soft company cap AND the multi-Gmail pool remaining capacity.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Optional


def _int(val: Any, default: int) -> int:
    try:
        return int(val)
    except Exception:
        return default


def shared_daily_cap(company: Optional[dict] = None) -> int:
    """Effective soft cap (autonomy_daily_email_cap ∩ autopilot_daily_target)."""
    from .agent_tools import DEFAULT_DAILY_EMAIL_CAP

    company = company or {}
    cap = _int(company.get("autonomy_daily_email_cap"), DEFAULT_DAILY_EMAIL_CAP)
    if cap <= 0:
        cap = DEFAULT_DAILY_EMAIL_CAP
    target = _int(company.get("autopilot_daily_target"), 0)
    if target > 0:
        cap = min(cap, target)
    return cap


def today_capacity(
    company: Optional[dict] = None,
    *,
    today: Optional[date] = None,
) -> dict[str, Any]:
    """
    Snapshot for Dashboard / runners:

      capacity   — effective soft cap today
      sent       — outbound log count today (live + dry_run)
      remaining  — min(soft remaining, pool remaining when pool usable)
      pool_cap / pool_sent / pool_remaining
      exhausted  — True when remaining == 0 and (soft or pool) blocked
      resumes_msg — human text when exhausted
      share_caps — True when autopilot + live (campaign & agent share pool)
    """
    from .agent_tools import emails_sent_today

    company = company or {}
    soft_cap = shared_daily_cap(company)
    sent = emails_sent_today(today=today)
    soft_remaining = max(0, soft_cap - sent)

    pool_cap = 0
    pool_sent = 0
    pool_remaining = 0
    pool_on = False
    try:
        from .mailboxes import pool_usable, today_usage, total_remaining_capacity

        if pool_usable():
            pool_on = True
            usage = today_usage()
            usable = [r for r in usage if r.get("enabled") and r.get("has_password")]
            pool_cap = sum(int(r.get("cap") or 0) for r in usable)
            pool_sent = sum(int(r.get("sent") or 0) for r in usable)
            pool_remaining = total_remaining_capacity()
    except Exception:
        pass

    if pool_on:
        remaining = min(soft_remaining, pool_remaining)
    else:
        remaining = soft_remaining

    live = bool(company.get("send_live_emails"))
    autopilot = bool(company.get("autonomy_autopilot"))
    share_caps = bool(live and autopilot)

    exhausted = remaining <= 0 and (sent >= soft_cap or (pool_on and pool_remaining <= 0))
    resumes_msg = ""
    if exhausted:
        if pool_on and pool_remaining <= 0:
            resumes_msg = (
                "Gmail pool at daily cap — sending resumes next day "
                "(America/Chicago calendar)."
            )
        else:
            resumes_msg = (
                f"Daily soft cap reached ({sent}/{soft_cap}) — "
                "remaining capacity resets tomorrow; due leads stay queued."
            )

    return {
        "capacity": soft_cap,
        "sent": sent,
        "remaining": remaining,
        "soft_cap": soft_cap,
        "soft_remaining": soft_remaining,
        "pool_on": pool_on,
        "pool_cap": pool_cap,
        "pool_sent": pool_sent,
        "pool_remaining": pool_remaining,
        "exhausted": exhausted,
        "resumes_msg": resumes_msg,
        "share_caps": share_caps,
        "live": live,
        "autopilot": autopilot,
    }


def can_send_under_shared_caps(
    company: Optional[dict] = None,
    *,
    today: Optional[date] = None,
) -> tuple[bool, str, dict[str, Any]]:
    """Return (ok, reason, snapshot). Used by campaign + autonomy send paths."""
    snap = today_capacity(company, today=today)
    if snap["remaining"] > 0:
        return True, "", snap
    return False, snap.get("resumes_msg") or "daily capacity exhausted", snap


def estimate_week_plan(
    *,
    lead_count: int = 4000,
    company: Optional[dict] = None,
    working_days: int = 5,
) -> dict[str, Any]:
    """
    One-click estimate: how many days to work through `lead_count` leads
    given today's pool + soft-cap throughput.
    """
    company = company or {}
    snap = today_capacity(company)
    # Prefer live pool capacity when configured; else soft cap; floor at 1
    if snap["pool_on"] and snap["pool_cap"] > 0:
        daily = snap["pool_cap"]
        source = "gmail_pool"
    else:
        daily = max(1, snap["soft_cap"])
        source = "soft_cap"
    target = _int(company.get("autopilot_daily_target"), 0)
    if target > 0:
        daily = min(daily, target)
        source = "autopilot_daily_target"

    leads = max(0, int(lead_count))
    days_needed = int(math.ceil(leads / daily)) if daily > 0 else 0
    weeks = days_needed / max(1, int(working_days))
    start = date.today()
    # Approximate calendar end skipping weekends lightly (Mon–Fri)
    remaining = days_needed
    cursor = start
    while remaining > 0:
        cursor = cursor + timedelta(days=1)
        if cursor.weekday() < 5:  # Mon=0 … Fri=4
            remaining -= 1

    return {
        "lead_count": leads,
        "daily_throughput": daily,
        "throughput_source": source,
        "days_needed": days_needed,
        "working_days_per_week": int(working_days),
        "weeks_approx": round(weeks, 1),
        "est_finish_date": cursor.isoformat() if days_needed else start.isoformat(),
        "capacity_snapshot": snap,
        "message": (
            f"{leads:,} leads @ ~{daily}/day ({source}) ≈ {days_needed} working day(s) "
            f"(~{round(weeks, 1)} week(s) at {working_days} days/week). "
            f"Est. finish {cursor.isoformat() if days_needed else 'today'}."
        ),
    }
