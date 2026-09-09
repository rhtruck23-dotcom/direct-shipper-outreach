"""
Permanent carrier (owner-operator recruit) storage.

Local  -> data/carrier_leads_db.json
Cloud  -> Google Sheet worksheet "carrier_leads" (separate from shipper "leads")
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from .paths import DATA_DIR

CARRIER_JSON = DATA_DIR / "carrier_leads_db.json"

CARRIER_COLUMNS = [
    "id",
    "company_name",
    "contact_name",
    "email",
    "phone",
    "state",
    "county",
    "zip",
    "mc_number",
    "dot_number",
    "equipment_type",
    "cdl_class",
    "years_exp",
    "authority_date",
    "lane_or_region",
    "notes",
    "remarks",
    "source",
    "website",
    "status",
    "first_contacted",
    "last_emailed",
    "last_step_sent",
    "responded",
    "active_sequence",
    "contact_count",
    "assigned_to",
    "deal_stage",
    "conversation_json",
]


def _blank_carrier() -> dict[str, Any]:
    return {
        "id": "",
        "company_name": "",
        "contact_name": "",
        "email": "",
        "phone": "",
        "state": "",
        "county": "",
        "zip": "",
        "mc_number": "",
        "dot_number": "",
        "equipment_type": "",
        "cdl_class": "",
        "years_exp": "",
        "authority_date": "",
        "lane_or_region": "",
        "notes": "",
        "remarks": "",
        "source": "",
        "website": "",
        "status": "not_started",
        "first_contacted": None,
        "last_emailed": None,
        "last_step_sent": 0,
        "responded": False,
        "active_sequence": False,
        "contact_count": 0,
        "assigned_to": "",
        "deal_stage": "",
        "conversation": [],
    }


def carrier_key(lead: dict) -> str:
    email = (lead.get("email") or "").lower().strip()
    if email:
        return email
    mc = (lead.get("mc_number") or "").lower().replace("mc-", "").replace("mc", "").strip()
    if mc:
        return f"mc:{mc}"
    dot = (lead.get("dot_number") or "").lower().replace("dot-", "").replace("dot", "").strip()
    if dot:
        return f"dot:{dot}"
    return f"id:{(lead.get('id') or lead.get('company_name') or '').lower().strip()}"


def _normalize(raw: dict) -> dict:
    lead = _blank_carrier()
    for k in lead:
        if k in raw and raw[k] not in (None, ""):
            lead[k] = raw[k]
    if "conversation_json" in raw and raw["conversation_json"]:
        try:
            lead["conversation"] = json.loads(raw["conversation_json"])
        except Exception:
            lead["conversation"] = []
    if isinstance(lead.get("conversation"), str):
        try:
            lead["conversation"] = json.loads(lead["conversation"])
        except Exception:
            lead["conversation"] = []
    lead["last_step_sent"] = int(lead.get("last_step_sent") or 0)
    lead["contact_count"] = int(lead.get("contact_count") or 0)
    lead["responded"] = str(lead.get("responded")).lower() in ("1", "true", "yes")
    lead["active_sequence"] = str(lead.get("active_sequence")).lower() in (
        "1",
        "true",
        "yes",
    )
    if not lead.get("status"):
        lead["status"] = "not_started"
    lead["assigned_to"] = str(lead.get("assigned_to") or "").strip()
    lead["deal_stage"] = str(lead.get("deal_stage") or "").strip()
    # normalize MC/DOT display
    mc = str(lead.get("mc_number") or "").strip()
    if mc and not mc.upper().startswith("MC"):
        lead["mc_number"] = f"MC-{mc.replace('MC-', '').replace('MC', '')}"
    dot = str(lead.get("dot_number") or "").strip()
    if dot and not dot.upper().startswith("DOT"):
        lead["dot_number"] = f"DOT-{dot.replace('DOT-', '').replace('DOT', '')}"
    return lead


def _to_sheet_row(lead: dict) -> dict:
    row = {c: lead.get(c, "") for c in CARRIER_COLUMNS if c != "conversation_json"}
    row["conversation_json"] = json.dumps(lead.get("conversation") or [], ensure_ascii=False)
    row["responded"] = "true" if lead.get("responded") else "false"
    row["active_sequence"] = "true" if lead.get("active_sequence") else "false"
    row["last_step_sent"] = str(int(lead.get("last_step_sent") or 0))
    row["contact_count"] = str(int(lead.get("contact_count") or 0))
    for k in ("first_contacted", "last_emailed"):
        row[k] = lead.get(k) or ""
    return row


def _load_local() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CARRIER_JSON.exists():
        return []
    with open(CARRIER_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [_normalize(x) for x in data]


def _save_local(leads: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CARRIER_JSON, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)


def _using_cloud() -> bool:
    from . import storage

    return storage.using_cloud()


def _open_carrier_worksheet(*, create_if_missing: bool = False):
    import gspread
    from . import storage

    sh = storage._open_spreadsheet()
    try:
        return sh.worksheet("carrier_leads")
    except gspread.WorksheetNotFound:
        if not create_if_missing:
            raise
        ws = sh.add_worksheet(
            title="carrier_leads", rows=2000, cols=max(len(CARRIER_COLUMNS), 26)
        )
        ws.update("A1", [CARRIER_COLUMNS], value_input_option="USER_ENTERED")
        return ws


def _load_sheets() -> list[dict]:
    import gspread

    try:
        ws = _open_carrier_worksheet(create_if_missing=False)
    except gspread.WorksheetNotFound:
        return []
    values = ws.get_all_values()
    if not values or len(values) < 2:
        return []
    header = [str(h).strip() for h in values[0]]
    out: list[dict] = []
    for row in values[1:]:
        raw = {
            header[i]: (row[i] if i < len(row) else "")
            for i in range(len(header))
            if header[i]
        }
        if raw.get("company_name") or raw.get("email") or raw.get("mc_number"):
            out.append(_normalize(raw))
    return out


def _save_sheets(leads: list[dict]) -> None:
    ws = _open_carrier_worksheet(create_if_missing=True)
    values = [CARRIER_COLUMNS]
    for lead in leads:
        row = _to_sheet_row(lead)
        values.append([row.get(c, "") for c in CARRIER_COLUMNS])
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")


def load_all_carriers() -> list[dict]:
    if _using_cloud():
        return _load_sheets()
    return _load_local()


def save_all_carriers(leads: list[dict]) -> None:
    if _using_cloud():
        _save_sheets(leads)
    else:
        _save_local(leads)


def upsert_carriers(new_leads: list[dict]) -> tuple[int, int]:
    existing = load_all_carriers()
    by_key = {carrier_key(l): l for l in existing if carrier_key(l)}
    added = updated = 0
    protected = {
        "status",
        "first_contacted",
        "last_emailed",
        "last_step_sent",
        "responded",
        "active_sequence",
        "contact_count",
        "conversation",
        "remarks",
        "assigned_to",
    }

    for raw in new_leads:
        incoming = _normalize(raw)
        if not (
            (incoming.get("email") or "").strip()
            or (incoming.get("company_name") or "").strip()
            or (incoming.get("mc_number") or "").strip()
        ):
            continue
        if not incoming.get("id"):
            incoming["id"] = f"C{datetime.now().strftime('%Y%m%d%H%M%S')}{added + updated}"
        key = carrier_key(incoming)
        if not key or key == "id:":
            continue
        if key in by_key:
            old = by_key[key]
            for field, val in incoming.items():
                if field in protected:
                    continue
                if val not in (None, ""):
                    old[field] = val
            if old.get("status") == "do_not_contact":
                old["active_sequence"] = False
            by_key[key] = old
            updated += 1
        else:
            by_key[key] = incoming
            added += 1

    save_all_carriers(list(by_key.values()))
    return added, updated


def update_carrier(updated: dict) -> None:
    leads = load_all_carriers()
    key = carrier_key(updated)
    out = []
    found = False
    for l in leads:
        if carrier_key(l) == key:
            out.append(_normalize({**l, **updated}))
            found = True
        else:
            out.append(l)
    if not found:
        out.append(_normalize(updated))
    save_all_carriers(out)


def bump_carrier_contact(lead: dict, step: int) -> None:
    today = datetime.now().isoformat()
    if not lead.get("first_contacted"):
        lead["first_contacted"] = today
    lead["last_emailed"] = today
    lead["last_step_sent"] = step
    lead["status"] = f"emailed_{step}"
    lead["contact_count"] = int(lead.get("contact_count") or 0) + 1
