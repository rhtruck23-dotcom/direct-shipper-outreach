"""SMTP email sending with dry-run safety and multi-Gmail mailbox pool."""
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


def _send_via_smtp(
    *,
    to_addr: str,
    subject: str,
    body: str,
    from_email: str,
    smtp_user: str,
    password: str,
    smtp_host: str,
    smtp_port: int,
) -> None:
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_addr
    msg["Reply-To"] = from_email

    context = ssl.create_default_context()
    with smtplib.SMTP(smtp_host or "smtp.gmail.com", int(smtp_port or 587)) as server:
        server.starttls(context=context)
        server.login(smtp_user or from_email, password)
        server.sendmail(from_email, [to_addr], msg.as_string())


def send_email(
    to_addr: str,
    subject: str,
    body: str,
    company: dict[str, Any],
    meta: dict | None = None,
) -> dict:
    """Send or dry-run. Prefer mailbox pool when configured; else company SMTP/OAuth.

    Dry-runs do NOT increment mailbox daily counters.
    """
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

    # --- Multi-Gmail pool (when any enabled mailbox has App Password) ---
    try:
        from .mailboxes import pick_mailbox, pool_usable, record_send

        if pool_usable():
            mb = pick_mailbox()
            if mb is None:
                result["ok"] = False
                result["error"] = (
                    "All Gmail pool mailboxes are at today's daily cap. "
                    "Sending resumes next day (America/Chicago)."
                )
                result["mode"] = "live_failed"
                result["mailbox_exhausted"] = True
                _append_log(result)
                return result

            from_email = (mb.get("email") or mb.get("smtp_user") or "").strip()
            smtp_user = (mb.get("smtp_user") or from_email).strip()
            password = (mb.get("smtp_password") or "").strip()
            try:
                _send_via_smtp(
                    to_addr=to_addr,
                    subject=subject,
                    body=body,
                    from_email=from_email,
                    smtp_user=smtp_user,
                    password=password,
                    smtp_host=mb.get("smtp_host") or "smtp.gmail.com",
                    smtp_port=int(mb.get("smtp_port") or 587),
                )
                record_send(mb["id"])
                result["mode"] = "live"
                result["from"] = from_email
                result["mailbox_id"] = mb.get("id")
                result["mailbox_email"] = from_email
            except Exception as e:
                result["ok"] = False
                result["error"] = str(e)
                result["mode"] = "live_failed"
                result["mailbox_id"] = mb.get("id")
                result["mailbox_email"] = from_email
            _append_log(result)
            return result
    except Exception as e:
        # Pool import/load failure → fall through to company SMTP
        result["pool_error"] = str(e)

    # --- Single company SMTP (fallback when pool empty) ---
    password = (company.get("smtp_password") or "").strip()
    smtp_user = (company.get("smtp_user") or company.get("my_email") or "").strip()
    from_email = (company.get("my_email") or smtp_user or "").strip()

    if password:
        try:
            _send_via_smtp(
                to_addr=to_addr,
                subject=subject,
                body=body,
                from_email=from_email,
                smtp_user=smtp_user or from_email,
                password=password,
                smtp_host=company.get("smtp_host") or "smtp.gmail.com",
                smtp_port=int(company.get("smtp_port", 587)),
            )
            result["mode"] = "live"
            result["from"] = from_email
        except Exception as e:
            result["ok"] = False
            result["error"] = str(e)
            result["mode"] = "live_failed"

        _append_log(result)
        return result

    # Optional: Gmail OAuth if App Password not set
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
        "Add Gmail accounts in the send pool (or paste a company App Password), "
        "then Save & enable LIVE."
    )
    result["mode"] = "live_failed"
    _append_log(result)
    return result
