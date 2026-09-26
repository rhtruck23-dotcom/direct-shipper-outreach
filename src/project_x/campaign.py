"""Lead-for-X campaign — 4-email sequence (days 0 / 4 / 9 / 16) with project context."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from ..emailer import send_email
from ..schedule import next_action_for_lead
from .agent import compose_step_email
from .leads import lead_key, persist_x_leads
from .store import bump_x_contact
from .templates import render_x_email


def run_due_x_emails(
    leads: list[dict],
    company: dict[str, Any],
    project: dict[str, Any],
    only_keys: list[str] | None = None,
    *,
    use_llm: bool = False,
) -> list[dict]:
    """
    Send due sequence emails for leads in this project.
    use_llm=False by default for batch speed; templates already scope-driven.
    """
    today = datetime.now()
    keyset = {k.lower() for k in only_keys} if only_keys else None
    results = []
    pid = project.get("id") or ""

    for lead in leads:
        if pid and (lead.get("project_id") or "") != pid:
            continue
        if keyset is not None and lead_key(lead).lower() not in keyset:
            continue

        if (lead.get("status") or "") == "do_not_contact":
            lead["active_sequence"] = False
            results.append(
                {
                    "lead": lead.get("company_name"),
                    "ok": False,
                    "error": "Do Not Contact — blocked forever",
                }
            )
            continue

        if not lead.get("email"):
            results.append(
                {
                    "lead": lead.get("company_name"),
                    "ok": False,
                    "error": "No email on file — add email before sending",
                }
            )
            continue

        step = next_action_for_lead(lead, today)
        if step is None:
            continue

        if use_llm:
            subject, body, reasoning = compose_step_email(
                step, lead, company, project, use_llm=True
            )
        else:
            subject, body = render_x_email(step, lead, company, project)
            reasoning = f"Template step {step}"

        send_result = send_email(
            lead["email"],
            subject,
            body,
            company,
            meta={
                "type": "x_sequence",
                "step": step,
                "project_id": pid,
                "lead_key": lead_key(lead),
                "company_name": lead.get("company_name"),
            },
        )

        if send_result.get("ok"):
            bump_x_contact(lead, step)
            conv = lead.get("conversation") or []
            conv.append(
                {
                    "at": today.isoformat(),
                    "direction": "outbound",
                    "step": step,
                    "subject": subject,
                    "body": body,
                    "mode": send_result.get("mode"),
                    "funnel": "lead_x",
                    "reasoning": reasoning,
                }
            )
            lead["conversation"] = conv
            if reasoning:
                lead["reasoning"] = reasoning
            stamp = today.strftime("%Y-%m-%d")
            note = lead.get("remarks") or ""
            tag = f"X Email {step} {stamp}"
            if tag not in note:
                lead["remarks"] = (note + f" | {tag}").strip(" |")

        results.append(
            {
                "lead": lead.get("company_name"),
                "email": lead.get("email"),
                "step": step,
                "body": body if not send_result.get("live") else "",
                "reasoning": reasoning,
                **send_result,
            }
        )

    persist_x_leads(leads)
    return results
