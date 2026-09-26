"""Lead-for-X email templates — per-project 4-step sequence + scope-driven generation."""
from __future__ import annotations

import re
from typing import Any

# Shared cadence with shipper/carrier engines
SEQUENCE_SCHEDULE_DAYS = {1: 0, 2: 4, 3: 9, 4: 16}


def _domain_from_scope(scope: str, project_type: str) -> dict[str, str]:
    """Pull plain-language domain cues from Project Scope for rule-based templates."""
    text = (scope or "").strip()
    low = text.lower()
    words = re.findall(r"[a-zA-Z][a-zA-Z\-']{2,}", text)
    # Prefer early noun phrases as the "offer"
    offer = "your opportunity"
    for w in (
        "shrimp",
        "seafood",
        "dairy",
        "produce",
        "freight",
        "software",
        "saas",
        "real estate",
        "insurance",
        "equipment",
        "parts",
        "wholesale",
        "retail",
        "import",
        "export",
    ):
        if w in low:
            offer = w
            break
    if offer == "your opportunity" and words:
        # First capitalized multi-word hint or first two content words
        offer = " ".join(words[:3]).lower()

    role = "buyer" if project_type == "buyer" else "seller" if project_type == "seller" else "partner"
    counterpart = {
        "buyer": "sellers / suppliers",
        "seller": "buyers / customers",
        "partner": "decision-makers",
    }.get(role, "decision-makers")

    # Extract a short "what we do" line from first sentence of scope
    first = re.split(r"[.\n]", text)[0].strip() if text else ""
    if len(first) > 160:
        first = first[:157] + "..."
    pitch = first or f"We help connect {role}s around {offer}."

    return {
        "offer": offer,
        "role": role,
        "counterpart": counterpart,
        "pitch": pitch,
        "domain": offer,
    }


def default_templates_for_scope(
    scope: str,
    project_type: str = "buyer",
    tone_notes: str = "",
) -> dict[int, dict[str, str]]:
    """Solid rule-based 4-email set molded by scope keywords (no API required)."""
    d = _domain_from_scope(scope, project_type)
    tone = (tone_notes or "").strip()
    tone_line = f"\nTone note for us: {tone}\n" if tone else ""

    if project_type == "buyer":
        intro_goal = f"I'm looking for reliable {d['counterpart']} who can supply {d['offer']}"
        value = (
            f"- Clear volume / quality expectations for {d['offer']}\n"
            f"- Direct conversation — no endless RFQ runaround\n"
            f"- Fast yes/no so neither side wastes time"
        )
        ask = "If you sell or source this, I'd like 10 minutes to see if specs and volume line up."
    elif project_type == "seller":
        intro_goal = f"I'm reaching out to {d['counterpart']} who may need {d['offer']}"
        value = (
            f"- Straightforward offer on {d['offer']}\n"
            f"- One point of contact for quotes and follow-through\n"
            f"- Happy to share samples / specs / pricing on a short call"
        )
        ask = "If you buy or influence purchasing here, can we book 10 minutes?"
    else:
        intro_goal = f"I'm building partnerships around {d['offer']}"
        value = (
            f"- Clear fit check against your goals\n"
            f"- Direct, respectful outreach — no spam blasts\n"
            f"- Easy opt-out anytime"
        )
        ask = "If this is relevant, I'd like a brief intro call."

    return {
        1: {
            "subject": "{domain} — intro for {company_name}",
            "body": f"""Hi {{contact_name}},

I'm {{my_name}} with {{my_company}}. {intro_goal}.

{{project_pitch}}
{tone_line}
What a good fit usually looks like:
{value}

{ask}

{{my_name}}
{{my_company}}
{{my_phone}}
{{website}}

{{unsubscribe_note}}""",
        },
        2: {
            "subject": "Following up — {domain} / {company_name}",
            "body": f"""Hi {{contact_name}},

Following up on my note about {d['offer']} — inboxes get crowded, so I'll keep this short.

Still interested in connecting with the right person at {{company_name}} on {d['offer']}.
If timing is off, a quick "not now" or a better contact name is perfect.

{{my_name}} | {{my_phone}}
{{my_company}}

{{unsubscribe_note}}""",
        },
        3: {
            "subject": "Quick question on {domain}",
            "body": f"""Hi {{contact_name}},

Last push from my side on {d['offer']}, then I'll leave the ball with you.

{{project_pitch}}

If {{company_name}} is open to a short conversation — or you can point me to the right {d['role']} contact — reply here or call {{my_phone}}.

{{my_name}}
{{my_company}}

{{unsubscribe_note}}""",
        },
        4: {
            "subject": "Closing the loop — {domain}",
            "body": f"""Hi {{contact_name}},

I don't want to keep filling your inbox. This is my last note for now on {d['offer']}.

I'll keep {{company_name}} on file. If anything changes, my direct line stays open: {{my_phone}}.

{{my_name}}
{{my_company}}

{{unsubscribe_note}}""",
        },
    }


def ensure_templates(project: dict) -> dict[int, dict[str, str]]:
    tmpl = project.get("templates") or {}
    if isinstance(tmpl, dict) and all(k in tmpl for k in (1, 2, 3, 4)):
        return {int(k): v for k, v in tmpl.items()}
    generated = default_templates_for_scope(
        project.get("scope") or project.get("name") or "",
        project.get("project_type") or "buyer",
        project.get("tone_notes") or "",
    )
    # merge any partial overrides
    for k, v in (tmpl or {}).items():
        generated[int(k)] = v
    return generated


def render_x_email(
    step: int,
    lead: dict,
    company: dict,
    project: dict,
) -> tuple[str, str]:
    templates = ensure_templates(project)
    if step not in templates:
        raise KeyError(f"No template for step {step}")
    tmpl = templates[step]
    d = _domain_from_scope(
        project.get("scope") or "",
        project.get("project_type") or "buyer",
    )
    lane = lead.get("lane_or_region") or ", ".join(
        p for p in [lead.get("county", ""), lead.get("state", "")] if p
    )
    pitch = d["pitch"]
    merge = {
        "contact_name": lead.get("contact_name") or "there",
        "company_name": lead.get("company_name") or "your company",
        "lane_or_region": lane or company.get("origin_area", "your region"),
        "domain": d["domain"],
        "offer": d["offer"],
        "project_pitch": pitch,
        "project_name": project.get("name") or "",
        "project_type": project.get("project_type") or "",
        "role_or_title": lead.get("role_or_title") or "",
        "my_company": company.get("my_company", ""),
        "my_name": company.get("my_name", ""),
        "my_phone": company.get("my_phone", ""),
        "my_email": company.get("my_email", ""),
        "my_mc": company.get("my_mc", ""),
        "website": company.get("website", ""),
        "unsubscribe_note": company.get("unsubscribe_note", ""),
    }

    def _fmt(s: str) -> str:
        try:
            return s.format(**merge)
        except KeyError:
            # tolerate unknown placeholders
            out = s
            for k, v in merge.items():
                out = out.replace("{" + k + "}", str(v))
            return out

    return _fmt(tmpl["subject"]), _fmt(tmpl["body"])


def apply_generated_templates(project: dict, templates: dict[int, dict[str, str]]) -> dict:
    """Return project-shaped templates dict ready to save."""
    out: dict[int, dict[str, str]] = {}
    for step in range(1, 5):
        t = templates.get(step) or templates.get(str(step))  # type: ignore[arg-type]
        if not t:
            continue
        out[step] = {
            "subject": str(t.get("subject") or "").strip(),
            "body": str(t.get("body") or "").strip(),
        }
    return out
