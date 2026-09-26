"""
Autonomy runner — agent decides next actions for due leads with ~5% human involvement.

run_autonomy_pass():
  1. Build RAG context (scope, notes, conversation, feedback)
  2. Ask LLM for next action JSON (priority failover → rules)
  3. Execute allowed tools
  4. Record reasoning note

Safety: autopilot defaults OFF; daily email cap; skip DNC/converted;
escalate rate/contract/legal. Dry-run still "sends" via emailer.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from .agent_tools import (
    DEFAULT_DAILY_EMAIL_CAP,
    execute_action,
    is_converted,
    is_dnc,
    parse_action_json,
    parse_actions_json,
    text_needs_escalation,
    tool_append_note,
    under_daily_email_cap,
)
from .lead_crm import lead_stable_id, parse_due_date
from .llm import complete, extract_json_object
from .outcome_learning import patterns_for_prompt
from .rag import build_context_pack
from .schedule import next_action_for_lead


def autonomy_enabled(company: Optional[dict] = None) -> bool:
    """Auto-pilot toggle — default OFF until user enables."""
    return bool((company or {}).get("autonomy_autopilot"))


def autonomy_max_leads(company: Optional[dict] = None) -> int:
    try:
        n = int((company or {}).get("autonomy_max_leads") or 10)
    except Exception:
        n = 10
    return max(1, min(n, 100))


def _next_contact_due(lead: dict, *, today: Optional[date] = None) -> bool:
    today = today or date.today()
    due = parse_due_date(lead.get("next_contact_at") or "")
    if not due:
        return False
    return due <= today


def lead_needs_autonomy(lead: dict, *, today: Optional[date] = None) -> bool:
    """Due/past-due next_contact, or active sequence with a due email step."""
    if is_dnc(lead) or is_converted(lead):
        return False
    today = today or date.today()
    if _next_contact_due(lead, today=today):
        return True
    if lead.get("active_sequence") and next_action_for_lead(lead) is not None:
        return True
    return False


def collect_autonomy_candidates(
    *,
    shipper_leads: Optional[list[dict]] = None,
    x_leads: Optional[list[dict]] = None,
    max_leads: int = 10,
    today: Optional[date] = None,
) -> list[tuple[dict, str, Optional[dict]]]:
    """
    Return list of (lead, funnel, project_or_none) due for agent attention.
    """
    today = today or date.today()
    out: list[tuple[dict, str, Optional[dict]]] = []
    for lead in shipper_leads or []:
        if lead_needs_autonomy(lead, today=today):
            out.append((lead, "shipper", None))
    for lead in x_leads or []:
        if lead_needs_autonomy(lead, today=today):
            out.append((lead, "lead_x", None))
    # Priority: past next_contact first, then active sequence
    def _sort_key(item: tuple) -> tuple:
        lead = item[0]
        due = parse_due_date(lead.get("next_contact_at") or "")
        overdue = 0 if (due and due < today) else 1
        return (overdue, due.isoformat() if due else "9999", lead.get("company_name") or "")

    out.sort(key=_sort_key)
    return out[: max(0, int(max_leads))]


def _rules_next_action(lead: dict, *, funnel: str = "shipper") -> dict[str, Any]:
    """Deterministic fallback when all LLMs fail — never leave total failure."""
    if is_dnc(lead) or is_converted(lead):
        return {
            "action": "noop",
            "reasoning": "Skip DNC/converted (rules).",
        }
    # Peek at last inbound for escalate keywords
    conv = lead.get("conversation") or []
    for m in reversed(conv[-4:]):
        if (m.get("direction") or "").startswith("inbound"):
            body = m.get("body") or ""
            if text_needs_escalation(body):
                return {
                    "action": "escalate_to_owner",
                    "reason": "Inbound mentions rate/contract/legal — human required.",
                    "reasoning": "rules escalate keywords",
                }
    step = next_action_for_lead(lead) if lead.get("active_sequence") else None
    if step is not None:
        return {
            "action": "schedule_followup",
            "days": 0,
            "title": f"Send sequence email {step}",
            "reasoning": f"rules: sequence step {step} due — schedule task (no auto blast without pipeline).",
        }
    if _next_contact_due(lead):
        return {
            "action": "create_task",
            "title": f"Follow up — {lead.get('company_name') or 'lead'}",
            "due_at": datetime.now().replace(microsecond=0).isoformat(timespec="minutes"),
            "reasoning": "rules: next_contact past due — create task for human/pipeline.",
        }
    return {
        "action": "append_note",
        "text": "Autonomy pass: no due action (rules).",
        "reasoning": "rules noop-ish note",
    }


def decide_next_actions(
    lead: dict,
    company: dict,
    *,
    funnel: str = "shipper",
    project: Optional[dict] = None,
) -> tuple[list[dict], str]:
    """
    Ask LLM for action JSON. Returns (actions, provider).
    Always returns at least one action via rules fallback.
    """
    pack = build_context_pack(project=project, lead=lead)
    patterns = patterns_for_prompt(lead=lead, project=project)
    import json as _json

    step = next_action_for_lead(lead) if lead.get("active_sequence") else None
    rules = _rules_next_action(lead, funnel=funnel)
    rules_json = _json.dumps(rules, ensure_ascii=False)

    prompt = f"""You are the LogixTrek outreach agent. Decide the SINGLE best next action for this lead.
You may only use these actions (JSON):
- update_lead_fields: status?, stage?, priority?, next_contact_at?, crm_status?
- append_note: text
- create_task: title, due_at (ISO)
- send_email: subject, body  (respects dry-run/live; NEVER for DNC)
- set_active_sequence: active (bool)
- schedule_followup: days or due_at, title?
- escalate_to_owner: reason  (REQUIRED for rate/contract/legal/load commitment)
- noop: no change

Hard rules:
- Never email do_not_contact / DNC / converted.
- Escalate rate, pricing, contract, insurance, legal, load-now language.
- Prefer create_task / schedule_followup / append_note over cold sends unless a clear nurture email is warranted.
- Sequence step due hint: {step!r}

CONTEXT PACK:
{pack}

{patterns}

Funnel: {funnel}
Return ONLY JSON like:
{{"action":"create_task","title":"...","due_at":"2026-09-27T09:00","reasoning":"one sentence"}}
or {{"actions":[{{...}}],"reasoning":"..."}}
"""
    result = complete(prompt, company, rules_fallback=rules_json)
    provider = result.provider
    actions = parse_actions_json(result.text)
    if not actions:
        single = parse_action_json(result.text)
        if single:
            actions = [single]
    if not actions:
        actions = [rules]
        provider = "rules"
    # Cap to 3 actions per lead per pass
    return actions[:3], provider


def _persist_lead(lead: dict, funnel: str, project: Optional[dict] = None) -> None:
    if funnel == "lead_x":
        from .project_x.store import update_x_lead

        update_x_lead(lead)
    else:
        from .storage import update_lead

        update_lead(lead)


def process_lead_autonomy(
    lead: dict,
    company: dict,
    *,
    funnel: str = "shipper",
    project: Optional[dict] = None,
) -> dict[str, Any]:
    """Decide + execute tools for one lead. Returns summary."""
    summary: dict[str, Any] = {
        "lead": lead.get("company_name") or lead.get("email") or "",
        "lead_key": lead_stable_id(lead, funnel=funnel),
        "funnel": funnel,
        "provider": "",
        "actions": [],
        "results": [],
        "escalated": False,
        "ok": True,
    }
    if is_dnc(lead) or is_converted(lead):
        summary["ok"] = False
        summary["actions"] = [{"action": "noop", "reasoning": "skip dnc/converted"}]
        summary["results"] = [{"ok": False, "skipped": True, "message": "dnc_or_converted"}]
        return summary

    actions, provider = decide_next_actions(
        lead, company, funnel=funnel, project=project
    )
    summary["provider"] = provider
    summary["actions"] = actions

    reasoning_bits = []
    for act in actions:
        if act.get("reasoning"):
            reasoning_bits.append(str(act["reasoning"]))
        tr = execute_action(act, lead=lead, company=company, funnel=funnel)
        summary["results"].append(
            {
                "action": tr.action,
                "ok": tr.ok,
                "message": tr.message,
                "skipped": tr.skipped,
                "escalated": tr.escalated,
            }
        )
        if tr.escalated:
            summary["escalated"] = True
        if not tr.ok and not tr.skipped:
            summary["ok"] = False

    note = (
        f"[agent/{provider}] "
        + ("; ".join(reasoning_bits) if reasoning_bits else "autonomy pass")
        + " → "
        + ", ".join(r.get("action") or "?" for r in summary["results"])
    )
    tool_append_note(lead, note[:400], author="agent")
    try:
        _persist_lead(lead, funnel, project)
    except Exception as e:
        summary["ok"] = False
        summary["persist_error"] = str(e)
    return summary


def run_autonomy_pass(
    company: dict,
    *,
    max_leads: Optional[int] = None,
    shipper_leads: Optional[list[dict]] = None,
    x_leads: Optional[list[dict]] = None,
    x_project: Optional[dict] = None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Run one autonomy pass over due leads.

    force=True → run even if autopilot is off (Dashboard "Run agent now").
    When autopilot is off and force is False → no-op summary.
    """
    if not force and not autonomy_enabled(company):
        return {
            "ran": False,
            "reason": "autopilot_off",
            "processed": 0,
            "summaries": [],
            "emails_today": under_daily_email_cap(company)[1],
            "email_cap": under_daily_email_cap(company)[2],
        }

    limit = max_leads if max_leads is not None else autonomy_max_leads(company)

    # Lazy-load leads if not provided
    if shipper_leads is None:
        try:
            from .storage import load_all_leads

            shipper_leads = load_all_leads()
        except Exception:
            shipper_leads = []
    if x_leads is None:
        try:
            from .project_x.store import get_active_project, load_leads_for_project

            proj = x_project or get_active_project()
            x_project = proj
            x_leads = load_leads_for_project(proj["id"]) if proj else []
        except Exception:
            x_leads = []

    candidates = collect_autonomy_candidates(
        shipper_leads=shipper_leads,
        x_leads=x_leads,
        max_leads=limit,
    )
    # Attach active project to lead_x rows
    summaries = []
    for lead, funnel, _ in candidates:
        proj = x_project if funnel == "lead_x" else None
        summaries.append(
            process_lead_autonomy(lead, company, funnel=funnel, project=proj)
        )

    ok_cap, sent, cap = under_daily_email_cap(company)
    return {
        "ran": True,
        "processed": len(summaries),
        "summaries": summaries,
        "escalated": sum(1 for s in summaries if s.get("escalated")),
        "emails_today": sent,
        "email_cap": cap,
        "under_email_cap": ok_cap,
        "daily_cap_default": DEFAULT_DAILY_EMAIL_CAP,
    }


def format_pass_summary(result: dict) -> str:
    if not result.get("ran"):
        return f"Agent idle ({result.get('reason') or 'not run'})."
    lines = [
        f"Agent processed {result.get('processed', 0)} lead(s); "
        f"escalated {result.get('escalated', 0)}; "
        f"emails today {result.get('emails_today')}/{result.get('email_cap')}."
    ]
    for s in result.get("summaries") or []:
        acts = ", ".join(
            f"{r.get('action')}{'✓' if r.get('ok') else '✗'}"
            for r in (s.get("results") or [])
        )
        lines.append(
            f"· {s.get('lead')} [{s.get('provider')}] {acts}"
        )
    return "\n".join(lines)
