"""Lead helpers — filters, CSV import, activate — backed by permanent storage."""
from __future__ import annotations

import csv
from typing import Optional

from .stages import may_start_outreach
from .storage import (
    lead_key,
    load_all_leads,
    save_all_leads,
    upsert_leads,
    update_lead,
)

# Re-export for callers
__all__ = [
    "lead_key",
    "load_leads",
    "save_leads",
    "upsert_leads",
    "update_lead",
    "filter_leads",
    "activate_sequence",
    "mark_response",
    "mark_converted",
    "parse_import_csv",
    "persist_lead_tracking",
    "set_remarks",
]


def load_leads() -> list[dict]:
    return load_all_leads()


def save_leads(leads: list[dict]) -> None:
    save_all_leads(leads)


def persist_lead_tracking(leads: list[dict]) -> None:
    """Full save — cloud or local."""
    save_all_leads(leads)


def filter_leads(
    leads: list[dict],
    state: Optional[str] = None,
    county: Optional[str] = None,
    zip_prefix: Optional[str] = None,
    freight_type: Optional[str] = None,
    status: Optional[str] = None,
    active_only: bool = False,
    hide_dnc: bool = False,
) -> list[dict]:
    out = leads
    if state:
        out = [l for l in out if (l.get("state") or "").lower() == state.lower()]
    if county:
        out = [l for l in out if (l.get("county") or "").lower() == county.lower()]
    if zip_prefix:
        out = [l for l in out if (l.get("zip") or "").startswith(zip_prefix)]
    if freight_type:
        out = [
            l
            for l in out
            if (l.get("freight_type") or "").lower() == freight_type.lower()
        ]
    if status:
        out = [l for l in out if (l.get("status") or "") == status]
    if active_only:
        out = [l for l in out if l.get("active_sequence")]
    if hide_dnc:
        out = [l for l in out if (l.get("status") or "") != "do_not_contact"]
    return out


def activate_sequence(
    leads: list[dict], selected_keys: list[str], force: bool = False
) -> tuple[int, list[str]]:
    """Activate outreach. Skips DNC / already-contacted unless force=True."""
    count = 0
    skipped: list[str] = []
    keyset = set(k.lower() for k in selected_keys)
    for lead in leads:
        if lead_key(lead) not in keyset:
            continue
        ok, reason = may_start_outreach(lead, force=force)
        if not ok and not (force and lead.get("status") != "do_not_contact"):
            # force still cannot override DNC
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
            # restart sequence but keep history in conversation/remarks
            lead["status"] = "not_started"
            lead["last_step_sent"] = 0
            lead["active_sequence"] = True
            # keep first_contacted for audit — add remark
            prev = lead.get("remarks") or ""
            lead["remarks"] = (prev + " | Sequence restarted").strip(" |")
            count += 1
            continue
        lead["active_sequence"] = True
        count += 1
    save_all_leads(leads)
    return count, skipped


def mark_response(lead: dict, positive: bool = True) -> None:
    lead["responded"] = True
    lead["active_sequence"] = False
    lead["status"] = "responded" if positive else "do_not_contact"
    if not positive:
        note = lead.get("remarks") or ""
        if "STOP / DNC" not in note:
            lead["remarks"] = (note + " | STOP / DNC").strip(" |")


def mark_converted(lead: dict) -> None:
    lead["status"] = "converted"
    lead["active_sequence"] = False
    lead["responded"] = True
    note = lead.get("remarks") or ""
    if "Converted" not in note:
        lead["remarks"] = (note + " | Converted direct customer").strip(" |")


def set_remarks(lead: dict, remarks: str) -> None:
    lead["remarks"] = remarks


def parse_import_csv(file_bytes: bytes) -> list[dict]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    reader = csv.DictReader(lines)
    if not reader.fieldnames:
        return []
    aliases = {
        "company": "company_name",
        "company name": "company_name",
        "name": "contact_name",
        "contact": "contact_name",
        "contact name": "contact_name",
        "e-mail": "email",
        "email address": "email",
        "telephone": "phone",
        "tel": "phone",
        "st": "state",
        "postal": "zip",
        "zipcode": "zip",
        "zip code": "zip",
        "freight": "freight_type",
        "equipment": "freight_type",
        "lane": "lane_or_region",
        "region": "lane_or_region",
        "url": "website",
        "web": "website",
        "remark": "remarks",
        "remarks": "remarks",
        "note": "notes",
        "notes": "notes",
    }
    header_fields = [
        "id",
        "company_name",
        "contact_name",
        "email",
        "phone",
        "state",
        "county",
        "zip",
        "freight_type",
        "lane_or_region",
        "notes",
        "remarks",
        "source",
        "website",
    ]
    out = []
    for row in reader:
        mapped = {h: "" for h in header_fields}
        for raw_key, val in row.items():
            if raw_key is None:
                continue
            key = raw_key.strip().lower()
            canon = aliases.get(key, key.replace(" ", "_"))
            if canon in mapped:
                mapped[canon] = (val or "").strip()
        if mapped.get("company_name") or mapped.get("email"):
            mapped["source"] = mapped.get("source") or "csv_import"
            out.append(mapped)
    return out
