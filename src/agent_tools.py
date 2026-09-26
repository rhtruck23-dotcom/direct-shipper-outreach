"""
Agent tool layer — structured JSON actions the LLM/autonomy runner can invoke.

Tools:
  update_lead_fields, append_note, create_task, send_email,
  set_active_sequence, schedule_followup, escalate_to_owner

Safety:
  - Never email do_not_contact / crm dnc
  - Respect send_live_emails (dry-run still "sends" via emailer)
  - Soft daily email cap
  - Escalate rate/contract/legal keywords to owner
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from .bot import ESCALATE_PATTERNS
from .crm_picklists import (
    normalize_crm_status,
    normalize_priority,
    normalize_sales_stage,
)
from .lead_crm import (
    append_note as crm_append_note,
    create_task as crm_create_task,
    lead_stable_id,
    send_one_off_email,
)
from .llm import extract_json_object
from .notify import notify_owner
from .paths import OUTBOUND_LOG

ALLOWED_ACTIONS = (
    "update_lead_fields",
    "append_note",
    "create_task",
    "send_email",
    "set_active_sequence",
    "schedule_followup",
    "escalate_to_owner",
    "noop",
)

DEFAULT_DAILY_EMAIL_CAP = 50

# Extra high-stakes phrases beyond bot escalate patterns
_EXTRA_ESCALATE = (
    r"\blegal\b",
    r"\battorney\b",
    r"\blawsuit\b",
    r"\bliability\b",
    r"\bindemnif",
    r"\bnda\b",
)


@dataclass
class ToolResult:
    ok: bool
    action: str
    message: str = ""
    data: dict = field(default_factory=dict)
    skipped: bool = False
    escalated: bool = False


LeadResolver = Callable[[str], Optional[tuple[dict, str]]]
# returns (lead, funnel) or None
LeadPersister = Callable[[dict, str], None]


def is_dnc(lead: dict) -> bool:
    status = (lead.get("status") or "").strip().lower()
    crm = normalize_crm_status(lead.get("crm_status"))
    return status == "do_not_contact" or crm == "dnc"


def is_converted(lead: dict) -> bool:
    status = (lead.get("status") or "").strip().lower()
    crm = normalize_crm_status(lead.get("crm_status"))
    stage = normalize_sales_stage(lead.get("sales_stage"))
    return status == "converted" or crm == "converted" or stage == "converted"


def text_needs_escalation(text: str) -> bool:
    t = (text or "").lower()
    for pat in ESCALATE_PATTERNS:
        if re.search(pat, t):
            return True
    for pat in _EXTRA_ESCALATE:
        if re.search(pat, t):
            return True
    return False


def emails_sent_today(*, today: Optional[date] = None) -> int:
    """Count outbound log entries for today (live + dry_run)."""
    today = today or date.today()
    day = today.isoformat()
    if not OUTBOUND_LOG.exists():
        return 0
    try:
        with open(OUTBOUND_LOG, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return 0
    n = 0
    for entry in log or []:
        at = str(entry.get("at") or "")
        if at.startswith(day):
            n += 1
    return n


def under_daily_email_cap(
    company: Optional[dict] = None,
    *,
    today: Optional[date] = None,
) -> tuple[bool, int, int]:
    """Return (ok_to_send, sent_today, cap)."""
    cap = int((company or {}).get("autonomy_daily_email_cap") or DEFAULT_DAILY_EMAIL_CAP)
    if cap <= 0:
        cap = DEFAULT_DAILY_EMAIL_CAP
    sent = emails_sent_today(today=today)
    return sent < cap, sent, cap


def parse_action_json(text: str) -> Optional[dict[str, Any]]:
    """
    Parse agent action JSON. Accepts:
      {"action":"...", ...}
      {"actions":[{...}, ...]}  → returns first action (batch handled elsewhere)
    """
    data = extract_json_object(text or "")
    if not data:
        return None
    if "actions" in data and isinstance(data["actions"], list) and data["actions"]:
        first = data["actions"][0]
        if isinstance(first, dict):
            # Preserve reasoning from wrapper
            if data.get("reasoning") and not first.get("reasoning"):
                first = {**first, "reasoning": data.get("reasoning")}
            return first
    action = (data.get("action") or data.get("tool") or "").strip()
    if action:
        return data
    return None


def parse_actions_json(text: str) -> list[dict[str, Any]]:
    data = extract_json_object(text or "")
    if not data:
        return []
    if "actions" in data and isinstance(data["actions"], list):
        out = [a for a in data["actions"] if isinstance(a, dict) and (a.get("action") or a.get("tool"))]
        return out
    if data.get("action") or data.get("tool"):
        return [data]
    return []


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve_lead_key(lead: dict, funnel: str) -> str:
    return lead_stable_id(lead, funnel=funnel) or (lead.get("email") or "").lower().strip()


def update_lead_fields(
    lead: dict,
    *,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    priority: Optional[str] = None,
    next_contact_at: Optional[str] = None,
    crm_status: Optional[str] = None,
) -> ToolResult:
    """Update CRM / workflow fields on an in-memory lead."""
    if is_dnc(lead) and (status or crm_status):
        # Allow setting DNC; block other status changes away from DNC? Allow updates.
        pass
    changed = []
    if status is not None and str(status).strip():
        s = str(status).strip().lower()
        # Sequence status OR crm — map common CRM values
        if s in ("do_not_contact", "dnc"):
            lead["status"] = "do_not_contact"
            lead["crm_status"] = "dnc"
            lead["active_sequence"] = False
            changed.append("status=dnc")
        elif s in ("converted", "won"):
            lead["status"] = "converted"
            lead["crm_status"] = "converted"
            lead["sales_stage"] = "converted"
            lead["active_sequence"] = False
            changed.append("status=converted")
        elif s in ("responded", "not_started") or s.startswith("emailed_"):
            lead["status"] = s
            changed.append(f"status={s}")
        else:
            lead["crm_status"] = normalize_crm_status(s)
            changed.append(f"crm_status={lead['crm_status']}")
    if crm_status is not None and str(crm_status).strip():
        lead["crm_status"] = normalize_crm_status(crm_status)
        if lead["crm_status"] == "dnc":
            lead["status"] = "do_not_contact"
            lead["active_sequence"] = False
        changed.append(f"crm_status={lead['crm_status']}")
    if stage is not None and str(stage).strip():
        lead["sales_stage"] = normalize_sales_stage(stage)
        changed.append(f"stage={lead['sales_stage']}")
    if priority is not None and str(priority).strip():
        lead["priority"] = normalize_priority(priority)
        changed.append(f"priority={lead['priority']}")
    if next_contact_at is not None:
        lead["next_contact_at"] = str(next_contact_at or "").strip()
        changed.append("next_contact_at")
    return ToolResult(
        ok=True,
        action="update_lead_fields",
        message="Updated: " + (", ".join(changed) if changed else "no-op"),
        data={"changed": changed},
    )


def tool_append_note(lead: dict, text: str, *, author: str = "agent") -> ToolResult:
    body = (text or "").strip()
    if not body:
        return ToolResult(ok=False, action="append_note", message="empty note")
    crm_append_note(lead, body, author=author)
    return ToolResult(ok=True, action="append_note", message="note appended")


def tool_create_task(
    lead: dict,
    title: str,
    due_at: str,
    *,
    funnel: str = "shipper",
) -> ToolResult:
    title = (title or "").strip()
    if not title:
        return ToolResult(ok=False, action="create_task", message="title required")
    due = (due_at or "").strip()
    if not due:
        due = (datetime.now() + timedelta(days=1)).replace(microsecond=0).isoformat(timespec="minutes")
    lid = _resolve_lead_key(lead, funnel)
    if not (lead.get("id") or "").strip():
        lead["id"] = lid
    task = crm_create_task(
        lead_id=lid,
        title=title,
        due_at=due,
        funnel=funnel,
        company_name=lead.get("company_name") or "",
    )
    return ToolResult(
        ok=True,
        action="create_task",
        message=f"task {task.get('id')} created",
        data={"task_id": task.get("id"), "due_at": due},
    )


def tool_send_email(
    lead: dict,
    company: dict,
    *,
    subject: str,
    body: str,
    funnel: str = "shipper",
) -> ToolResult:
    if is_dnc(lead):
        return ToolResult(
            ok=False,
            action="send_email",
            message="blocked: do_not_contact",
            skipped=True,
        )
    if is_converted(lead):
        return ToolResult(
            ok=False,
            action="send_email",
            message="skipped: converted",
            skipped=True,
        )
    if not (lead.get("email") or "").strip():
        return ToolResult(ok=False, action="send_email", message="no email on lead")
    subj = (subject or "").strip()
    bod = (body or "").strip()
    if not subj or not bod:
        return ToolResult(ok=False, action="send_email", message="subject and body required")
    # High-stakes content in draft → escalate instead of send
    if text_needs_escalation(subj + "\n" + bod):
        return tool_escalate_to_owner(
            lead,
            company,
            reason="Agent draft contained rate/contract/legal language — human must send.",
            funnel=funnel,
        )
    ok_cap, sent, cap = under_daily_email_cap(company)
    if not ok_cap:
        return ToolResult(
            ok=False,
            action="send_email",
            message=f"daily email cap reached ({sent}/{cap})",
            skipped=True,
            data={"sent_today": sent, "cap": cap},
        )
    result = send_one_off_email(
        lead, company, subject=subj, body=bod, funnel=funnel
    )
    mode = result.get("mode") or ("live" if company.get("send_live_emails") else "dry_run")
    return ToolResult(
        ok=bool(result.get("ok")),
        action="send_email",
        message=f"email {mode}" + (f": {result.get('error')}" if result.get("error") else ""),
        data={"mode": mode, "live": bool(company.get("send_live_emails"))},
    )


def tool_set_active_sequence(
    lead: dict,
    active: bool = True,
) -> ToolResult:
    if is_dnc(lead):
        return ToolResult(
            ok=False,
            action="set_active_sequence",
            message="blocked: do_not_contact",
            skipped=True,
        )
    if is_converted(lead) and active:
        return ToolResult(
            ok=False,
            action="set_active_sequence",
            message="skipped: converted",
            skipped=True,
        )
    lead["active_sequence"] = bool(active)
    return ToolResult(
        ok=True,
        action="set_active_sequence",
        message=f"active_sequence={bool(active)}",
        data={"active_sequence": bool(active)},
    )


def tool_schedule_followup(
    lead: dict,
    *,
    due_at: str = "",
    days: int = 3,
    title: str = "Follow up",
    funnel: str = "shipper",
) -> ToolResult:
    if due_at and str(due_at).strip():
        when = str(due_at).strip()
    else:
        when = (datetime.now() + timedelta(days=max(0, int(days)))).replace(
            microsecond=0
        ).isoformat(timespec="minutes")
    lead["next_contact_at"] = when
    tr = tool_create_task(lead, title or "Follow up", when, funnel=funnel)
    return ToolResult(
        ok=tr.ok,
        action="schedule_followup",
        message=f"next_contact_at={when}; {tr.message}",
        data={"next_contact_at": when, "task": tr.data},
    )


def tool_escalate_to_owner(
    lead: dict,
    company: dict,
    *,
    reason: str,
    funnel: str = "shipper",
) -> ToolResult:
    reason = (reason or "Agent escalation").strip()
    co = lead.get("company_name") or "?"
    email = lead.get("email") or ""
    alert = (
        f"AGENT ESCALATE [{funnel}]: {co} ({email})\n"
        f"Reason: {reason}\n"
        f"CRM: {lead.get('crm_status')} · stage {lead.get('sales_stage')} · "
        f"priority {lead.get('priority')}"
    )
    notify_owner(company, f"Agent escalate: {co}", alert)
    crm_append_note(lead, f"[ESCALATE] {reason}", author="agent")
    # Pause sequence so human owns the thread
    lead["active_sequence"] = False
    if normalize_crm_status(lead.get("crm_status")) not in ("dnc", "converted"):
        lead["crm_status"] = normalize_crm_status("waiting_reply")
    return ToolResult(
        ok=True,
        action="escalate_to_owner",
        message="escalated to owner",
        escalated=True,
        data={"reason": reason},
    )


def execute_action(
    action: dict,
    *,
    lead: dict,
    company: dict,
    funnel: str = "shipper",
) -> ToolResult:
    """Dispatch a single structured action against a lead."""
    name = (action.get("action") or action.get("tool") or "").strip().lower()
    if name not in ALLOWED_ACTIONS:
        return ToolResult(ok=False, action=name or "unknown", message=f"unknown action: {name}")

    if name == "noop":
        return ToolResult(ok=True, action="noop", message=action.get("reasoning") or "noop")

    if name == "update_lead_fields":
        return update_lead_fields(
            lead,
            status=action.get("status"),
            stage=action.get("stage") or action.get("sales_stage"),
            priority=action.get("priority"),
            next_contact_at=action.get("next_contact_at"),
            crm_status=action.get("crm_status"),
        )
    if name == "append_note":
        return tool_append_note(lead, action.get("text") or action.get("note") or "")
    if name == "create_task":
        return tool_create_task(
            lead,
            action.get("title") or "",
            action.get("due_at") or "",
            funnel=funnel,
        )
    if name == "send_email":
        return tool_send_email(
            lead,
            company,
            subject=action.get("subject") or "",
            body=action.get("body") or "",
            funnel=funnel,
        )
    if name == "set_active_sequence":
        active = action.get("active")
        if active is None:
            active = action.get("active_sequence", True)
        return tool_set_active_sequence(lead, bool(active))
    if name == "schedule_followup":
        return tool_schedule_followup(
            lead,
            due_at=action.get("due_at") or "",
            days=int(action.get("days") or 3),
            title=action.get("title") or "Follow up",
            funnel=funnel,
        )
    if name == "escalate_to_owner":
        return tool_escalate_to_owner(
            lead,
            company,
            reason=action.get("reason") or action.get("text") or "escalation",
            funnel=funnel,
        )
    return ToolResult(ok=False, action=name, message="unhandled")
