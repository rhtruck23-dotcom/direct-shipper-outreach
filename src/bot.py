"""Logistics specialist bot — classifies replies and drafts safe responses."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


OPT_OUT_PATTERNS = [
    r"\bstop\b",
    r"\bunsubscribe\b",
    r"\bopt[\s-]?out\b",
    r"\bnot interested\b",
    r"\bremove me\b",
    r"\bdo not (email|contact)\b",
    r"\bno thanks\b",
    r"\bdon't contact\b",
]

ESCALATE_PATTERNS = [
    r"\brate\b",
    r"\bpricing\b",
    r"\bprice\b",
    r"\bper mile\b",
    r"\ball[\s-]?in\b",
    r"\bcontract\b",
    r"\bmsa\b",
    r"\binsurance\b",
    r"\bcoi\b",
    r"\bcertificate\b",
    r"\bonboard",
    r"\bpacket\b",
    r"\bw\-?9\b",
    r"\bload (today|tonight|tomorrow|now)\b",
    r"\bneed (a )?truck\b",
    r"\bavailable (today|tomorrow)\b",
    r"\bcommit",
    r"\bbook (it|the load)\b",
    r"\bhow much\b",
    r"\bquote\b",
]

POSITIVE_PATTERNS = [
    r"\binterested\b",
    r"\btell me more\b",
    r"\bsend (me )?(info|details|packet)\b",
    r"\bwho (should|do) i (talk|speak)\b",
    r"\bcall me\b",
    r"\blet'?s talk\b",
    r"\byes\b",
    r"\bsounds good\b",
]

REFERRAL_PATTERNS = [
    r"\bwrong (person|contact)\b",
    r"\bnot the right (person|contact)\b",
    r"\btalk to\b",
    r"\breach out to\b",
    r"\bforward(ed)? to\b",
    r"\bour (logistics|transportation|shipping) (manager|team|dept)",
]

# Routine — auto-handle, no owner escalate
OOO_PATTERNS = [
    r"\bout of (the )?office\b",
    r"\booo\b",
    r"\bon (vacation|leave|pto|holiday)\b",
    r"\baway (from|until)\b",
    r"\bautomatic reply\b",
    r"\bauto[\s-]?reply\b",
    r"\bi will be (out|away)\b",
]

THANKS_ONLY_PATTERNS = [
    r"^(thanks|thank you|thx|ty)[\s!.]*$",
    r"^(thanks|thank you)[,!]?\s+(got it|received|noted)[\s!.]*$",
]

TIMING_PATTERNS = [
    r"\b(not right now|not at (this|the) (time|moment)|maybe later|check back|reach out in)\b",
    r"\b(next quarter|after (the )?holidays|in a few months)\b",
    r"\bcircling back later\b",
]

INFO_REQUEST_PATTERNS = [
    r"\b(where are you based|what (lanes|equipment) do you (run|haul))\b",
    r"\b(send|share) (your )?(authority|mc|dot|website)\b",
    r"\bcompany (info|snapshot|overview)\b",
]

ALREADY_COVERED_PATTERNS = [
    r"\b(already have (a )?(carrier|broker|provider)|we('re| are) all set|not looking)\b",
    r"\bhappy with (our|current) (carrier|provider)\b",
]


@dataclass
class BotDecision:
    intent: str  # opt_out | escalate | positive | referral | ooo | thanks | timing | info | covered | unclear
    auto_send: bool
    reply_subject: str
    reply_body: str
    escalate_to_owner: bool
    owner_alert: str
    stop_sequence: bool
    mark_positive: bool


def classify_reply(text: str) -> str:
    t = (text or "").lower().strip()
    for pat in OPT_OUT_PATTERNS:
        if re.search(pat, t):
            return "opt_out"
    for pat in ESCALATE_PATTERNS:
        if re.search(pat, t):
            return "escalate"
    for pat in OOO_PATTERNS:
        if re.search(pat, t):
            return "ooo"
    for pat in THANKS_ONLY_PATTERNS:
        if re.search(pat, t, flags=re.I):
            return "thanks"
    for pat in TIMING_PATTERNS:
        if re.search(pat, t):
            return "timing"
    for pat in ALREADY_COVERED_PATTERNS:
        if re.search(pat, t):
            return "covered"
    for pat in INFO_REQUEST_PATTERNS:
        if re.search(pat, t):
            return "info"
    for pat in REFERRAL_PATTERNS:
        if re.search(pat, t):
            return "referral"
    for pat in POSITIVE_PATTERNS:
        if re.search(pat, t):
            return "positive"
    return "unclear"


def handle_reply(lead: dict, inbound_text: str, company: dict[str, Any]) -> BotDecision:
    intent = classify_reply(inbound_text)
    contact = lead.get("contact_name") or "there"
    co = lead.get("company_name") or "your company"
    my = company.get("my_company", "our company")
    name = company.get("my_name", "Dispatch")
    phone = company.get("my_phone", "")
    email = company.get("my_email", "")
    mc = company.get("my_mc", "")
    dot = company.get("my_dot", "")
    web = company.get("website", "")
    equip = company.get("equipment", "")
    origin = company.get("origin_area", "")

    if intent == "opt_out":
        return BotDecision(
            intent=intent,
            auto_send=True,
            reply_subject=f"Re: Opt-out confirmed — {my}",
            reply_body=(
                f"Hi {contact},\n\n"
                f"Understood — I've removed {co} from our outreach list. "
                f"You won't receive further emails from us.\n\n"
                f"If anything changes in the future, you can always reach us at {phone}.\n\n"
                f"{name}\n{my}"
            ),
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=True,
            mark_positive=False,
        )

    if intent == "escalate":
        return BotDecision(
            intent=intent,
            auto_send=False,  # owner closes the deal
            reply_subject="",
            reply_body="",
            escalate_to_owner=True,
            owner_alert=(
                f"ESCALATE: {co} ({lead.get('email')}) replied with rates/contract/"
                f"load commitment language. You need to reply personally.\n\n"
                f"Their message:\n{inbound_text}"
            ),
            stop_sequence=True,
            mark_positive=True,
        )

    if intent == "ooo":
        return BotDecision(
            intent=intent,
            auto_send=False,  # no reply to auto-responder noise
            reply_subject="",
            reply_body="",
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=False,  # keep sequence; nudge next_contact later via agent
            mark_positive=False,
        )

    if intent == "thanks":
        return BotDecision(
            intent=intent,
            auto_send=True,
            reply_subject=f"Re: You're welcome — {my}",
            reply_body=(
                f"Hi {contact},\n\n"
                f"You're welcome — happy to help. If a lane or capacity question "
                f"comes up later, my direct line is {phone}.\n\n"
                f"{name}\n{my}"
            ),
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=True,
            mark_positive=True,
        )

    if intent == "timing":
        return BotDecision(
            intent=intent,
            auto_send=True,
            reply_subject=f"Re: Timing noted — {my}",
            reply_body=(
                f"Hi {contact},\n\n"
                f"Understood on timing — I'll pause outreach for now and check back later. "
                f"If anything opens up sooner, I'm at {phone} / {email}.\n\n"
                f"{name}\n{my}"
            ),
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=True,
            mark_positive=True,
        )

    if intent == "covered":
        return BotDecision(
            intent=intent,
            auto_send=True,
            reply_subject=f"Re: Thanks for letting me know — {my}",
            reply_body=(
                f"Hi {contact},\n\n"
                f"Appreciate the clarity — glad {co} is covered. I'll close the loop "
                f"on our side. If you ever need backup capacity, keep us in mind "
                f"({phone}).\n\n"
                f"{name}\n{my}"
            ),
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=True,
            mark_positive=False,
        )

    if intent == "info":
        return BotDecision(
            intent=intent,
            auto_send=True,
            reply_subject=f"Re: {my} — quick company snapshot",
            reply_body=(
                f"Hi {contact},\n\n"
                f"Happy to share a quick snapshot of {my}:\n"
                f"- Based: {origin}\n"
                f"- Equipment: {equip}\n"
                f"- Authority: {mc} / {dot}\n"
                f"- Website: {web}\n"
                f"- Direct: {phone} | {email}\n\n"
                f"Happy to dig into a specific lane whenever useful.\n\n"
                f"{name}\n{my}"
            ),
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=False,
            mark_positive=True,
        )

    if intent == "referral":
        return BotDecision(
            intent=intent,
            auto_send=True,
            reply_subject=f"Re: Right contact at {co}",
            reply_body=(
                f"Hi {contact},\n\n"
                f"Thanks for the redirect — much appreciated.\n\n"
                f"Could you share the best name, email, and/or phone for the person who "
                f"handles inbound/outbound freight or carrier onboarding at {co}? "
                f"I'll reach out to them directly and won't keep bothering you.\n\n"
                f"{name}\n{my} | {phone}\nMC# {mc}"
            ),
            # Soft notify via note/task only when referral names arrive — not escalate
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=True,
            mark_positive=True,
        )

    if intent == "positive":
        return BotDecision(
            intent=intent,
            auto_send=True,
            reply_subject=f"Re: {my} — capacity & company snapshot",
            reply_body=(
                f"Hi {contact},\n\n"
                f"Thanks for getting back to me — glad this might be a fit.\n\n"
                f"Quick snapshot of {my}:\n"
                f"- Equipment: {equip}\n"
                f"- Authority: {mc} / {dot}\n"
                f"- Website: {web}\n"
                f"- Direct line: {phone} | {email}\n\n"
                f"Happy to hop on a short call or look at a specific lane when you're ready. "
                f"What works best for you?\n\n"
                f"{name}\n{my}"
            ),
            # Capability snapshot is safe — escalate only if they later ask rates
            escalate_to_owner=False,
            owner_alert="",
            stop_sequence=True,
            mark_positive=True,
        )

    # unclear — acknowledge without owner escalate (agent/task can follow up)
    return BotDecision(
        intent=intent,
        auto_send=True,
        reply_subject=f"Re: Following up — {my}",
        reply_body=(
            f"Hi {contact},\n\n"
            f"Thanks for the reply. I want to make sure I help the right way — "
            f"are you the best person for freight/logistics at {co}, or should I "
            f"connect with someone else on your team?\n\n"
            f"Either way, my direct line is {phone} if a quick call is easier.\n\n"
            f"{name}\n{my}"
        ),
        escalate_to_owner=False,
        owner_alert="",
        stop_sequence=True,
        mark_positive=True,
    )
