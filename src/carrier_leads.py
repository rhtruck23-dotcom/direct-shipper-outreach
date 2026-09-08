"""Carrier lead helpers — filters, activate, status — backed by carrier storage."""
from __future__ import annotations

from typing import Optional

from .stages import may_start_outreach
from .carrier_storage import (
    carrier_key,
    load_all_carriers,
    save_all_carriers,
    update_carrier,
    upsert_carriers,
)

__all__ = [
    "carrier_key",
    "load_carriers",
    "save_carriers",
    "upsert_carriers",
    "update_carrier",
    "filter_carriers",
    "activate_carrier_sequence",
    "mark_carrier_response",
    "mark_carrier_hired",
    "persist_carriers",
]


def load_carriers() -> list[dict]:
    return load_all_carriers()


def save_carriers(leads: list[dict]) -> None:
    save_all_carriers(leads)


def persist_carriers(leads: list[dict]) -> None:
    save_all_carriers(leads)


def filter_carriers(
    leads: list[dict],
    state: Optional[str] = None,
    zip_prefix: Optional[str] = None,
    equipment_type: Optional[str] = None,
    status: Optional[str] = None,
    active_only: bool = False,
    hide_dnc: bool = False,
) -> list[dict]:
    out = leads
    if state:
        out = [l for l in out if (l.get("state") or "").lower() == state.lower()]
    if zip_prefix:
        out = [l for l in out if (l.get("zip") or "").startswith(zip_prefix)]
    if equipment_type:
        out = [
            l
            for l in out
            if equipment_type.lower() in (l.get("equipment_type") or "").lower()
        ]
    if status:
        out = [l for l in out if (l.get("status") or "") == status]
    if active_only:
        out = [l for l in out if l.get("active_sequence")]
    if hide_dnc:
        out = [l for l in out if (l.get("status") or "") != "do_not_contact"]
    return out


def activate_carrier_sequence(
    leads: list[dict], selected_keys: list[str], force: bool = False
) -> tuple[int, list[str]]:
    count = 0
    skipped: list[str] = []
    keyset = set(k.lower() for k in selected_keys)
    for lead in leads:
        if carrier_key(lead) not in keyset:
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
    save_all_carriers(leads)
    return count, skipped


def mark_carrier_response(lead: dict, positive: bool = True) -> None:
    lead["responded"] = True
    lead["active_sequence"] = False
    lead["status"] = "responded" if positive else "do_not_contact"
    if not positive:
        note = lead.get("remarks") or ""
        if "STOP / DNC" not in note:
            lead["remarks"] = (note + " | STOP / DNC").strip(" |")


def mark_carrier_hired(lead: dict) -> None:
    lead["status"] = "converted"
    lead["active_sequence"] = False
    lead["responded"] = True
    note = lead.get("remarks") or ""
    if "Hired under MC" not in note:
        lead["remarks"] = (note + " | Hired under LogixTrek MC").strip(" |")
