"""Email templates — owner-operator / carrier recruiting under LogixTrek MC."""
from __future__ import annotations

TEMPLATES = {
    1: {
        "subject": "Lease-on under {my_mc} — earn toward $40k gross with {my_company}",
        "body": """Hi {contact_name},

I'm reaching out from {my_company} ({my_mc} / {my_dot}). We're onboarding a small number of owner-operators to run under our authority — so you can haul and earn without carrying the full authority / compliance load alone.

What we offer lease-on carriers:
- Run under our MC with dispatch support
- Clear path toward ~$40k gross (lane + equipment dependent — we'll talk numbers honestly on a call)
- Straightforward settlement, no broker games on your side
- Equipment focus: {equipment}

I found {company_name}{mc_line} while looking for solid operators in {lane_or_region}. If you're open to lease-on / owner-operator work under a reputable MC, I'd like 10 minutes to see if we're a fit.

{my_name}
{my_company}
{my_phone}
{website}

{unsubscribe_note}""",
    },
    2: {
        "subject": "Following up — owner-operator seats under {my_mc}",
        "body": """Hi {contact_name},

Quick follow-up from {my_company}. We're still filling a few owner-operator seats under {my_mc}.

Operators who lease on with us usually want:
- Steady freight without hunting boards alone every day
- A clean authority home (we handle the MC-side compliance)
- Transparent gross potential — we talk ~$40k gross targets openly

If timing is bad, just tell me — or point me to the right person at {company_name}.

{my_name} | {my_phone}
{my_company} · {my_mc}

{unsubscribe_note}""",
    },
    3: {
        "subject": "Still hiring O/Os under {my_company} authority",
        "body": """Hi {contact_name},

Last push from my side, then I'll leave the ball in your court.

If you've been thinking about leasing onto an MC instead of running authority solo (or sitting between loads), {my_company} is actively onboarding owner-operators now. We keep the roster small on purpose — better freight, better communication.

Reply "interested" or call {my_phone} and I'll walk you through equipment, lanes, and realistic gross toward the $40k range.

{my_name}
{my_company} | {my_mc} / {my_dot}

{unsubscribe_note}""",
    },
    4: {
        "subject": "Keeping the door open — {my_company} lease-on",
        "body": """Hi {contact_name},

I won't keep filling your inbox. This is my last note for now.

If you or another operator at {company_name} wants to lease on under {my_mc} later, my direct line stays open: {my_phone}. Happy to explain the program, settlements, and gross expectations anytime.

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
