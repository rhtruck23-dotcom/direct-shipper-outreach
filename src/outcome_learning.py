"""
Outcome learning v1 (NOT RL).

On convert / DNC / reply intent, append outcomes to data/agent_feedback.json.
When generating emails, surface top similar past successful patterns.
UI copy should say "outcome learning", never "reinforcement learning".
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from .paths import DATA_DIR
from .rag import select_similar_snippets, truncate

FEEDBACK_JSON = DATA_DIR / "agent_feedback.json"

SUCCESS_OUTCOMES = frozenset({"converted", "positive_reply", "engaged", "referral"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_feedback() -> list[dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not FEEDBACK_JSON.exists():
        return []
    try:
        with open(FEEDBACK_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_feedback(rows: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)


def record_outcome(
    *,
    outcome: str,
    lead: Optional[dict] = None,
    project: Optional[dict] = None,
    subject: str = "",
    body_snippet: str = "",
    intent: str = "",
    funnel: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Append one outcome event. Safe no-op on disk errors."""
    entry = {
        "id": f"fb_{uuid.uuid4().hex[:12]}",
        "at": _utc_now(),
        "outcome": (outcome or "").strip().lower(),
        "intent": (intent or "").strip().lower(),
        "funnel": funnel or "",
        "project_id": (project or {}).get("id") or "",
        "project_name": (project or {}).get("name") or "",
        "lead_id": (lead or {}).get("id") or "",
        "company_name": (lead or {}).get("company_name") or "",
        "email": (lead or {}).get("email") or "",
        "sales_stage": (lead or {}).get("sales_stage") or "",
        "subject": truncate(subject, 200),
        "body_snippet": truncate(body_snippet or ((lead or {}).get("remarks") or ""), 500),
        "notes": truncate(notes, 300),
        "scope_snip": truncate(((project or {}).get("scope") or ""), 400),
    }
    try:
        rows = load_feedback()
        rows.append(entry)
        # keep file bounded
        if len(rows) > 2000:
            rows = rows[-2000:]
        save_feedback(rows)
        _maybe_sheet_append(entry)
    except Exception:
        pass
    return entry


def _maybe_sheet_append(entry: dict) -> None:
    """Best-effort append to Google Sheet tab `agent_feedback` when cloud is on."""
    try:
        from . import storage

        if not storage.using_cloud():
            return
        sh = storage._open_spreadsheet()  # noqa: SLF001 — shared workbook helper
        import gspread

        try:
            ws = sh.worksheet("agent_feedback")
        except gspread.WorksheetNotFound:
            cols = list(entry.keys())
            ws = sh.add_worksheet(title="agent_feedback", rows=500, cols=max(len(cols), 12))
            ws.update("A1", [cols], value_input_option="USER_ENTERED")
        header = ws.row_values(1) or list(entry.keys())
        row = [str(entry.get(c, "")) for c in header]
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        return


def successful_patterns(
    *,
    query: str = "",
    project_id: str = "",
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Return similar past successful outcomes for prompt injection."""
    rows = [
        r
        for r in load_feedback()
        if (r.get("outcome") or "") in SUCCESS_OUTCOMES
        and (not project_id or r.get("project_id") == project_id or not r.get("project_id"))
    ]
    if not rows:
        return []
    if not query.strip():
        return rows[-top_k:]

    docs = []
    for r in rows:
        docs.append(
            " ".join(
                [
                    r.get("subject") or "",
                    r.get("body_snippet") or "",
                    r.get("scope_snip") or "",
                    r.get("company_name") or "",
                    r.get("notes") or "",
                ]
            )
        )
    ranked = select_similar_snippets(query, docs, top_k=top_k)
    # map back by content equality (stable enough for v1)
    out: list[dict] = []
    used: set[str] = set()
    for snip in ranked:
        for r, d in zip(rows, docs):
            if d == snip and r["id"] not in used:
                out.append(r)
                used.add(r["id"])
                break
    return out


def patterns_for_prompt(
    *,
    lead: Optional[dict] = None,
    project: Optional[dict] = None,
    top_k: int = 3,
) -> str:
    lead = lead or {}
    project = project or {}
    query = " ".join(
        [
            project.get("scope") or "",
            lead.get("company_name") or "",
            lead.get("notes") or "",
            lead.get("remarks") or "",
            lead.get("freight_type") or "",
            lead.get("lane_or_region") or "",
        ]
    )
    hits = successful_patterns(
        query=query,
        project_id=project.get("id") or "",
        top_k=top_k,
    )
    if not hits:
        return ""
    lines = ["OUTCOME LEARNING — similar past successes (not RL):"]
    for h in hits:
        lines.append(
            f"- [{h.get('outcome')}] {h.get('company_name') or '?'}: "
            f"{truncate(h.get('subject') or '', 80)} | "
            f"{truncate(h.get('body_snippet') or '', 160)}"
        )
    return "\n".join(lines)
