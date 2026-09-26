"""
Lead-for-X LLM agent — molds emails/replies from Project Scope.

Uses unified llm.py priority failover (gemini → groq → ollama → rules);
otherwise solid rule-based templates. Injects RAG context pack + outcome learning.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from ..llm import complete, extract_json_object
from ..outcome_learning import patterns_for_prompt
from ..rag import build_context_pack
from .templates import default_templates_for_scope, ensure_templates, render_x_email


def generate_templates_from_scope(
    project: dict,
    company: Optional[dict] = None,
) -> tuple[dict[int, dict[str, str]], str]:
    """
    Return (templates, method) where method is provider name or 'rules'.
    Always returns a complete 1–4 template set.
    """
    scope = (project.get("scope") or "").strip()
    ptype = project.get("project_type") or "buyer"
    tone = project.get("tone_notes") or ""
    fallback = default_templates_for_scope(scope or project.get("name") or "", ptype, tone)
    if not scope:
        return fallback, "rules"

    pack = build_context_pack(project=project)
    patterns = patterns_for_prompt(project=project)

    prompt = f"""You write cold-email sequences for a lead-conversion project.

Project name: {project.get('name')}
Project type (buyer = we want to buy; seller = we want to sell): {ptype}
Tone notes: {tone or '(none)'}

CONTEXT PACK:
{pack}

{patterns}

PROJECT SCOPE (source of truth — mold every email to this domain):
---
{scope}
---

Write a 4-email follow-up sequence (days 0 / 4 / 9 / 16). Professional, specific to the scope, not generic SaaS spam.
Use merge placeholders exactly as written: {{contact_name}}, {{company_name}}, {{my_name}}, {{my_company}}, {{my_phone}}, {{website}}, {{unsubscribe_note}}, {{domain}}, {{project_pitch}}

Return ONLY valid JSON:
{{"1":{{"subject":"...","body":"..."}},"2":{{...}},"3":{{...}},"4":{{...}}}}
"""
    try:
        import json as _json

        rules_payload = _json.dumps(
            {str(k): v for k, v in fallback.items()}, ensure_ascii=False
        )
        result = complete(prompt, company, rules_fallback=rules_payload)
        data = extract_json_object(result.text) if result.ok else None
        if not data:
            return fallback, "rules"
        out: dict[int, dict[str, str]] = {}
        for step in range(1, 5):
            t = data.get(str(step)) or data.get(step)
            if not t or not t.get("subject") or not t.get("body"):
                out[step] = fallback[step]
            else:
                out[step] = {
                    "subject": str(t["subject"]).strip(),
                    "body": str(t["body"]).strip(),
                }
        return out, result.provider if result.provider != "none" else "rules"
    except Exception:
        return fallback, "rules"


def compose_step_email(
    step: int,
    lead: dict,
    company: dict,
    project: dict,
    *,
    use_llm: bool = True,
) -> tuple[str, str, str]:
    """
    Compose subject/body for a sequence step.
    Returns (subject, body, reasoning_note).
    """
    subject, body = render_x_email(step, lead, company, project)
    reasoning = f"Rendered project template step {step} for {project.get('name')}"

    scope = (project.get("scope") or "").strip()
    if not use_llm or not scope:
        return subject, body, reasoning + " (rules)"

    pack = build_context_pack(project=project, lead=lead)
    patterns = patterns_for_prompt(lead=lead, project=project)

    prompt = f"""Refine this outreach email for the lead below. Keep merge fields already filled.
Stay faithful to PROJECT SCOPE. Return ONLY JSON: {{"subject":"...","body":"...","reasoning":"one sentence"}}

CONTEXT PACK:
{pack}

{patterns}

PROJECT SCOPE:
{scope}

Project type: {project.get('project_type')}
Tone: {project.get('tone_notes') or ''}

Lead: {json.dumps({k: lead.get(k) for k in ('company_name','contact_name','email','state','role_or_title','notes','remarks','sales_stage','crm_status')}, ensure_ascii=False)}

Draft subject: {subject}
Draft body:
{body}
"""
    try:
        import json as _json

        rules_payload = _json.dumps(
            {"subject": subject, "body": body, "reasoning": reasoning + " (rules)"},
            ensure_ascii=False,
        )
        result = complete(prompt, company, rules_fallback=rules_payload)
        data = extract_json_object(result.text) if result.text else None
        if not data:
            return subject, body, reasoning + " (rules — no LLM)"
        subj = str(data.get("subject") or subject).strip()
        bod = str(data.get("body") or body).strip()
        reason = str(data.get("reasoning") or reasoning).strip()[:240]
        return subj, bod, f"{result.provider}: {reason}"
    except Exception:
        return subject, body, reasoning + " (llm error → rules)"


def classify_reply_sentiment(text: str) -> dict[str, str]:
    """Extend bot intents with simple sentiment + intent labels."""
    from ..bot import classify_reply

    intent = classify_reply(text)
    t = (text or "").lower()
    if intent == "opt_out":
        sentiment = "negative"
    elif intent in ("positive", "escalate", "referral"):
        sentiment = "positive"
    elif any(w in t for w in ("angry", "lawsuit", "spam", "harass")):
        sentiment = "negative"
    else:
        sentiment = "neutral"
    return {"intent": intent, "sentiment": sentiment}


def compose_reply(
    lead: dict,
    inbound_text: str,
    company: dict,
    project: dict,
    *,
    intent: str = "",
) -> tuple[str, str, str]:
    """
    Draft a reply using project scope. Returns (subject, body, reasoning).
    Falls back to empty strings when escalate / no auto body needed.
    """
    from ..bot import handle_reply

    base = handle_reply(lead, inbound_text, company)
    intent = intent or base.intent
    labels = classify_reply_sentiment(inbound_text)
    reasoning = (
        f"Intent={labels['intent']}, sentiment={labels['sentiment']}; "
        f"project={project.get('name')}"
    )

    if intent == "escalate":
        return "", "", reasoning + " — escalate to owner (no auto body)"

    subject = base.reply_subject
    body = base.reply_body
    scope = (project.get("scope") or "").strip()
    if not scope or not body:
        if scope and body and "PROJECT SCOPE" not in body:
            pitch = re.split(r"[.\n]", scope)[0].strip()[:140]
            if pitch:
                body = body.replace(
                    f"Thanks for getting back to me",
                    f"Thanks for getting back to me — we work on: {pitch}",
                    1,
                )
                reasoning += " | scope phrase injected (rules)"
        return subject, body, reasoning

    pack = build_context_pack(project=project, lead=lead, extra_snippets=[inbound_text])
    patterns = patterns_for_prompt(lead=lead, project=project)

    prompt = f"""You handle inbound replies for a lead-conversion project.
Project type: {project.get('project_type')}

CONTEXT PACK:
{pack}

{patterns}

PROJECT SCOPE:
{scope}

Classified intent: {intent}
Sentiment: {labels['sentiment']}
Lead: {lead.get('company_name')} <{lead.get('email')}>
Their message:
{inbound_text}

Draft a short professional reply. If intent is opt_out, confirm removal politely.
Return ONLY JSON: {{"subject":"...","body":"...","reasoning":"one sentence"}}
"""
    try:
        import json as _json

        rules_payload = _json.dumps(
            {"subject": subject, "body": body, "reasoning": reasoning + " (rules)"},
            ensure_ascii=False,
        )
        result = complete(prompt, company, rules_fallback=rules_payload)
        data = extract_json_object(result.text) if result.text else None
        if not data:
            return subject, body, reasoning + " (rules — no LLM)"
        return (
            str(data.get("subject") or subject).strip(),
            str(data.get("body") or body).strip(),
            f"{result.provider}: {str(data.get('reasoning') or reasoning).strip()[:240]}",
        )
    except Exception:
        return subject, body, reasoning + " (llm error)"


def preview_templates(project: dict, company: dict) -> list[tuple[int, str, str]]:
    """Render steps 1–4 against a sample lead for UI preview."""
    sample = {
        "contact_name": "Alex",
        "company_name": "Sample Co",
        "state": "FL",
        "lane_or_region": "Southeast",
        "role_or_title": "Purchasing",
    }
    ensure_templates(project)
    out = []
    for step in range(1, 5):
        subj, body = render_x_email(step, sample, company, project)
        out.append((step, subj, body))
    return out


def agent_chat_about_project(
    message: str,
    company: dict,
    project: dict,
    *,
    lead: Optional[dict] = None,
    history: Optional[list[dict[str, str]]] = None,
) -> tuple[str, str]:
    """Return (reply_text, provider)."""
    from ..llm import chat

    pack = build_context_pack(project=project, lead=lead)
    patterns = patterns_for_prompt(lead=lead, project=project)
    system = (
        "You are the Lead-for-X project agent. Be concise.\n\n"
        f"CONTEXT PACK:\n{pack}\n"
    )
    if patterns:
        system += f"\n{patterns}\n"
    msgs = list(history or [])
    msgs.append({"role": "user", "content": message})
    result = chat(msgs, company, system=system)
    if result.ok:
        return result.text.strip(), result.provider
    return (
        f"(Rules) Project **{project.get('name')}** — scope length "
        f"{len(project.get('scope') or '')} chars. No LLM available "
        f"({result.error or 'none'}). Install Ollama or set Gemini/Groq.",
        "rules",
    )
