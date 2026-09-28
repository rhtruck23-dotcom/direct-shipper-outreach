"""
Optional IMAP inbox poll (feature-flagged, default OFF).

Reads recent INBOX messages from mailbox-pool accounts that store a Gmail
App Password. Never sends. Designed for unit tests with mocked imaplib.

Enable only when company["imap_poll_enabled"] is True.
"""
from __future__ import annotations

import email
import imaplib
import re
from dataclasses import dataclass, field
from email.header import decode_header
from typing import Any, Callable, Optional


DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_LOOKBACK = 20  # most-recent messages per mailbox


@dataclass
class InboundMessage:
    mailbox_email: str
    from_addr: str
    subject: str
    body: str
    message_id: str = ""
    date: str = ""
    raw_uid: str = ""


@dataclass
class PollResult:
    ok: bool
    enabled: bool
    messages: list[InboundMessage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    mailboxes_polled: int = 0


def imap_poll_enabled(company: Optional[dict] = None) -> bool:
    """Hard default OFF — must opt in via company / secrets."""
    return bool((company or {}).get("imap_poll_enabled"))


def _decode_mime(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return value.decode("latin-1", errors="replace")
    parts = decode_header(str(value))
    out = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            out.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(str(chunk))
    return "".join(out).strip()


def _extract_addr(raw: str) -> str:
    s = (raw or "").strip()
    m = re.search(r"<([^>]+)>", s)
    if m:
        return m.group(1).strip().lower()
    if "@" in s:
        return s.lower()
    return s.lower()


def _body_from_message(msg: email.message.Message) -> str:
    if msg.is_multipart():
        texts = []
        for part in msg.walk():
            ctype = (part.get_content_type() or "").lower()
            disp = str(part.get("Content-Disposition") or "").lower()
            if "attachment" in disp:
                continue
            if ctype == "text/plain":
                payload = part.get_payload(decode=True) or b""
                texts.append(_decode_mime(payload))
            elif ctype == "text/html" and not texts:
                payload = part.get_payload(decode=True) or b""
                html = _decode_mime(payload)
                # Naive strip tags for paste-friendly text
                plain = re.sub(r"<[^>]+>", " ", html)
                plain = re.sub(r"\s+", " ", plain).strip()
                texts.append(plain)
        return "\n".join(t for t in texts if t).strip()
    payload = msg.get_payload(decode=True) or b""
    return _decode_mime(payload).strip()


def parse_raw_email(raw: bytes, *, mailbox_email: str = "") -> InboundMessage:
    msg = email.message_from_bytes(raw)
    return InboundMessage(
        mailbox_email=(mailbox_email or "").lower(),
        from_addr=_extract_addr(_decode_mime(msg.get("From"))),
        subject=_decode_mime(msg.get("Subject")),
        body=_body_from_message(msg),
        message_id=_decode_mime(msg.get("Message-ID")),
        date=_decode_mime(msg.get("Date")),
    )


ImapFactory = Callable[..., Any]  # injectable for tests


def _poll_one_mailbox(
    mb: dict,
    *,
    lookback: int = DEFAULT_LOOKBACK,
    imap_factory: Optional[ImapFactory] = None,
) -> tuple[list[InboundMessage], Optional[str]]:
    email_addr = (mb.get("email") or mb.get("smtp_user") or "").strip().lower()
    password = (mb.get("smtp_password") or "").strip()
    if not email_addr or not password:
        return [], "missing email or app password"

    host = (mb.get("imap_host") or DEFAULT_IMAP_HOST).strip()
    try:
        port = int(mb.get("imap_port") or DEFAULT_IMAP_PORT)
    except Exception:
        port = DEFAULT_IMAP_PORT

    factory = imap_factory or imaplib.IMAP4_SSL
    try:
        conn = factory(host, port)
        try:
            conn.login(email_addr, password)
            typ, _ = conn.select("INBOX", readonly=True)
            if typ != "OK":
                return [], f"cannot select INBOX for {email_addr}"
            typ, data = conn.search(None, "ALL")
            if typ != "OK" or not data or not data[0]:
                return [], None
            ids = data[0].split()
            recent = ids[-max(1, int(lookback)) :]
            out: list[InboundMessage] = []
            for uid in recent:
                typ, fetched = conn.fetch(uid, "(RFC822)")
                if typ != "OK" or not fetched:
                    continue
                for item in fetched:
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue
                    raw = item[1]
                    if not isinstance(raw, bytes):
                        continue
                    inbound = parse_raw_email(raw, mailbox_email=email_addr)
                    inbound.raw_uid = (
                        uid.decode("ascii", errors="replace")
                        if isinstance(uid, bytes)
                        else str(uid)
                    )
                    out.append(inbound)
            return out, None
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as e:
        return [], f"{email_addr}: {e}"


def poll_recent_inbox(
    company: dict,
    *,
    mailboxes: Optional[list[dict]] = None,
    lookback: int = DEFAULT_LOOKBACK,
    imap_factory: Optional[ImapFactory] = None,
    force: bool = False,
) -> PollResult:
    """
    Read-only poll of enabled pool mailboxes.

    force=True bypasses the feature flag (tests / explicit UI "Poll once").
    """
    if not force and not imap_poll_enabled(company):
        return PollResult(ok=True, enabled=False, messages=[], errors=[])

    if mailboxes is None:
        try:
            from .mailboxes import enabled_with_password

            mailboxes = enabled_with_password()
        except Exception as e:
            return PollResult(
                ok=False,
                enabled=True,
                errors=[f"load mailboxes: {e}"],
            )

    messages: list[InboundMessage] = []
    errors: list[str] = []
    polled = 0
    for mb in mailboxes or []:
        polled += 1
        got, err = _poll_one_mailbox(
            mb, lookback=lookback, imap_factory=imap_factory
        )
        messages.extend(got)
        if err:
            errors.append(err)

    return PollResult(
        ok=len(errors) == 0,
        enabled=True,
        messages=messages,
        errors=errors,
        mailboxes_polled=polled,
    )


def mailto_compose_link(
    to_addr: str,
    *,
    subject: str = "",
    body: str = "",
) -> str:
    """Build a mailto: deep-link for 'Reply in Gmail' when IMAP is off."""
    from urllib.parse import quote

    to_addr = (to_addr or "").strip()
    q = []
    if subject:
        q.append(f"subject={quote(subject)}")
    if body:
        q.append(f"body={quote(body)}")
    qs = ("?" + "&".join(q)) if q else ""
    return f"mailto:{to_addr}{qs}"


def gmail_web_inbox_url(account_email: str = "") -> str:
    """Open Gmail web UI (optionally for a specific account)."""
    from urllib.parse import quote

    base = "https://mail.google.com/mail/u/0/#inbox"
    email_addr = (account_email or "").strip()
    if email_addr:
        return f"https://mail.google.com/mail/?authuser={quote(email_addr)}#inbox"
    return base
