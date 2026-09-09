"""Stage labels + colors for the leads list."""
from __future__ import annotations

# status -> (label, background hex, text hex)
STAGE_STYLE = {
    "not_started": ("Not started", "#E8E8E8", "#333333"),
    "emailed_1": ("Email 1 sent", "#D6EAF8", "#1A5276"),
    "emailed_2": ("Email 2 sent", "#AED6F1", "#1A5276"),
    "emailed_3": ("Email 3 sent", "#F9E79F", "#7D6608"),
    "emailed_4": ("Email 4 done", "#D7BDE2", "#4A235A"),
    "responded": ("Responded", "#ABEBC6", "#145A32"),
    "converted": ("Converted ★", "#27AE60", "#FFFFFF"),
    "do_not_contact": ("Do not contact", "#F5B7B1", "#7B241C"),
}

STAGE_ORDER = [
    "not_started",
    "emailed_1",
    "emailed_2",
    "emailed_3",
    "emailed_4",
    "responded",
    "converted",
    "do_not_contact",
]


def stage_label(status: str) -> str:
    return STAGE_STYLE.get(status or "not_started", ("Unknown", "#eee", "#000"))[0]


def stage_colors(status: str) -> tuple[str, str]:
    _, bg, fg = STAGE_STYLE.get(status or "not_started", ("Unknown", "#eee", "#000"))
    return bg, fg


def contact_indicator(lead: dict) -> str:
    """Short badge for list view."""
    status = lead.get("status") or "not_started"
    if status == "do_not_contact":
        return "🚫 Never again"
    if status == "converted":
        return "✅ Customer"
    if status == "responded":
        return "📞 Needs you"
    if lead.get("active_sequence"):
        step = int(lead.get("last_step_sent") or 0)
        return f"📨 Sequence · step {step}/4"
    if int(lead.get("last_step_sent") or 0) > 0 or lead.get("first_contacted"):
        return "📋 Contacted before"
    return "⚪ New"


def already_contacted(lead: dict) -> bool:
    return bool(
        lead.get("first_contacted")
        or int(lead.get("last_step_sent") or 0) > 0
        or (lead.get("status") or "not_started") != "not_started"
    )


def may_start_outreach(lead: dict, force: bool = False) -> tuple[bool, str]:
    """Block re-bothering people. Returns (ok, reason)."""
    status = lead.get("status") or "not_started"
    if status == "do_not_contact":
        return False, "Marked Do Not Contact — will never email again"
    if status == "converted":
        return False, "Already converted — use remarks if you need a note"
    if not (lead.get("email") or "").strip():
        return False, "No email on file"
    if force:
        return True, "OK (forced)"
    if status == "responded":
        return False, "They already replied — use Inbox Bot / call them (or Force restart)"
    if already_contacted(lead) and not lead.get("active_sequence"):
        if int(lead.get("last_step_sent") or 0) >= 4:
            return False, "Finished 4 emails with no reply — Force restart only if you really want"
        if status.startswith("emailed_"):
            return False, "Already contacted — activate only with Force restart if needed"
    return True, "OK"


# Carrier onboarding deal stages (after they reply — separate from email status)
CARRIER_DEAL_STAGES = {
    "": ("—", "#E8E8E8", "#333"),
    "applied": ("Applied / Responded", "#D5F5E3", "#145A32"),
    "packet_sent": ("Packet sent", "#D6EAF8", "#1A5276"),
    "docs_reviewed": ("Docs under review", "#FCF3CF", "#7D6608"),
    "signed_onboarded": ("Signed & onboarded", "#27AE60", "#FFFFFF"),
    "not_qualified": ("Not qualified", "#F5B7B1", "#7B241C"),
}


def carrier_deal_label(stage: str) -> str:
    return CARRIER_DEAL_STAGES.get(stage or "", ("—", "#eee", "#000"))[0]


def set_carrier_deal_stage(lead: dict, stage: str) -> None:
    """Advance carrier onboarding. signed_onboarded also marks status=converted."""
    stage = (stage or "").strip()
    if stage and stage not in CARRIER_DEAL_STAGES:
        raise ValueError(f"Unknown carrier deal stage: {stage}")
    lead["deal_stage"] = stage
    if stage == "signed_onboarded":
        lead["status"] = "converted"
        lead["active_sequence"] = False
        lead["responded"] = True
    elif stage == "applied":
        lead["status"] = "responded"
        lead["active_sequence"] = False
        lead["responded"] = True
    elif stage == "not_qualified":
        lead["active_sequence"] = False

