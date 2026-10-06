"""SMTP email sending with dry-run safety and multi-Gmail mailbox pool."""
from __future__ import annotations

import json
import smtplib
import ssl
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

from .paths import OUTBOUND_LOG


def _append_log(entry: dict) -> None:
    log: list = []
    if OUTBOUND_LOG.exists():
        with open(OUTBOUND_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)
    log.append(entry)
    with open(OUTBOUND_LOG, "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2)


def _build_message(
    *,
    to_addr: str,
    subject: str,
    body: str,
    from_email: str,
    attachments: Optional[list[dict[str, Any]]] = None,
) -> MIMEMultipart | MIMEText:
    atts = [a for a in (attachments or []) if a and a.get("content") is not None]
    if not atts:
        msg: MIMEMultipart | MIMEText = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_email
        msg["To"] = to_addr
        msg["Reply-To"] = from_email
        return msg

    msg = MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_addr
    msg["Reply-To"] = from_email
    msg.attach(MIMEText(body))
    for att in atts:
        raw = att["content"]
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        filename = att.get("filename") or "attachment.bin"
        subtype = att.get("subtype") or "octet-stream"
        part = MIMEApplication(raw, _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=filename)
        msg.attach(part)
    return msg


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
    attachments: Optional[list[dict[str, Any]]] = None,
) -> None:
    msg = _build_message(
        to_addr=to_addr,
        subject=subject,
        body=body,
        from_email=from_email,
        attachments=attachments,
    )
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
    attachments: Optional[list[dict[str, Any]]] = None,
) -> dict:
    """Send or dry-run. Prefer mailbox pool when configured; else company SMTP/OAuth.

    attachments: optional list of {filename, content(bytes), subtype?} e.g. subtype=pdf
    Dry-runs do NOT increment mailbox daily counters.
    """
    live = bool(company.get("send_live_emails"))
    att_meta = [
        {"filename": a.get("filename"), "bytes": len(a.get("content") or b"")}
        for a in (attachments or [])
        if a
    ]
    result = {
        "to": to_addr,
        "subject": subject,
        "body": body,
        "live": live,
        "ok": True,
        "error": None,
        "at": datetime.now().isoformat(),
        "attachments": att_meta,
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
                    attachments=attachments,
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
                attachments=attachments,
            )
            result["mode"] = "live"
            result["from"] = from_email
        except Exception as e:
            result["ok"] = False
            result["error"] = str(e)
            result["mode"] = "live_failed"

        _append_log(result)
        return result

    # Optional: Gmail OAuth if App Password not set (attachments not supported here)
    if attachments:
        result["ok"] = False
        result["error"] = (
            "PDF attachments require SMTP App Password (Gmail pool or company SMTP). "
            "Gmail OAuth path does not attach files yet."
        )
        result["mode"] = "live_failed"
        _append_log(result)
        return result

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
