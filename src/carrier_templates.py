"""Email templates — owner-operator / carrier recruiting under LogixTrek MC.

Earnings language stays general (no guaranteed $ figure) — walk real numbers on a call.
"""
from __future__ import annotations

TEMPLATES = {
    1: {
        "subject": "Lease on with {my_company} — keep your truck, drop the overhead",
        "body": """Hi {contact_name},

I'm {my_name} with {my_company}, and we're looking for a few more owner-operators to run under our authority (MC# {my_mc} / DOT# {my_dot}).

If you're tired of chasing your own authority paperwork, insurance renewals, and broker headaches, running under our MC means:
- You keep your truck; we handle the authority side, with dispatch support
- Freight focus: {equipment} lanes in {lane_or_region} and beyond
- No long-term lock-in just to talk — we'll walk through real pay and lanes on a call (results vary by hours, lanes, and equipment)

I found {company_name}{mc_line} while looking for solid operators. If you've got your own truck and a clean record, I'd like 10 minutes to see if this is a fit.

{my_name}
{my_company}
{my_phone}
{website}

{unsubscribe_note}""",
    },
    2: {
        "subject": "Following up — owner-operator spot with {my_company}",
        "body": """Hi {contact_name},

Following up on my note — figured it might have gotten buried.

Owner-operators who lease on with us usually care about:
- Who's actually running dispatch (a real person, not a call center)
- How pay actually works (we'll walk the cycle honestly)
- Whether there's real freight in their lanes, not just promises

If timing is bad, just tell me — or point me to the right person at {company_name}.

{my_name} | {my_phone}
{my_company} · {my_mc}

{unsubscribe_note}""",
    },
    3: {
        "subject": "Still onboarding O/Os under {my_company}",
        "body": """Hi {contact_name},

Last push from my side, then I'll leave the ball in your court.

If you've been thinking about leasing onto an MC instead of running authority solo (or sitting between loads), {my_company} is actively onboarding a small number of owner-operators now. We keep the roster small on purpose.

Reply "interested" or call {my_phone} and I'll walk equipment, lanes, and realistic pay — not a canned pitch.

{my_name}
{my_company} | {my_mc} / {my_dot}

{unsubscribe_note}""",
    },
    4: {
        "subject": "Keeping the door open — {my_company} lease-on",
        "body": """Hi {contact_name},

I won't keep filling your inbox. This is my last note for now.

If you or another operator at {company_name} wants to lease on under {my_mc} later, my direct line stays open: {my_phone}. Happy to explain the program anytime.

Wishing you safe miles either way.

{my_name}
{my_company}

{unsubscribe_note}""",
    },
}

SEQUENCE_SCHEDULE_DAYS = {1: 0, 2: 4, 3: 9, 4: 16}


def render_carrier_email(step: int, lead: dict, company: dict) -> tuple[str, str]:
    tmpl = TEMPLATES[step]
    lane = lead.get("lane_or_region") or ", ".join(
        p for p in [lead.get("county", ""), lead.get("state", "")] if p
    )
    mc = (lead.get("mc_number") or "").strip()
    mc_line = f" ({mc})" if mc else ""
    merge = {
        "contact_name": lead.get("contact_name") or "there",
        "company_name": lead.get("company_name") or "your company",
        "mc_line": mc_line,
        "lane_or_region": lane or company.get("origin_area", "your area"),
        "my_company": company.get("my_company", "LogixTrek LLC"),
        "my_name": company.get("my_name", ""),
        "my_phone": company.get("my_phone", ""),
        "my_mc": company.get("my_mc", "MC-1590829"),
        "my_dot": company.get("my_dot", "DOT-4146389"),
        "equipment": company.get("equipment", "53' Reefer / Dry Van"),
        "website": company.get("website", ""),
        "unsubscribe_note": company.get("unsubscribe_note", ""),
    }
    return tmpl["subject"].format(**merge), tmpl["body"].format(**merge)
