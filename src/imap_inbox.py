"""
Optional IMAP inbox poll (feature-flagged, default OFF).

Reads recent UNSEEN / recent INBOX messages from mailbox-pool accounts that
store a Gmail App Password. Never sends. Read-only IMAP (does not mark-all-read).

Designed for unit tests with mocked imaplib.

Enable light auto-poll when company["imap_poll_enabled"] is True (or Autopilot).
Dashboard **Check inbox for replies** always force-polls once.
"""
from __future__ import annotations

import email
import imaplib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from email.header import decode_header
from pathlib import Path
from typing import Any, Callable, Optional

from .paths import DATA_DIR


DEFAULT_IMAP_HOST = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_LOOKBACK = 20  # most-recent messages per mailbox
SEEN_JSON = DATA_DIR / "imap_seen_message_ids.json"


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


@dataclass
class MatchedReply:
    funnel: str  # shipper | carrier | lead_x
    lead_email: str
    company_name: str
    lead_key: str
    message: InboundMessage
    applied: bool = False
    skipped_reason: str = ""  # dnc | duplicate | unknown | error
    task_id: str = ""


@dataclass
class InboxCheckResult:
    poll: PollResult
    matches: list[MatchedReply] = field(default_factory=list)
    applied: int = 0
    skipped_dnc: int = 0
    skipped_dup: int = 0
    skipped_unknown: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.poll.ok and not self.errors


def imap_poll_enabled(company: Optional[dict] = None) -> bool:
    """Hard default OFF — must opt in via company / secrets."""
    return bool((company or {}).get("imap_poll_enabled"))


def should_auto_poll(company: Optional[dict] = None) -> bool:
    """Light auto-poll when IMAP toggle OR Autopilot is on."""
    c = company or {}
    return bool(c.get("imap_poll_enabled") or c.get("autonomy_autopilot"))


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


def _load_seen_ids(path: Optional[Path] = None) -> set[str]:
    p = path or SEEN_JSON
    if not p.exists():
        return set()
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {str(x).strip() for x in data if str(x).strip()}
        if isinstance(data, dict):
            return {str(x).strip() for x in (data.get("ids") or []) if str(x).strip()}
    except Exception:
        return set()
    return set()


def _save_seen_ids(ids: set[str], path: Optional[Path] = None) -> None:
    p = path or SEEN_JSON
    # Cap growth — keep newest-ish by sorting; message-ids are opaque
    ordered = sorted(ids)[-2000:]
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"ids": ordered}, f, indent=2)


def _message_fingerprint(msg: InboundMessage) -> str:
    mid = (msg.message_id or "").strip()
    if mid:
        return mid.lower()
    # Fallback when Message-ID missing
    return f"{msg.from_addr}|{msg.subject}|{(msg.body or '')[:120]}".lower()


def _poll_one_mailbox(
    mb: dict,
    *,
    lookback: int = DEFAULT_LOOKBACK,
    imap_factory: Optional[ImapFactory] = None,
    prefer_unseen: bool = True,
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
            # readonly=True → do not flip \Seen aggressively
            typ, _ = conn.select("INBOX", readonly=True)
            if typ != "OK":
                return [], f"cannot select INBOX for {email_addr}"

            ids: list[bytes] = []
            if prefer_unseen:
                typ_u, data_u = conn.search(None, "UNSEEN")
                if typ_u == "OK" and data_u and data_u[0]:
                    ids = data_u[0].split()
            if not ids:
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
    prefer_unseen: bool = True,
) -> PollResult:
    """
    Read-only poll of enabled pool mailboxes.

    force=True bypasses the feature flag (tests / explicit UI "Check inbox").
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
            mb,
            lookback=lookback,
            imap_factory=imap_factory,
            prefer_unseen=prefer_unseen,
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


def _normalize_email(addr: str) -> str:
    return (addr or "").strip().lower()


def _is_dnc(lead: dict) -> bool:
    status = (lead.get("status") or "").strip().lower()
    crm = (lead.get("crm_status") or "").strip().lower()
    return status == "do_not_contact" or crm == "dnc"


def _lead_already_has_message(lead: dict, fingerprint: str) -> bool:
    fp = (fingerprint or "").lower()
    if not fp:
        return False
    for m in lead.get("conversation") or []:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("message_id") or "").strip().lower()
        if mid and mid == fp:
            return True
        if m.get("direction") == "inbound" and m.get("imap_fp") == fp:
            return True
    return False


def build_lead_email_index(
    *,
    shipper_leads: Optional[list[dict]] = None,
    carrier_leads: Optional[list[dict]] = None,
    x_leads: Optional[list[dict]] = None,
) -> dict[str, tuple[dict, str]]:
    """Map contact email → (lead dict, funnel). First wins on collision."""
    index: dict[str, tuple[dict, str]] = {}

    def _add(leads: list[dict], funnel: str) -> None:
        for lead in leads or []:
            email_addr = _normalize_email(lead.get("email") or "")
            if not email_addr or "@" not in email_addr:
                continue
            if email_addr not in index:
                index[email_addr] = (lead, funnel)

    _add(shipper_leads or [], "shipper")
    _add(carrier_leads or [], "carrier")
    _add(x_leads or [], "lead_x")
    return index


def _load_all_funnel_leads() -> tuple[list[dict], list[dict], list[dict]]:
    shipper: list[dict] = []
    carrier: list[dict] = []
    x_leads: list[dict] = []
    try:
        from .storage import load_all_leads

        shipper = load_all_leads()
    except Exception:
        shipper = []
    try:
        from .carrier_storage import load_all_carriers

        carrier = load_all_carriers()
    except Exception:
        carrier = []
    try:
        from .project_x.store import get_active_project, load_leads_for_project

        proj = get_active_project()
        if proj:
            x_leads = load_leads_for_project(proj["id"])
    except Exception:
        x_leads = []
    return shipper, carrier, x_leads


def _persist_funnel_lead(lead: dict, funnel: str) -> None:
    if funnel == "carrier":
        from .carrier_storage import update_carrier

        update_carrier(lead)
    elif funnel == "lead_x":
        from .project_x.store import update_x_lead

        update_x_lead(lead)
    else:
        from .storage import update_lead

        update_lead(lead)


def _mark_responded(lead: dict, funnel: str, *, positive: bool = True) -> None:
    if funnel == "carrier":
        from .carrier_leads import mark_carrier_response

        mark_carrier_response(lead, positive=positive)
    elif funnel == "lead_x":
        from .project_x.leads import mark_x_response

        mark_x_response(lead, positive=positive)
    else:
        from .leads import mark_response

        mark_response(lead, positive=positive)


def _lead_identity(lead: dict, funnel: str) -> str:
    if funnel == "carrier":
        from .carrier_storage import carrier_key

        return carrier_key(lead)
    if funnel == "lead_x":
        from .project_x.store import lead_key as xkey

        return xkey(lead)
    from .storage import lead_key as ship_key

    return ship_key(lead)


def _create_reply_task(lead: dict, funnel: str, msg: InboundMessage) -> str:
    try:
        from .lead_crm import create_task

        lid = _lead_identity(lead, funnel)
        due = datetime.now().date().isoformat()
        snippet = (msg.body or msg.subject or "")[:180].replace("\n", " ")
        task = create_task(
            lead_id=lid,
            title=f"Lead replied — {(lead.get('company_name') or lid)[:60]}",
            due_at=due,
            funnel=funnel,
            company_name=lead.get("company_name") or "",
            notes=f"From {msg.from_addr}\nSubject: {msg.subject}\n{snippet}",
            priority="high",
        )
        return str(task.get("id") or "")
    except Exception:
        return ""


def apply_matched_replies(
    messages: list[InboundMessage],
    *,
    lead_index: Optional[dict[str, tuple[dict, str]]] = None,
    seen_path: Optional[Path] = None,
    create_tasks: bool = True,
) -> InboxCheckResult:
    """
    Match From: to known lead emails; append conversation; set responded;
    create Dashboard task. Honors DNC (skip apply). Dedupes by Message-ID.
    """
    if lead_index is None:
        shipper, carrier, x_leads = _load_all_funnel_leads()
        lead_index = build_lead_email_index(
            shipper_leads=shipper, carrier_leads=carrier, x_leads=x_leads
        )

    seen = _load_seen_ids(seen_path)
    matches: list[MatchedReply] = []
    applied = skipped_dnc = skipped_dup = skipped_unknown = 0
    errors: list[str] = []

    # Own pool emails — never treat as lead replies
    own_addrs: set[str] = set()
    try:
        from .mailboxes import enabled_with_password

        for mb in enabled_with_password():
            e = _normalize_email(mb.get("email") or mb.get("smtp_user") or "")
            if e:
                own_addrs.add(e)
    except Exception:
        pass

    for msg in messages or []:
        from_addr = _normalize_email(msg.from_addr)
        if not from_addr or "@" not in from_addr:
            skipped_unknown += 1
            continue
        if from_addr in own_addrs:
            skipped_unknown += 1
            continue

        fp = _message_fingerprint(msg)
        if fp in seen:
            skipped_dup += 1
            matches.append(
                MatchedReply(
                    funnel="",
                    lead_email=from_addr,
                    company_name="",
                    lead_key="",
                    message=msg,
                    applied=False,
                    skipped_reason="duplicate",
                )
            )
            continue

        hit = lead_index.get(from_addr)
        if not hit:
            skipped_unknown += 1
            # Still remember so we don't re-scan forever for noise
            seen.add(fp)
            continue

        lead, funnel = hit
        lkey = _lead_identity(lead, funnel)

        if _lead_already_has_message(lead, fp):
            seen.add(fp)
            skipped_dup += 1
            matches.append(
                MatchedReply(
                    funnel=funnel,
                    lead_email=from_addr,
                    company_name=lead.get("company_name") or "",
                    lead_key=lkey,
                    message=msg,
                    applied=False,
                    skipped_reason="duplicate",
                )
            )
            continue

        if _is_dnc(lead):
            seen.add(fp)
            skipped_dnc += 1
            matches.append(
                MatchedReply(
                    funnel=funnel,
                    lead_email=from_addr,
                    company_name=lead.get("company_name") or "",
                    lead_key=lkey,
                    message=msg,
                    applied=False,
                    skipped_reason="dnc",
                )
            )
            continue

        try:
            conv = list(lead.get("conversation") or [])
            conv.append(
                {
                    "at": datetime.now().isoformat(),
                    "direction": "inbound",
                    "body": msg.body or "",
                    "subject": msg.subject or "",
                    "message_id": msg.message_id or "",
                    "imap_fp": fp,
                    "mailbox": msg.mailbox_email or "",
                    "source": "imap_poll",
                }
            )
            lead["conversation"] = conv
            rem = lead.get("remarks") or ""
            tag = "Reply:imap"
            if tag not in rem:
                lead["remarks"] = (rem + f" | {tag}").strip(" |")

            # Only flip to responded if not already converted
            status = (lead.get("status") or "").strip().lower()
            if status != "converted":
                _mark_responded(lead, funnel, positive=True)

            task_id = ""
            if create_tasks:
                task_id = _create_reply_task(lead, funnel, msg)

            _persist_funnel_lead(lead, funnel)
            seen.add(fp)
            applied += 1
            matches.append(
                MatchedReply(
                    funnel=funnel,
                    lead_email=from_addr,
                    company_name=lead.get("company_name") or "",
                    lead_key=lkey,
                    message=msg,
                    applied=True,
                    task_id=task_id,
                )
            )
        except Exception as e:
            errors.append(f"{from_addr}: {e}")
            matches.append(
                MatchedReply(
                    funnel=funnel,
                    lead_email=from_addr,
                    company_name=lead.get("company_name") or "",
                    lead_key=lkey,
                    message=msg,
                    applied=False,
                    skipped_reason="error",
                )
            )

    try:
        _save_seen_ids(seen, seen_path)
    except Exception as e:
        errors.append(f"save seen ids: {e}")

    empty_poll = PollResult(ok=True, enabled=True, messages=list(messages or []))
    return InboxCheckResult(
        poll=empty_poll,
        matches=matches,
        applied=applied,
        skipped_dnc=skipped_dnc,
        skipped_dup=skipped_dup,
        skipped_unknown=skipped_unknown,
        errors=errors,
    )


def check_inbox_for_replies(
    company: dict,
    *,
    mailboxes: Optional[list[dict]] = None,
    lookback: int = DEFAULT_LOOKBACK,
    imap_factory: Optional[ImapFactory] = None,
    force: bool = False,
    lead_index: Optional[dict[str, tuple[dict, str]]] = None,
    seen_path: Optional[Path] = None,
    create_tasks: bool = True,
) -> InboxCheckResult:
    """
    Poll activated Gmail pool + match From: to known lead emails across
    shipper / carrier / Lead-for-X. Append conversation, set responded,
    create Dashboard tasks.

    force=True: used by Dashboard button (works even when toggle is OFF).
    Auto-poll path: when imap_poll_enabled or Autopilot is on.
    """
    auto = should_auto_poll(company)
    if not force and not imap_poll_enabled(company) and not auto:
        return InboxCheckResult(
            poll=PollResult(ok=True, enabled=False, messages=[], errors=[]),
        )

    # Once we decide to poll, force so App Password pool is read even if
    # the Org toggle is still off (manual Check inbox / Autopilot).
    poll = poll_recent_inbox(
        company,
        mailboxes=mailboxes,
        lookback=lookback,
        imap_factory=imap_factory,
        force=True,
        prefer_unseen=True,
    )

    result = apply_matched_replies(
        poll.messages,
        lead_index=lead_index,
        seen_path=seen_path,
        create_tasks=create_tasks,
    )
    result.poll = poll
    result.errors = list(poll.errors) + list(result.errors)
    return result


def format_check_summary(result: InboxCheckResult) -> str:
    parts = [
        f"Matched & recorded {result.applied} reply(ies)",
        f"polled {result.poll.mailboxes_polled} mailbox(es)",
    ]
    if result.skipped_unknown:
        parts.append(f"{result.skipped_unknown} unknown From")
    if result.skipped_dup:
        parts.append(f"{result.skipped_dup} already seen")
    if result.skipped_dnc:
        parts.append(f"{result.skipped_dnc} DNC skipped")
    if result.errors:
        parts.append(f"{len(result.errors)} error(s)")
    return " · ".join(parts)


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
