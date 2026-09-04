"""SMTP email sending with dry-run safety."""
from __future__ import annotations

import json
import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from typing import Any

from .paths import OUTBOUND_LOG


def _append_log(entry: dict) -> None:
    log: list = []
    if OUTBOUND_LOG.exists():
        with open(OUTBOUND_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)
    log.append(entry)
    with open(OUTBOUND_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def send_email(
    to_addr: str,
    subject: str,
    body: str,
    company: dict[str, Any],
    meta: dict | None = None,
) -> dict:
    """Send or dry-run. Returns result dict."""
    live = bool(company.get("send_live_emails"))
    result = {
        "to": to_addr,
        "subject": subject,
        "body": body,
        "live": live,
        "ok": True,
        "error": None,
        "at": datetime.now().isoformat(),
        **(meta or {}),
    }

    if not live:
        result["mode"] = "dry_run"
        _append_log(result)
        return result

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = company["my_email"]
    msg["To"] = to_addr
    msg["Reply-To"] = company.get("my_email", "")

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(company["smtp_host"], int(company.get("smtp_port", 587))) as server:
            server.starttls(context=context)
            password = company.get("smtp_password") or ""
            if not password:
                raise ValueError("SMTP password is empty — set it in Org Setup or .env")
            server.login(company["smtp_user"], password)
            server.sendmail(company["my_email"], [to_addr], msg.as_string())
        result["mode"] = "live"
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
        result["mode"] = "live_failed"

    _append_log(result)
    return result
