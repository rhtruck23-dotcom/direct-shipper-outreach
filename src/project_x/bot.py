"""Lead-for-X inbox bot — classifies replies with project scope in the loop."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from ..bot import BotDecision
from ..emailer import send_email
from ..notify import notify_owner
from .agent import classify_reply_sentiment, compose_reply
from .leads import mark_x_response
from .store import update_x_lead


def handle_x_reply(
    lead: dict,
    inbound_text: str,
    company: dict[str, Any],
    project: dict[str, Any],
) -> BotDecision:
    """Classify + draft reply molded by Project Scope."""
    labels = classify_reply_sentiment(inbound_text)
    intent = labels["intent"]
    subject, body, reasoning = compose_reply(
        lead, inbound_text, company, project, intent=intent
    )

    stop = intent in ("opt_out", "escalate", "positive", "referral", "unclear")
    mark_pos = intent != "opt_out"
    escalate = intent in ("escalate", "positive", "referral", "unclear")
    auto = bool(body) and intent != "escalate"

    owner_alert = ""
    if escalate:
        owner_alert = (
            f"Lead-for-X [{project.get('name')}] {intent.upper()}: "
            f"{lead.get('company_name')} ({lead.get('email')})\n"
            f"Sentiment: {labels['sentiment']}\n"
            f"Reasoning: {reasoning}\n\nTheir message:\n{inbound_text}"
        )

    # Stash reasoning on lead for UI
    lead["reasoning"] = reasoning

    return BotDecision(
        intent=intent,
        auto_send=auto,
        reply_subject=subject,
        reply_body=body,
        escalate_to_owner=escalate,
        owner_alert=owner_alert,
        stop_sequence=stop,
        mark_positive=mark_pos,
    )


def process_inbox_reply(
    lead: dict,
    inbound_text: str,
    company: dict[str, Any],
    project: dict[str, Any],
) -> dict[str, Any]:
    """Full inbox pass: decide, optionally send, persist. Returns summary dict."""
    decision = handle_x_reply(lead, inbound_text, company, project)
    summary: dict[str, Any] = {
        "intent": decision.intent,
        "reasoning": lead.get("reasoning") or "",
        "sent": False,
        "mode": "",
        "decision": decision,
    }

    if decision.stop_sequence:
        mark_x_response(lead, positive=decision.mark_positive)

    conv = lead.get("conversation") or []
    conv.append(
        {
            "at": datetime.now().isoformat(),
            "direction": "inbound",
            "body": inbound_text,
            "intent": decision.intent,
            "funnel": "lead_x",
            "project_id": project.get("id"),
        }
    )

    if decision.auto_send and company.get("bot_auto_reply", True) and decision.reply_body:
        result = send_email(
            lead["email"],
            decision.reply_subject,
            decision.reply_body,
            company,
            meta={
                "type": "x_bot_reply",
                "intent": decision.intent,
                "project_id": project.get("id"),
            },
        )
        conv.append(
            {
                "at": result.get("at") or datetime.now().isoformat(),
                "direction": "outbound_bot",
                "subject": decision.reply_subject,
                "body": decision.reply_body,
                "mode": result.get("mode"),
                "funnel": "lead_x",
            }
        )
        summary["sent"] = bool(result.get("ok"))
        summary["mode"] = result.get("mode") or ""

    if decision.escalate_to_owner and decision.owner_alert:
        notify_owner(
            company,
            f"X {decision.intent.upper()}: {lead.get('company_name')} [{project.get('name')}]",
            decision.owner_alert,
        )

    rem = lead.get("remarks") or ""
    tag = f"XReply:{decision.intent}"
    if tag not in rem:
        lead["remarks"] = (rem + f" | {tag}").strip(" |")
    if lead.get("reasoning"):
        rnote = lead["reasoning"][:120]
        if rnote and rnote not in (lead.get("remarks") or ""):
            lead["remarks"] = ((lead.get("remarks") or "") + f" | {rnote}").strip(" |")

    lead["conversation"] = conv
    update_x_lead(lead)
    return summary
