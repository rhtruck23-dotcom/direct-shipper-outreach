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
    """Send or dry-run. Prefer Gmail App Password (SMTP); OAuth only if no password."""
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

    password = (company.get("smtp_password") or "").strip()
    smtp_user = (company.get("smtp_user") or company.get("my_email") or "").strip()
    from_email = (company.get("my_email") or smtp_user or "").strip()

    # 1) Simple path: Gmail App Password via SMTP
    if password:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_addr
        msg["Reply-To"] = from_email

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(
                company.get("smtp_host") or "smtp.gmail.com",
                int(company.get("smtp_port", 587)),
            ) as server:
                server.starttls(context=context)
                server.login(smtp_user or from_email, password)
                server.sendmail(from_email, [to_addr], msg.as_string())
            result["mode"] = "live"
            result["from"] = from_email
        except Exception as e:
            result["ok"] = False
            result["error"] = str(e)
            result["mode"] = "live_failed"

        _append_log(result)
        return result

    # 2) Optional: Gmail OAuth if App Password not set
    try:
        from .gmail_oauth import gmail_connected, send_via_gmail

        if gmail_connected():
            sent = send_via_gmail(
                to_addr,
                subject,
                body,
                from_email=from_email,
            )
            result["mode"] = "live_gmail"
            result["gmail_id"] = sent.get("id")
            result["from"] = sent.get("email")
            _append_log(result)
            return result
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
        result["mode"] = "live_failed"
        _append_log(result)
        return result

    result["ok"] = False
    result["error"] = (
        "Paste a Gmail App Password in Email setup, then Save & enable LIVE."
    )
    result["mode"] = "live_failed"
    _append_log(result)
    return result
