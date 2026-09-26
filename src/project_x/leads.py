"""Lead-for-X lead helpers — filter, activate, status — scoped by project_id."""
from __future__ import annotations

from typing import Optional

from ..stages import may_start_outreach
from .store import (
    lead_key,
    load_all_x_leads,
    load_leads_for_project,
    save_all_x_leads,
    update_x_lead,
    upsert_leads_for_project,
)

__all__ = [
    "lead_key",
    "load_x_leads",
    "save_x_leads",
    "upsert_x_leads",
    "update_x_lead",
    "filter_x_leads",
    "activate_x_sequence",
    "mark_x_response",
    "mark_x_converted",
    "persist_x_leads",
]


def load_x_leads(project_id: str = "") -> list[dict]:
    if project_id:
        return load_leads_for_project(project_id)
    return load_all_x_leads()


def save_x_leads(leads: list[dict]) -> None:
    save_all_x_leads(leads)


def persist_x_leads(leads: list[dict]) -> None:
    save_all_x_leads(leads)


def upsert_x_leads(project_id: str, new_leads: list[dict]) -> tuple[int, int]:
    return upsert_leads_for_project(project_id, new_leads)


def filter_x_leads(
    leads: list[dict],
    *,
    project_id: Optional[str] = None,
    state: Optional[str] = None,
    status: Optional[str] = None,
    active_only: bool = False,
    hide_dnc: bool = False,
    q: Optional[str] = None,
) -> list[dict]:
    out = leads
    if project_id:
        out = [l for l in out if (l.get("project_id") or "") == project_id]
    if state:
        out = [l for l in out if (l.get("state") or "").lower() == state.lower()]
    if status:
        out = [l for l in out if (l.get("status") or "") == status]
    if active_only:
        out = [l for l in out if l.get("active_sequence")]
    if hide_dnc:
        out = [l for l in out if (l.get("status") or "") != "do_not_contact"]
    if q:
        needle = q.lower().strip()
        out = [
            l
            for l in out
            if needle
            in " ".join(
                [
                    str(l.get("company_name") or ""),
                    str(l.get("contact_name") or ""),
                    str(l.get("email") or ""),
                    str(l.get("remarks") or ""),
                ]
            ).lower()
        ]
    return out


def activate_x_sequence(
    leads: list[dict], selected_keys: list[str], force: bool = False
) -> tuple[int, list[str]]:
    count = 0
    skipped: list[str] = []
    keyset = set(k.lower() for k in selected_keys)
    for lead in leads:
        if lead_key(lead).lower() not in keyset:
            continue
        ok, reason = may_start_outreach(lead, force=force)
        if not ok and not (force and lead.get("status") != "do_not_contact"):
            if lead.get("status") == "do_not_contact":
                skipped.append(f"{lead.get('company_name')}: {reason}")
                continue
            if not force:
                skipped.append(f"{lead.get('company_name')}: {reason}")
                continue
        if lead.get("status") == "do_not_contact":
            skipped.append(f"{lead.get('company_name')}: Do Not Contact — locked")
            continue
        if force and lead.get("status") not in ("do_not_contact", "converted"):
            lead["status"] = "not_started"
            lead["last_step_sent"] = 0
            lead["active_sequence"] = True
            prev = lead.get("remarks") or ""
            lead["remarks"] = (prev + " | Sequence restarted").strip(" |")
            count += 1
            continue
        lead["active_sequence"] = True
        count += 1
    save_all_x_leads(leads)
    return count, skipped


def mark_x_response(lead: dict, positive: bool = True) -> None:
    lead["responded"] = True
    lead["active_sequence"] = False
    lead["status"] = "responded" if positive else "do_not_contact"
    if not positive:
        note = lead.get("remarks") or ""
        if "STOP / DNC" not in note:
            lead["remarks"] = (note + " | STOP / DNC").strip(" |")


def mark_x_converted(lead: dict) -> None:
    lead["status"] = "converted"
    lead["active_sequence"] = False
    lead["responded"] = True
    note = lead.get("remarks") or ""
    if "Converted" not in note:
        lead["remarks"] = (note + " | Converted").strip(" |")
