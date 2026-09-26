"""
Multi-Gmail mailbox send pool.

Local  -> data/mailboxes.json + data/mailbox_send_counts.json
Cloud  -> Google Sheet worksheet "mailboxes" (follow carrier_storage pattern)
         Daily send counters stay on local JSON (same as outbound_log).

pick_mailbox() round-robins enabled mailboxes that still have App Password
capacity under daily_cap (default 200). Dry-runs must NOT call record_send().
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from .paths import DATA_DIR

MAILBOXES_JSON = DATA_DIR / "mailboxes.json"
SEND_COUNTS_JSON = DATA_DIR / "mailbox_send_counts.json"

DEFAULT_DAILY_CAP = 200
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587
COUNT_TZ = ZoneInfo("America/Chicago")

MAILBOX_COLUMNS = [
    "id",
    "email",
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "daily_cap",
    "enabled",
]


def _today_key() -> str:
    """Calendar date for counters — America/Chicago (falls back to local)."""
    try:
        return datetime.now(COUNT_TZ).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def _blank_mailbox() -> dict[str, Any]:
    return {
        "id": "",
        "email": "",
        "smtp_host": DEFAULT_SMTP_HOST,
        "smtp_port": DEFAULT_SMTP_PORT,
        "smtp_user": "",
        "smtp_password": "",
        "daily_cap": DEFAULT_DAILY_CAP,
        "enabled": True,
    }


def _normalize(raw: dict) -> dict[str, Any]:
    mb = _blank_mailbox()
    for k in mb:
        if k in raw and raw[k] not in (None,):
            mb[k] = raw[k]
    mb["id"] = str(mb.get("id") or "").strip()
    mb["email"] = str(mb.get("email") or "").strip().lower()
    mb["smtp_host"] = str(mb.get("smtp_host") or DEFAULT_SMTP_HOST).strip()
    try:
        mb["smtp_port"] = int(mb.get("smtp_port") or DEFAULT_SMTP_PORT)
    except Exception:
        mb["smtp_port"] = DEFAULT_SMTP_PORT
    mb["smtp_user"] = str(mb.get("smtp_user") or mb["email"] or "").strip()
    mb["smtp_password"] = str(mb.get("smtp_password") or "").strip()
    try:
        mb["daily_cap"] = max(1, int(mb.get("daily_cap") or DEFAULT_DAILY_CAP))
    except Exception:
        mb["daily_cap"] = DEFAULT_DAILY_CAP
    mb["enabled"] = str(mb.get("enabled")).lower() in ("1", "true", "yes", "on")
    if not mb["id"] and mb["email"]:
        mb["id"] = f"mb_{uuid.uuid4().hex[:10]}"
    return mb


def _using_cloud() -> bool:
    try:
        from . import storage

        return storage.using_cloud()
    except Exception:
        return False


def _load_local() -> list[dict]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not MAILBOXES_JSON.exists():
        return []
    try:
        with open(MAILBOXES_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [_normalize(x) for x in data if isinstance(x, dict)]


def _save_local(mailboxes: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(MAILBOXES_JSON, "w", encoding="utf-8") as f:
        json.dump(mailboxes, f, indent=2, ensure_ascii=False)


def _open_mailboxes_worksheet(*, create_if_missing: bool = False):
    import gspread
    from . import storage

    sh = storage._open_spreadsheet()
    try:
        return sh.worksheet("mailboxes")
    except gspread.WorksheetNotFound:
        if not create_if_missing:
            raise
        ws = sh.add_worksheet(
            title="mailboxes", rows=200, cols=max(len(MAILBOX_COLUMNS), 10)
        )
        ws.update("A1", [MAILBOX_COLUMNS], value_input_option="USER_ENTERED")
        return ws


def _load_sheets() -> list[dict]:
    import gspread

    try:
        ws = _open_mailboxes_worksheet(create_if_missing=False)
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
        if raw.get("email") or raw.get("id"):
            out.append(_normalize(raw))
    return out


def _save_sheets(mailboxes: list[dict]) -> None:
    ws = _open_mailboxes_worksheet(create_if_missing=True)
    values = [MAILBOX_COLUMNS]
    for mb in mailboxes:
        row = _normalize(mb)
        values.append(
            [
                str(row.get(c, "") if c != "enabled" else ("true" if row.get("enabled") else "false"))
                for c in MAILBOX_COLUMNS
            ]
        )
    ws.clear()
    ws.update("A1", values, value_input_option="USER_ENTERED")


def load_mailboxes() -> list[dict]:
    if _using_cloud():
        try:
            return _load_sheets()
        except Exception:
            return _load_local()
    return _load_local()


def save_mailboxes(mailboxes: list[dict]) -> None:
    normalized = [_normalize(m) for m in mailboxes]
    if _using_cloud():
        try:
            _save_sheets(normalized)
            return
        except Exception:
            pass
    _save_local(normalized)


def _load_counts() -> dict[str, Any]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SEND_COUNTS_JSON.exists():
        return {"rr_index": 0, "counts": {}}
    try:
        with open(SEND_COUNTS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"rr_index": 0, "counts": {}}
    if not isinstance(data, dict):
        return {"rr_index": 0, "counts": {}}
    data.setdefault("rr_index", 0)
    data.setdefault("counts", {})
    return data


def _save_counts(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SEND_COUNTS_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _count_key(day: str, mailbox_id: str) -> str:
    return f"{day}:{mailbox_id}"


def get_send_count(mailbox_id: str, *, day: Optional[str] = None) -> int:
    day = day or _today_key()
    data = _load_counts()
    counts = data.get("counts") or {}
    try:
        return int(counts.get(_count_key(day, mailbox_id), 0) or 0)
    except Exception:
        return 0


def record_send(mailbox_id: str, *, day: Optional[str] = None) -> int:
    """Increment live-send counter for mailbox. Returns new count."""
    day = day or _today_key()
    mid = str(mailbox_id or "").strip()
    if not mid:
        return 0
    data = _load_counts()
    counts = data.setdefault("counts", {})
    key = _count_key(day, mid)
    try:
        n = int(counts.get(key, 0) or 0) + 1
    except Exception:
        n = 1
    counts[key] = n
    _save_counts(data)
    return n


def enabled_with_password(mailboxes: Optional[list[dict]] = None) -> list[dict]:
    """Enabled pool members that have an App Password (usable for live SMTP)."""
    mbs = mailboxes if mailboxes is not None else load_mailboxes()
    out = []
    for mb in mbs:
        n = _normalize(mb)
        if n.get("enabled") and (n.get("smtp_password") or "").strip() and n.get("email"):
            out.append(n)
    return out


def pool_usable(mailboxes: Optional[list[dict]] = None) -> bool:
    return bool(enabled_with_password(mailboxes))


def mailbox_under_cap(mb: dict, *, day: Optional[str] = None) -> bool:
    day = day or _today_key()
    n = _normalize(mb)
    sent = get_send_count(n["id"], day=day)
    return sent < int(n.get("daily_cap") or DEFAULT_DAILY_CAP)


def pick_mailbox(*, day: Optional[str] = None) -> Optional[dict]:
    """
    Next enabled mailbox under daily_cap (round-robin).
    Returns None if pool empty or all exhausted for the day.
    """
    day = day or _today_key()
    candidates = enabled_with_password()
    if not candidates:
        return None
    available = [m for m in candidates if mailbox_under_cap(m, day=day)]
    if not available:
        return None

    data = _load_counts()
    try:
        rr = int(data.get("rr_index") or 0)
    except Exception:
        rr = 0
    # Prefer round-robin among *all* enabled-with-password, skipping at-cap.
    # Index into full candidate list so order stays stable as caps fill.
    n = len(candidates)
    start = rr % n if n else 0
    chosen: Optional[dict] = None
    for i in range(n):
        idx = (start + i) % n
        mb = candidates[idx]
        if mailbox_under_cap(mb, day=day):
            chosen = mb
            data["rr_index"] = (idx + 1) % n
            _save_counts(data)
            break
    return chosen


def today_usage(*, day: Optional[str] = None) -> list[dict[str, Any]]:
    """Per-mailbox usage for UI: email → sent/cap + remaining."""
    day = day or _today_key()
    rows = []
    for mb in load_mailboxes():
        n = _normalize(mb)
        sent = get_send_count(n["id"], day=day)
        cap = int(n.get("daily_cap") or DEFAULT_DAILY_CAP)
        rows.append(
            {
                "id": n["id"],
                "email": n["email"],
                "enabled": bool(n.get("enabled")),
                "has_password": bool((n.get("smtp_password") or "").strip()),
                "sent": sent,
                "cap": cap,
                "remaining": max(0, cap - sent) if n.get("enabled") else 0,
                "daily_cap": cap,
            }
        )
    return rows


def total_remaining_capacity(*, day: Optional[str] = None) -> int:
    day = day or _today_key()
    return sum(
        r["remaining"]
        for r in today_usage(day=day)
        if r.get("enabled") and r.get("has_password")
    )


def pool_exhausted(*, day: Optional[str] = None) -> bool:
    """True when pool has usable mailboxes but none have remaining capacity."""
    if not pool_usable():
        return False
    return total_remaining_capacity(day=day) <= 0


def add_mailbox(
    email: str,
    smtp_password: str,
    *,
    daily_cap: int = DEFAULT_DAILY_CAP,
    smtp_host: str = DEFAULT_SMTP_HOST,
    smtp_port: int = DEFAULT_SMTP_PORT,
    enabled: bool = True,
) -> dict:
    email = (email or "").strip().lower()
    pw = (smtp_password or "").strip().replace(" ", "")
    mbs = load_mailboxes()
    for existing in mbs:
        if (existing.get("email") or "").lower() == email:
            existing["smtp_password"] = pw or existing.get("smtp_password") or ""
            existing["daily_cap"] = max(1, int(daily_cap or DEFAULT_DAILY_CAP))
            existing["smtp_host"] = smtp_host or DEFAULT_SMTP_HOST
            existing["smtp_port"] = int(smtp_port or DEFAULT_SMTP_PORT)
            existing["smtp_user"] = email
            existing["enabled"] = bool(enabled)
            save_mailboxes(mbs)
            return _normalize(existing)
    mb = _normalize(
        {
            "id": f"mb_{uuid.uuid4().hex[:10]}",
            "email": email,
            "smtp_host": smtp_host or DEFAULT_SMTP_HOST,
            "smtp_port": int(smtp_port or DEFAULT_SMTP_PORT),
            "smtp_user": email,
            "smtp_password": pw,
            "daily_cap": max(1, int(daily_cap or DEFAULT_DAILY_CAP)),
            "enabled": bool(enabled),
        }
    )
    mbs.append(mb)
    save_mailboxes(mbs)
    return mb


def update_mailbox(mailbox_id: str, **fields: Any) -> Optional[dict]:
    mid = str(mailbox_id or "").strip()
    mbs = load_mailboxes()
    found = None
    for i, mb in enumerate(mbs):
        if mb.get("id") == mid:
            updated = {**mb, **fields, "id": mid}
            if "smtp_password" in fields and not (fields.get("smtp_password") or "").strip():
                updated["smtp_password"] = mb.get("smtp_password") or ""
            if "email" in fields and fields["email"]:
                updated["email"] = str(fields["email"]).strip().lower()
                updated["smtp_user"] = updated["email"]
            mbs[i] = _normalize(updated)
            found = mbs[i]
            break
    if found is None:
        return None
    save_mailboxes(mbs)
    return found


def delete_mailbox(mailbox_id: str) -> bool:
    mid = str(mailbox_id or "").strip()
    mbs = load_mailboxes()
    new = [m for m in mbs if m.get("id") != mid]
    if len(new) == len(mbs):
        return False
    save_mailboxes(new)
    return True


def set_mailbox_enabled(mailbox_id: str, enabled: bool) -> Optional[dict]:
    return update_mailbox(mailbox_id, enabled=bool(enabled))
