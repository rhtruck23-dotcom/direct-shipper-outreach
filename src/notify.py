"""Owner alerts — email always; SMS optional via Twilio."""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from .emailer import send_email
from .paths import ALERTS_JSON


def _save_alert(entry: dict) -> None:
    alerts: list = []
    if ALERTS_JSON.exists():
        with open(ALERTS_JSON, "r", encoding="utf-8") as f:
            alerts = json.load(f)
    alerts.append(entry)
    with open(ALERTS_JSON, "w", encoding="utf-8") as f:
        json.dump(alerts, f, indent=2)


def notify_owner(company: dict[str, Any], subject: str, body: str) -> dict:
    """Email the owner; optionally SMS if Twilio env vars are set."""
    to = company.get("owner_notify_email") or company.get("my_email")
    # Always log; send via same dry-run / live switch for email channel
    alert_company = dict(company)
    # Owner alerts should attempt email even in dry-run as a logged preview,
    # but respect send_live_emails for actual SMTP.
    result = send_email(
        to,
        f"[LogixTrek Outreach] {subject}",
        body,
        alert_company,
        meta={"type": "owner_alert"},
    )

    sms_status = _maybe_sms(body)
    entry = {
        "at": datetime.now().isoformat(),
        "subject": subject,
        "body": body,
        "email_result": result,
        "sms": sms_status,
    }
    _save_alert(entry)
    return entry


def _maybe_sms(body: str) -> dict:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_num = os.getenv("TWILIO_FROM_NUMBER", "")
    to_num = os.getenv("OWNER_SMS_NUMBER", "")
    if not all([sid, token, from_num, to_num]):
        return {"sent": False, "reason": "Twilio not configured — email-only alerts"}

    try:
        import requests

        url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
        # Keep SMS short
        text = body[:300] + ("…" if len(body) > 300 else "")
        resp = requests.post(
            url,
            data={"From": from_num, "To": to_num, "Body": text},
            auth=(sid, token),
            timeout=20,
        )
        return {"sent": resp.status_code in (200, 201), "status_code": resp.status_code}
    except Exception as e:
        return {"sent": False, "reason": str(e)}
