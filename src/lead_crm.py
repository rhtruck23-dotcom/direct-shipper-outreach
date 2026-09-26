"""
Per-lead CRM helpers — notes timeline + scheduled tasks + due notifications.

Tasks live in data/lead_tasks.json (and sheet tab `lead_tasks` when cloud).
Notes timeline appends onto the lead dict (`notes_timeline`) without wiping remarks.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

from .crm_picklists import apply_crm_defaults
from .paths import DATA_DIR

TASKS_JSON = DATA_DIR / "lead_tasks.json"

TASK_COLUMNS = [
    "id",
    "lead_id",
    "funnel",
    "title",
    "due_at",
    "status",
    "created_at",
    "done_at",
    "company_name",
    "notes",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_dt(value: str) -> Optional[datetime]:
    s = (value or "").strip()
    if not s:
        return None
    try:
        # date-only → start of day local-ish (naive)
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s + "T00:00:00")
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except Exception:
        return None


def parse_due_date(value: str) -> Optional[date]:
    dt = _parse_dt(value)
    return dt.date() if dt else None


# ---------- Notes timeline ----------

def append_note(
    lead: dict,
    text: str,
    *,
    author: str = "",
) -> dict:
    """Append a timeline note; also mirrors into remarks as a short tag."""
    apply_crm_defaults(lead)
    body = (text or "").strip()
    if not body:
        return lead
    entry = {
        "id": f"n_{uuid.uuid4().hex[:10]}",
        "at": _utc_now(),
        "text": body,
        "author": (author or "").strip(),
    }
    tl = list(lead.get("notes_timeline") or [])
    tl.append(entry)
    lead["notes_timeline"] = tl
    # Keep legacy remarks useful as a rolling summary line
    rem = (lead.get("remarks") or "").strip()
    tag = f"[{entry['at'][:10]}] {body[:120]}"
    lead["remarks"] = (rem + " | " + tag).strip(" |") if rem else tag
    return lead


# ---------- Tasks store ----------

def _blank_task() -> dict[str, Any]:
    return {
        "id": "",
        "lead_id": "",
        "funnel": "shipper",  # shipper | lead_x | carrier
        "title": "",
        "due_at": "",
        "status": "open",  # open | done
        "created_at": "",
        "done_at": "",
        "company_name": "",
        "notes": "",
    }


def _normalize_task(raw: dict) -> dict:
    t = _blank_task()
    for k in t:
        if k in raw and raw[k] not in (None,):
            t[k] = raw[k]
    t["status"] = "done" if str(t.get("status") or "").lower() == "done" else "open"
    t["title"] = str(t.get("title") or "").strip()
    t["lead_id"] = str(t.get("lead_id") or "").strip()
    t["funnel"] = str(t.get("funnel") or "shipper").strip() or "shipper"
    t["due_at"] = str(t.get("due_at") or "").strip()
    if not t.get("id"):
        t["id"] = f"task_{uuid.uuid4().hex[:12]}"
    if not t.get("created_at"):
        t["created_at"] = _utc_now()
    return t


def load_tasks() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not TASKS_JSON.exists():
        cloud = _try_load_sheet_tasks()
        if cloud is not None:
            return cloud
        return []
    try:
        with open(TASKS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [_normalize_task(x) for x in (data or [])]
    except Exception:
        return []


def save_tasks(tasks: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    normed = [_normalize_task(t) for t in tasks]
    with open(TASKS_JSON, "w", encoding="utf-8") as f:
        json.dump(normed, f, indent=2, ensure_ascii=False)
    _try_save_sheet_tasks(normed)


def _try_load_sheet_tasks() -> Optional[list[dict]]:
    try:
        from . import storage

        if not storage.using_cloud():
            return None
        import gspread

        sh = storage._open_spreadsheet()  # noqa: SLF001
        try:
            ws = sh.worksheet("lead_tasks")
        except gspread.WorksheetNotFound:
            return []
        values = ws.get_all_values()
        if not values or len(values) < 2:
            return []
        header = [str(h).strip() for h in values[0]]
        out = []
        for row in values[1:]:
            raw = {
                header[i]: (row[i] if i < len(row) else "")
                for i in range(len(header))
                if header[i]
            }
            if raw.get("id") or raw.get("title"):
                out.append(_normalize_task(raw))
        return out
    except Exception:
        return None


def _try_save_sheet_tasks(tasks: list[dict]) -> None:
    try:
        from . import storage

        if not storage.using_cloud():
            return
        import gspread

        sh = storage._open_spreadsheet()  # noqa: SLF001
        try:
            ws = sh.worksheet("lead_tasks")
        except gspread.WorksheetNotFound:
            ws = sh.add_worksheet(
                title="lead_tasks", rows=1000, cols=max(len(TASK_COLUMNS), 12)
            )
        values = [TASK_COLUMNS]
        for t in tasks:
            values.append([str(t.get(c, "") or "") for c in TASK_COLUMNS])
        ws.clear()
        ws.update("A1", values, value_input_option="USER_ENTERED")
    except Exception:
        return


def create_task(
    *,
    lead_id: str,
    title: str,
    due_at: str,
    funnel: str = "shipper",
    company_name: str = "",
    notes: str = "",
) -> dict:
    tasks = load_tasks()
    task = _normalize_task(
        {
            "lead_id": lead_id,
            "title": title,
            "due_at": due_at,
            "funnel": funnel,
            "company_name": company_name,
            "notes": notes,
            "status": "open",
        }
    )
    tasks.append(task)
    save_tasks(tasks)
    return task


def update_task(task_id: str, **fields: Any) -> Optional[dict]:
    tasks = load_tasks()
    out = None
    for t in tasks:
        if t.get("id") == task_id:
            for k, v in fields.items():
                if k in t:
                    t[k] = v
            if fields.get("status") == "done" and not t.get("done_at"):
                t["done_at"] = _utc_now()
            if fields.get("status") == "open":
                t["done_at"] = ""
            out = _normalize_task(t)
            break
    if out:
        save_tasks([_normalize_task(t) for t in tasks])
    return out


def mark_task_done(task_id: str) -> Optional[dict]:
    return update_task(task_id, status="done")


def tasks_for_lead(lead_id: str, *, include_done: bool = True) -> list[dict]:
    lid = (lead_id or "").strip()
    out = [t for t in load_tasks() if (t.get("lead_id") or "") == lid]
    if not include_done:
        out = [t for t in out if t.get("status") != "done"]
    out.sort(key=lambda t: t.get("due_at") or "")
    return out


def classify_task_bucket(
    task: dict,
    *,
    today: Optional[date] = None,
    upcoming_days: int = 7,
) -> str:
    """
    Return: past_due | due_today | upcoming | later | done | no_due
    """
    if (task.get("status") or "") == "done":
        return "done"
    due = parse_due_date(task.get("due_at") or "")
    if not due:
        return "no_due"
    today = today or date.today()
    if due < today:
        return "past_due"
    if due == today:
        return "due_today"
    if due <= today + timedelta(days=upcoming_days):
        return "upcoming"
    return "later"


def group_open_tasks(
    tasks: Optional[list[dict]] = None,
    *,
    today: Optional[date] = None,
    upcoming_days: int = 7,
) -> dict[str, list[dict]]:
    today = today or date.today()
    buckets = {"past_due": [], "due_today": [], "upcoming": [], "later": [], "no_due": []}
    for t in tasks if tasks is not None else load_tasks():
        if (t.get("status") or "") == "done":
            continue
        b = classify_task_bucket(t, today=today, upcoming_days=upcoming_days)
        if b in buckets:
            buckets[b].append(t)
    for k in buckets:
        buckets[k].sort(key=lambda x: x.get("due_at") or "")
    return buckets


def lead_stable_id(lead: dict, *, funnel: str = "shipper") -> str:
    """Stable id for task linking — prefer lead.id, else email/company key."""
    lid = (lead.get("id") or "").strip()
    if lid:
        return lid
    email = (lead.get("email") or "").lower().strip()
    if email:
        pid = (lead.get("project_id") or "").strip()
        return f"{funnel}:{pid}:{email}" if pid else f"{funnel}:{email}"
    company = (lead.get("company_name") or "").lower().strip()
    return f"{funnel}:co:{company}"


def ensure_lead_crm_fields(lead: dict) -> dict:
    return apply_crm_defaults(lead)


def send_one_off_email(
    lead: dict,
    company: dict,
    *,
    subject: str,
    body: str,
    funnel: str = "shipper",
) -> dict:
    """Send independent one-off via emailer (respects live/dry-run)."""
    from .emailer import send_email

    to_addr = (lead.get("email") or "").strip()
    if not to_addr:
        return {"ok": False, "error": "Lead has no email", "mode": ""}
    result = send_email(
        to_addr,
        subject,
        body,
        company,
        meta={"type": "one_off", "funnel": funnel, "lead_id": lead.get("id") or ""},
    )
    conv = list(lead.get("conversation") or [])
    conv.append(
        {
            "at": result.get("at") or _utc_now(),
            "direction": "outbound_one_off",
            "subject": subject,
            "body": body,
            "mode": result.get("mode"),
            "funnel": funnel,
        }
    )
    lead["conversation"] = conv
    return result
