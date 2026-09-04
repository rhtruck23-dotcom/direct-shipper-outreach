"""Email templates for the 4-step direct-shipper sequence."""
from __future__ import annotations

TEMPLATES = {
    1: {
        "subject": "Reliable {freight_type} capacity for {company_name} — direct, no broker delay",
        "body": """Hi {contact_name},

I run {my_company}, a {equipment} carrier operating in and around {origin_area}. I came across {company_name} while researching {freight_type} shippers in {lane_or_region} and wanted to introduce myself directly.

I've been hauling {freight_type} for 4+ years and I'm looking to build a small number of direct shipping relationships — companies who want one dependable truck they can call, instead of whoever a broker assigns that week.

What that means for you:
- One point of contact — me, directly, not a rotating dispatcher
- Consistent on-time pickup/delivery with live GPS tracking available
- Full reefer temp compliance and food-safety documentation on request
- Rates negotiated once, honored every time — no last-minute broker games

If you handle inbound/outbound freight for {company_name}, I'd like 10 minutes on the phone to see if our lanes line up. No obligation — happy to just exchange info for when you need backup capacity.

MC# {my_mc} / DOT# {my_dot}
{website}

Best,
{my_name}
{my_company}
{my_phone}

{unsubscribe_note}""",
    },
    2: {
        "subject": "Following up — {freight_type} capacity in {lane_or_region}",
        "body": """Hi {contact_name},

Following up on my note from last week — I know inbound emails get buried, so I'll keep this short.

I have {equipment} capacity regularly available in {lane_or_region}, and I'm specifically trying to reduce how much freight I move through brokers by building 3-5 direct shipper relationships this quarter.

A few things shippers I work with tell me they value most:
- I answer my own phone
- I don't no-show or bail on committed loads
- Rate confirmations are simple, one page, no surprise deductions

If now isn't the right time, no worries — just let me know who the right contact is for freight/logistics at {company_name} and I'll follow up with them instead.

{my_name}
{my_company} | {my_phone}
MC# {my_mc}

{unsubscribe_note}""",
    },
    3: {
        "subject": "Quick question about your {freight_type} routing",
        "body": """Hi {contact_name},

Last try on my end, then I'll leave it to you to reach out if it's ever useful.

Most of the shippers I work with directly came from the same situation: tired of broker markups eating into their freight budget, and tired of a different driver/carrier every week with no accountability. Cutting the broker out usually saves the shipper money too — you're paying carrier rate instead of carrier rate + broker margin.

If {company_name} ever has a load that fell through last-minute, needs backup capacity during peak season, or you're open to a standing relationship for {lane_or_region} — I'm one call away.

{my_name}
{my_company} | {my_phone}
MC# {my_mc} / DOT# {my_dot}

{unsubscribe_note}""",
    },
    4: {
        "subject": "Closing the loop — keeping my info on file for {company_name}",
        "body": """Hi {contact_name},

I don't want to keep filling your inbox, so this is my last note for now.

I'll keep {company_name} on my list in case a fit comes up down the road. In the meantime, if you ever need a dependable {equipment} truck in {lane_or_region} — planned or last-minute — my direct line is below.

Wishing you a smooth peak season either way.

{my_name}
{my_company} | {my_phone}
MC# {my_mc}

{unsubscribe_note}""",
    },
}

# Days after first contact when each step becomes due
SEQUENCE_SCHEDULE_DAYS = {1: 0, 2: 4, 3: 9, 4: 16}


def render_email(step: int, lead: dict, company: dict) -> tuple[str, str]:
    tmpl = TEMPLATES[step]
    lane = lead.get("lane_or_region") or ", ".join(
        p for p in [lead.get("county", ""), lead.get("state", "")] if p
    )
    merge = {
        "contact_name": lead.get("contact_name") or "there",
        "company_name": lead.get("company_name", ""),
        "origin_area": company.get("origin_area", company.get("my_company", "")),
        "lane_or_region": lane or company.get("default_lanes", "your region"),
        "freight_type": lead.get("freight_type") or "freight",
        "my_company": company.get("my_company", ""),
        "my_name": company.get("my_name", ""),
        "my_phone": company.get("my_phone", ""),
        "my_mc": company.get("my_mc", ""),
        "my_dot": company.get("my_dot", ""),
        "equipment": company.get("equipment", ""),
        "website": company.get("website", ""),
        "unsubscribe_note": company.get("unsubscribe_note", ""),
    }
    return tmpl["subject"].format(**merge), tmpl["body"].format(**merge)
