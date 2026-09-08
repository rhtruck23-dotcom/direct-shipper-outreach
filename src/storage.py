"""
Permanent lead storage.

Local mode  -> data/leads.json  (dev / PC)
Cloud mode  -> Google Sheet     (Streamlit Cloud free hosting)

Streamlit Community Cloud wipes local files on reboot, so Google Sheets
is the free permanent record of every contacted lead.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from .paths import DATA_DIR

LEADS_JSON = DATA_DIR / "leads_db.json"

# Flat columns stored in Google Sheet (conversation stored as JSON string)
SHEET_COLUMNS = [
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


def _blank_lead() -> dict[str, Any]:
    return {
        "id": "",
        "company_name": "",
        "contact_name": "",
        "email": "",
        "phone": "",
        "state": "",
        "county": "",
        "zip": "",
        "freight_type": "",
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
        "conversation": [],
    }


def lead_key(lead: dict) -> str:
    email = (lead.get("email") or "").lower().strip()
    if email:
        return email
    return f"id:{(lead.get('id') or lead.get('company_name') or '').lower().strip()}"


def _normalize(raw: dict) -> dict:
    lead = _blank_lead()
    for k in lead:
        if k in raw and raw[k] not in (None, ""):
            lead[k] = raw[k]
    # aliases / sheet string casts
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
    return lead


def _to_sheet_row(lead: dict) -> dict:
    row = {c: lead.get(c, "") for c in SHEET_COLUMNS if c != "conversation_json"}
    row["conversation_json"] = json.dumps(lead.get("conversation") or [], ensure_ascii=False)
    row["responded"] = "true" if lead.get("responded") else "false"
    row["active_sequence"] = "true" if lead.get("active_sequence") else "false"
    row["last_step_sent"] = str(int(lead.get("last_step_sent") or 0))
    row["contact_count"] = str(int(lead.get("contact_count") or 0))
    for k in ("first_contacted", "last_emailed"):
        row[k] = lead.get(k) or ""
    return row


# ---------- Local JSON ----------

def _load_local() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not LEADS_JSON.exists():
        # migrate old CSV+state if present
        migrated = _migrate_legacy()
        if migrated:
            _save_local(migrated)
            return migrated
        return []
    with open(LEADS_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [_normalize(x) for x in data]


def _save_local(leads: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LEADS_JSON, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)


def _migrate_legacy() -> list[dict]:
    try:
        from .leads import load_leads as legacy_load

        return [_normalize(l) for l in legacy_load()]
    except Exception:
        return []


# ---------- Google Sheets ----------

def _secrets_dict() -> dict:
    try:
        import streamlit as st

        # Streamlit AttrDict → plain dict of top-level keys
        return {k: st.secrets[k] for k in st.secrets}
    except Exception:
        return {}


def _get_sheet_id() -> str:
    try:
        import streamlit as st

        return str(st.secrets.get("google_sheet_id", "") or "").strip()
    except Exception:
        return ""


def _get_gcp_info() -> Optional[dict]:
    """
    Accept (in order):
      1) gcp_sa_b64 = "base64 of entire JSON"   ← hardest to break in Secrets
      2) gcp_service_account_json = \"\"\"{...}\"\"\"
      3) [gcp_service_account] TOML table
    """
    try:
        import streamlit as st
        import base64

        # 1) Base64 one-liner (recommended)
        b64 = None
        try:
            b64 = st.secrets.get("gcp_sa_b64", None)
        except Exception:
            b64 = None
        if b64:
            raw = base64.b64decode(str(b64).strip()).decode("utf-8")
            return json.loads(raw)

        # 2) Full JSON string
        raw = None
        try:
            raw = st.secrets.get("gcp_service_account_json", None)
        except Exception:
            raw = None
        if raw:
            if isinstance(raw, dict):
                return dict(raw)
            text = str(raw).strip()
            if text and text != "REPLACE_ME":
                return json.loads(text)

        # 3) TOML table
        if "gcp_service_account" in st.secrets:
            info = dict(st.secrets["gcp_service_account"])
            # private_key sometimes needs newline fix
            pk = info.get("private_key")
            if isinstance(pk, str) and "\\n" in pk and "\n" not in pk.replace("\\n", ""):
                info["private_key"] = pk.replace("\\n", "\n")
            elif isinstance(pk, str) and "-----BEGIN" in pk and "\\n" in pk:
                info["private_key"] = pk.replace("\\n", "\n")
            return info
    except Exception:
        return None
    return None


def sheets_configured(secrets: Optional[dict] = None) -> bool:
    if secrets is not None:
        sheet_id = str(secrets.get("google_sheet_id", "") or "").strip()
        gcp = (
            secrets.get("gcp_sa_b64")
            or secrets.get("gcp_service_account_json")
            or secrets.get("gcp_service_account")
        )
        return bool(sheet_id) and bool(gcp)
    return bool(_get_sheet_id()) and bool(_get_gcp_info())


def test_sheet_connection() -> str:
    """Try reading/writing the Sheet. Returns OK message or error."""
    ws = _open_worksheet(create_if_missing=True)
    title = ws.title
    rows = len(ws.get_all_values())
    return f"Connected to worksheet '{title}' ({rows} row(s) including header)."


def _open_spreadsheet():
    import gspread
    from google.oauth2.service_account import Credentials

    info = _get_gcp_info()
    if not info:
        raise RuntimeError(
            "Google service account not found in Secrets. "
            "Use Cloud Hosting → paste JSON → copy generated Secrets → Save."
        )
    sheet_id = _get_sheet_id()
    if not sheet_id:
        raise RuntimeError("google_sheet_id missing in Secrets.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(sheet_id)


def _open_worksheet(*, create_if_missing: bool = False):
    """
    Open the leads worksheet.
    Reads must use create_if_missing=False so load never writes to Google.
    """
    import gspread

    sh = _open_spreadsheet()
    try:
        return sh.worksheet("leads")
    except gspread.WorksheetNotFound:
        if not create_if_missing:
            raise
        ws = sh.add_worksheet(title="leads", rows=2000, cols=max(len(SHEET_COLUMNS), 26))
        # Single batch write — never update_cell loops
        ws.update("A1", [SHEET_COLUMNS], value_input_option="USER_ENTERED")
        return ws


def _load_sheets() -> list[dict]:
    """Read-only. Missing sheet / empty sheet → []. Never mutates cells."""
    import gspread

    try:
        ws = _open_worksheet(create_if_missing=False)
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
        if raw.get("company_name") or raw.get("email"):
            out.append(_normalize(raw))
    return out


def _save_sheets(leads: list[dict]) -> None:
    """Full rewrite — also migrates new columns (e.g. assigned_to) in one write."""
    ws = _open_worksheet(create_if_missing=True)
    values = [SHEET_COLUMNS]
    for lead in leads:
        row = _to_sheet_row(lead)
        values.append([row.get(c, "") for c in SHEET_COLUMNS])
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")


# ---------- Public API ----------

def using_cloud() -> bool:
    return sheets_configured()


def load_all_leads() -> list[dict]:
    if using_cloud():
        return _load_sheets()
    return _load_local()


def save_all_leads(leads: list[dict]) -> None:
    if using_cloud():
        _save_sheets(leads)
    else:
        _save_local(leads)


def upsert_leads(new_leads: list[dict]) -> tuple[int, int]:
    """
    Add/update by email. Never wipes DNC / converted / contact history
    when the same email is imported again.
    """
    existing = load_all_leads()
    by_key = {lead_key(l): l for l in existing if lead_key(l)}
    added = updated = 0

    for raw in new_leads:
        incoming = _normalize(raw)
        if not (incoming.get("email") or "").strip() and not (
            incoming.get("company_name") or ""
        ).strip():
            continue
        if not incoming.get("id"):
            incoming["id"] = f"L{datetime.now().strftime('%Y%m%d%H%M%S')}{added + updated}"
        key = lead_key(incoming)
        if not key or key == "id:":
            continue

        if key in by_key:
            old = by_key[key]
            # Protect history
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
            for field, val in incoming.items():
                if field in protected:
                    continue
                if val not in (None, ""):
                    old[field] = val
            # Never un-DNC via re-import
            if old.get("status") == "do_not_contact":
                old["active_sequence"] = False
            by_key[key] = old
            updated += 1
        else:
            by_key[key] = incoming
            added += 1

    save_all_leads(list(by_key.values()))
    return added, updated


def update_lead(updated: dict) -> None:
    leads = load_all_leads()
    key = lead_key(updated)
    out = []
    found = False
    for l in leads:
        if lead_key(l) == key:
            out.append(_normalize({**l, **updated}))
            found = True
        else:
            out.append(l)
    if not found:
        out.append(_normalize(updated))
    save_all_leads(out)


def bump_contact(lead: dict, step: int) -> None:
    today = datetime.now().isoformat()
    if not lead.get("first_contacted"):
        lead["first_contacted"] = today
    lead["last_emailed"] = today
    lead["last_step_sent"] = step
    lead["status"] = f"emailed_{step}"
    lead["contact_count"] = int(lead.get("contact_count") or 0) + 1
