"""Standard CRM picklists + normalization (sales stage / status / priority)."""
from __future__ import annotations

from typing import Optional

# Sales funnel stages (CRM) — distinct from email-sequence `status`
SALES_STAGES = (
    "new",
    "contacted",
    "engaged",
    "qualified",
    "proposal",
    "negotiation",
    "converted",
    "lost",
)

SALES_STAGE_LABELS = {
    "new": "New",
    "contacted": "Contacted",
    "engaged": "Engaged",
    "qualified": "Qualified",
    "proposal": "Proposal",
    "negotiation": "Negotiation",
    "converted": "Converted",
    "lost": "Lost",
}

# CRM workflow status — distinct from email-sequence `status`
CRM_STATUSES = (
    "open",
    "waiting_reply",
    "nurture",
    "on_hold",
    "converted",
    "dnc",
)

CRM_STATUS_LABELS = {
    "open": "Open",
    "waiting_reply": "Waiting reply",
    "nurture": "Nurture",
    "on_hold": "On hold",
    "converted": "Converted",
    "dnc": "Do not contact",
}

PRIORITIES = ("low", "medium", "high", "urgent")

PRIORITY_LABELS = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "urgent": "Urgent",
}

# Aliases people might type / migrate from email sequence status
_STAGE_ALIASES = {
    "not_started": "new",
    "emailed_1": "contacted",
    "emailed_2": "contacted",
    "emailed_3": "engaged",
    "emailed_4": "engaged",
    "responded": "engaged",
    "do_not_contact": "lost",
    "closed": "lost",
    "won": "converted",
    "customer": "converted",
}

_STATUS_ALIASES = {
    "not_started": "open",
    "active": "open",
    "waiting": "waiting_reply",
    "wait": "waiting_reply",
    "hold": "on_hold",
    "paused": "on_hold",
    "do_not_contact": "dnc",
    "donotcontact": "dnc",
    "won": "converted",
}

_PRIORITY_ALIASES = {
    "med": "medium",
    "mid": "medium",
    "normal": "medium",
    "crit": "urgent",
    "critical": "urgent",
    "p0": "urgent",
    "p1": "high",
    "p2": "medium",
    "p3": "low",
}


def _slug(value: Optional[str]) -> str:
    s = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s


def normalize_sales_stage(value: Optional[str], *, default: str = "new") -> str:
    s = _slug(value)
    if not s:
        return default
    if s in SALES_STAGES:
        return s
    mapped = _STAGE_ALIASES.get(s)
    if mapped in SALES_STAGES:
        return mapped
    return default


def normalize_crm_status(value: Optional[str], *, default: str = "open") -> str:
    s = _slug(value)
    if not s:
        return default
    if s in CRM_STATUSES:
        return s
    mapped = _STATUS_ALIASES.get(s)
    if mapped in CRM_STATUSES:
        return mapped
    return default


def normalize_priority(value: Optional[str], *, default: str = "medium") -> str:
    s = _slug(value)
    if not s:
        return default
    if s in PRIORITIES:
        return s
    mapped = _PRIORITY_ALIASES.get(s)
    if mapped in PRIORITIES:
        return mapped
    return default


def sales_stage_label(stage: Optional[str]) -> str:
    s = normalize_sales_stage(stage)
    return SALES_STAGE_LABELS.get(s, s)


def crm_status_label(status: Optional[str]) -> str:
    s = normalize_crm_status(status)
    return CRM_STATUS_LABELS.get(s, s)


def priority_label(priority: Optional[str]) -> str:
    p = normalize_priority(priority)
    return PRIORITY_LABELS.get(p, p)


def apply_crm_defaults(lead: dict) -> dict:
    """Ensure CRM fields exist on a lead dict without wiping other keys."""
    lead["sales_stage"] = normalize_sales_stage(lead.get("sales_stage"))
    lead["crm_status"] = normalize_crm_status(lead.get("crm_status"))
    lead["priority"] = normalize_priority(lead.get("priority"))
    if lead.get("next_contact_at") in (None,):
        lead["next_contact_at"] = ""
    else:
        lead["next_contact_at"] = str(lead.get("next_contact_at") or "").strip()
    tl = lead.get("notes_timeline")
    if not isinstance(tl, list):
        lead["notes_timeline"] = []
    return lead
