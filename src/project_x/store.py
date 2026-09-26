"""
Lead-for-X persistence — projects + leads.

Local  -> data/x_projects.json, data/x_leads.json, data/x_active.json
Cloud  -> Google Sheet worksheets x_projects, x_leads (same workbook as shippers)
"""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Optional

from ..paths import DATA_DIR
from .templates import default_templates_for_scope

PROJECTS_JSON = DATA_DIR / "x_projects.json"
LEADS_JSON = DATA_DIR / "x_leads.json"
ACTIVE_JSON = DATA_DIR / "x_active.json"

PROJECT_TYPES = ("buyer", "seller", "other")

PROJECT_COLUMNS = [
    "id",
    "name",
    "project_type",
    "scope",
    "tone_notes",
    "status",
    "cadence_json",
    "templates_json",
    "created_at",
    "updated_at",
]

LEAD_COLUMNS = [
    "id",
    "project_id",
    "company_name",
    "contact_name",
    "email",
    "phone",
    "state",
    "county",
    "zip",
    "role_or_title",
    "lane_or_region",
    "notes",
    "remarks",
    "reasoning",
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
    "conversation_json",
]

DEFAULT_CADENCE = {1: 0, 2: 4, 3: 9, 4: 16}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _using_cloud() -> bool:
    from .. import storage

    return storage.using_cloud()


def _blank_project() -> dict[str, Any]:
    return {
        "id": "",
        "name": "",
        "project_type": "buyer",
        "scope": "",
        "tone_notes": "",
        "status": "active",
        "cadence": dict(DEFAULT_CADENCE),
        "templates": {},
        "created_at": "",
        "updated_at": "",
    }


def _blank_lead() -> dict[str, Any]:
    return {
        "id": "",
        "project_id": "",
        "company_name": "",
        "contact_name": "",
        "email": "",
        "phone": "",
        "state": "",
        "county": "",
        "zip": "",
        "role_or_title": "",
        "lane_or_region": "",
        "notes": "",
        "remarks": "",
        "reasoning": "",
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
        "conversation": [],
    }


def lead_key(lead: dict) -> str:
    email = (lead.get("email") or "").lower().strip()
    pid = (lead.get("project_id") or "").strip()
    if email:
        return f"{pid}:{email}" if pid else email
    company = (lead.get("company_name") or lead.get("id") or "").lower().strip()
    return f"{pid}:id:{company}" if pid else f"id:{company}"


def _normalize_project(raw: dict) -> dict:
    p = _blank_project()
    for k in p:
        if k in raw and raw[k] not in (None, ""):
            p[k] = raw[k]
    if "cadence_json" in raw and raw["cadence_json"]:
        try:
            p["cadence"] = {int(k): int(v) for k, v in json.loads(raw["cadence_json"]).items()}
        except Exception:
            p["cadence"] = dict(DEFAULT_CADENCE)
    if "templates_json" in raw and raw["templates_json"]:
        try:
            tmpl = json.loads(raw["templates_json"])
            p["templates"] = {int(k): v for k, v in tmpl.items()}
        except Exception:
            p["templates"] = {}
    if isinstance(p.get("cadence"), str):
        try:
            p["cadence"] = {int(k): int(v) for k, v in json.loads(p["cadence"]).items()}
        except Exception:
            p["cadence"] = dict(DEFAULT_CADENCE)
    if not isinstance(p.get("cadence"), dict) or not p["cadence"]:
        p["cadence"] = dict(DEFAULT_CADENCE)
    else:
        p["cadence"] = {int(k): int(v) for k, v in p["cadence"].items()}
    if isinstance(p.get("templates"), str):
        try:
            tmpl = json.loads(p["templates"])
            p["templates"] = {int(k): v for k, v in tmpl.items()}
        except Exception:
            p["templates"] = {}
    if not isinstance(p.get("templates"), dict):
        p["templates"] = {}
    else:
        p["templates"] = {int(k): v for k, v in p["templates"].items()}
    ptype = str(p.get("project_type") or "buyer").lower().strip()
    p["project_type"] = ptype if ptype in PROJECT_TYPES else "other"
    if not p.get("status"):
        p["status"] = "active"
    return p


def _normalize_lead(raw: dict) -> dict:
    lead = _blank_lead()
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
    lead["project_id"] = str(lead.get("project_id") or "").strip()
    lead["reasoning"] = str(lead.get("reasoning") or "")
    return lead


def _project_to_sheet_row(p: dict) -> dict:
    row = {c: p.get(c, "") for c in PROJECT_COLUMNS if c not in ("cadence_json", "templates_json")}
    row["cadence_json"] = json.dumps(
        {str(k): v for k, v in (p.get("cadence") or DEFAULT_CADENCE).items()},
        ensure_ascii=False,
    )
    row["templates_json"] = json.dumps(
        {str(k): v for k, v in (p.get("templates") or {}).items()},
        ensure_ascii=False,
    )
    return row


def _lead_to_sheet_row(lead: dict) -> dict:
    row = {c: lead.get(c, "") for c in LEAD_COLUMNS if c != "conversation_json"}
    row["conversation_json"] = json.dumps(lead.get("conversation") or [], ensure_ascii=False)
    row["responded"] = "true" if lead.get("responded") else "false"
    row["active_sequence"] = "true" if lead.get("active_sequence") else "false"
    row["last_step_sent"] = str(int(lead.get("last_step_sent") or 0))
    row["contact_count"] = str(int(lead.get("contact_count") or 0))
    for k in ("first_contacted", "last_emailed"):
        row[k] = lead.get(k) or ""
    return row


# ---------- Local JSON ----------


def _load_projects_local() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PROJECTS_JSON.exists():
        return []
    with open(PROJECTS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [_normalize_project(x) for x in data]


def _save_projects_local(projects: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROJECTS_JSON, "w", encoding="utf-8") as f:
        json.dump(projects, f, indent=2, ensure_ascii=False)


def _load_leads_local() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not LEADS_JSON.exists():
        return []
    with open(LEADS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [_normalize_lead(x) for x in data]


def _save_leads_local(leads: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEADS_JSON, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)


# ---------- Google Sheets ----------


def _open_worksheet(title: str, columns: list[str], *, create_if_missing: bool = False):
    import gspread
    from .. import storage

    sh = storage._open_spreadsheet()
    try:
        return sh.worksheet(title)
    except gspread.WorksheetNotFound:
        if not create_if_missing:
            raise
        ws = sh.add_worksheet(title=title, rows=2000, cols=max(len(columns), 26))
        ws.update("A1", [columns], value_input_option="USER_ENTERED")
        return ws


def _load_projects_sheets() -> list[dict]:
    import gspread

    try:
        ws = _open_worksheet("x_projects", PROJECT_COLUMNS, create_if_missing=False)
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
        if raw.get("id") or raw.get("name"):
            out.append(_normalize_project(raw))
    return out


def _save_projects_sheets(projects: list[dict]) -> None:
    ws = _open_worksheet("x_projects", PROJECT_COLUMNS, create_if_missing=True)
    values = [PROJECT_COLUMNS]
    for p in projects:
        row = _project_to_sheet_row(p)
        values.append([row.get(c, "") for c in PROJECT_COLUMNS])
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")


def _load_leads_sheets() -> list[dict]:
    import gspread

    try:
        ws = _open_worksheet("x_leads", LEAD_COLUMNS, create_if_missing=False)
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
        if raw.get("email") or raw.get("company_name") or raw.get("id"):
            out.append(_normalize_lead(raw))
    return out


def _save_leads_sheets(leads: list[dict]) -> None:
    ws = _open_worksheet("x_leads", LEAD_COLUMNS, create_if_missing=True)
    values = [LEAD_COLUMNS]
    for lead in leads:
        row = _lead_to_sheet_row(lead)
        values.append([row.get(c, "") for c in LEAD_COLUMNS])
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")


# ---------- Public API: projects ----------


def load_all_projects() -> list[dict]:
    if _using_cloud():
        return _load_projects_sheets()
    return _load_projects_local()


def save_all_projects(projects: list[dict]) -> None:
    if _using_cloud():
        _save_projects_sheets(projects)
    else:
        _save_projects_local(projects)


def list_projects(*, include_archived: bool = False) -> list[dict]:
    projects = load_all_projects()
    if include_archived:
        return projects
    return [p for p in projects if (p.get("status") or "active") != "archived"]


def get_project(project_id: str) -> Optional[dict]:
    pid = (project_id or "").strip()
    if not pid:
        return None
    for p in load_all_projects():
        if p.get("id") == pid:
            return p
    return None


def create_project(
    *,
    name: str,
    project_type: str = "buyer",
    scope: str = "",
    tone_notes: str = "",
) -> dict:
    name = (name or "").strip()
    if not name:
        raise ValueError("Project name is required.")
    ptype = (project_type or "buyer").lower().strip()
    if ptype not in PROJECT_TYPES:
        ptype = "other"
    now = _utc_now()
    project = _normalize_project(
        {
            "id": f"x_{uuid.uuid4().hex[:10]}",
            "name": name,
            "project_type": ptype,
            "scope": scope or "",
            "tone_notes": tone_notes or "",
            "status": "active",
            "cadence": dict(DEFAULT_CADENCE),
            "templates": default_templates_for_scope(scope or name, ptype, tone_notes or ""),
            "created_at": now,
            "updated_at": now,
        }
    )
    projects = load_all_projects()
    projects.append(project)
    save_all_projects(projects)
    set_active_project_id(project["id"])
    return project


def update_project(project_id: str, **fields: Any) -> dict:
    projects = load_all_projects()
    found = None
    for p in projects:
        if p.get("id") == project_id:
            found = p
            break
    if not found:
        raise ValueError("Project not found.")
    allowed = {
        "name",
        "project_type",
        "scope",
        "tone_notes",
        "status",
        "cadence",
        "templates",
    }
    for k, v in fields.items():
        if k not in allowed:
            continue
        if k == "project_type":
            pt = str(v or "buyer").lower().strip()
            found[k] = pt if pt in PROJECT_TYPES else "other"
        elif k == "templates" and isinstance(v, dict):
            found[k] = {int(sk): sv for sk, sv in v.items()}
        elif k == "cadence" and isinstance(v, dict):
            found[k] = {int(sk): int(sv) for sk, sv in v.items()}
        else:
            found[k] = v
    found["updated_at"] = _utc_now()
    save_all_projects(projects)
    return deepcopy(found)


def get_active_project_id() -> str:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if ACTIVE_JSON.exists():
        try:
            with open(ACTIVE_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get("active_project_id") or "").strip()
        except Exception:
            pass
    projects = list_projects()
    return projects[0]["id"] if projects else ""


def set_active_project_id(project_id: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(ACTIVE_JSON, "w", encoding="utf-8") as f:
        json.dump({"active_project_id": (project_id or "").strip()}, f, indent=2)


def get_active_project() -> Optional[dict]:
    pid = get_active_project_id()
    if not pid:
        return None
    return get_project(pid)


# ---------- Public API: leads ----------


def load_all_x_leads() -> list[dict]:
    if _using_cloud():
        return _load_leads_sheets()
    return _load_leads_local()


def save_all_x_leads(leads: list[dict]) -> None:
    if _using_cloud():
        _save_leads_sheets(leads)
    else:
        _save_leads_local(leads)


def load_leads_for_project(project_id: str) -> list[dict]:
    pid = (project_id or "").strip()
    return [l for l in load_all_x_leads() if (l.get("project_id") or "") == pid]


def upsert_leads_for_project(project_id: str, new_leads: list[dict]) -> tuple[int, int]:
    pid = (project_id or "").strip()
    if not pid:
        raise ValueError("project_id is required.")
    existing = load_all_x_leads()
    by_key = {lead_key(l): l for l in existing if lead_key(l)}
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
        "reasoning",
        "assigned_to",
        "project_id",
    }

    for raw in new_leads:
        incoming = _normalize_lead({**raw, "project_id": pid})
        if not (
            (incoming.get("email") or "").strip()
            or (incoming.get("company_name") or "").strip()
        ):
            continue
        if not incoming.get("id"):
            incoming["id"] = f"XL{datetime.now().strftime('%Y%m%d%H%M%S')}{added + updated}"
        key = lead_key(incoming)
        if not key or key.endswith(":id:") or key == "id:":
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

    save_all_x_leads(list(by_key.values()))
    return added, updated


def update_x_lead(updated: dict) -> None:
    leads = load_all_x_leads()
    key = lead_key(updated)
    out = []
    found = False
    for l in leads:
        if lead_key(l) == key:
            out.append(_normalize_lead({**l, **updated}))
            found = True
        else:
            out.append(l)
    if not found:
        out.append(_normalize_lead(updated))
    save_all_x_leads(out)


def bump_x_contact(lead: dict, step: int) -> None:
    today = datetime.now().isoformat()
    if not lead.get("first_contacted"):
        lead["first_contacted"] = today
    lead["last_emailed"] = today
    lead["last_step_sent"] = step
    lead["status"] = f"emailed_{step}"
    lead["contact_count"] = int(lead.get("contact_count") or 0) + 1
