"""Campaign runner — send due emails for activated leads."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .emailer import send_email
from .leads import lead_key, persist_lead_tracking
from .schedule import next_action_for_lead
from .stages import may_start_outreach
from .storage import bump_contact
from .templates import render_email


def run_due_emails(
    leads: list[dict],
    company: dict[str, Any],
    only_keys: list[str] | None = None,
) -> list[dict]:
    today = datetime.now()
    keyset = {k.lower() for k in only_keys} if only_keys else None
    results = []

    # When autopilot + LIVE, share mailbox/soft caps with the autonomy pass
    share_caps = bool(company.get("autonomy_autopilot") and company.get("send_live_emails"))
    cap_snap = None
    if share_caps:
        try:
            from .capacity import can_send_under_shared_caps

            ok_cap, reason, cap_snap = can_send_under_shared_caps(company)
            if not ok_cap:
                return [
                    {
                        "lead": "(pool)",
                        "ok": False,
                        "error": reason
                        or "Shared daily capacity exhausted — resumes next day",
                        "capacity": cap_snap,
                        "mailbox_exhausted": True,
                    }
                ]
        except Exception:
            share_caps = False

    for lead in leads:
        if keyset is not None and lead_key(lead) not in keyset:
            continue

        # Hard stop: never email DNC
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

        # Re-check shared caps before each send when autopilot+live
        if share_caps:
            try:
                from .capacity import can_send_under_shared_caps

                ok_cap, reason, cap_snap = can_send_under_shared_caps(company)
                if not ok_cap:
                    results.append(
                        {
                            "lead": lead.get("company_name"),
                            "ok": False,
                            "error": reason or "Shared daily capacity exhausted",
                            "mailbox_exhausted": True,
                            "capacity": cap_snap,
                        }
                    )
                    break
            except Exception:
                pass

        subject, body = render_email(step, lead, company)
        send_result = send_email(
            lead["email"],
            subject,
            body,
            company,
            meta={
                "type": "sequence",
                "step": step,
                "lead_key": lead_key(lead),
                "company_name": lead.get("company_name"),
            },
        )

        if send_result.get("ok"):
            bump_contact(lead, step)
            conv = lead.get("conversation") or []
            conv.append(
                {
                    "at": today.isoformat(),
                    "direction": "outbound",
                    "step": step,
                    "subject": subject,
                    "body": body,
                    "mode": send_result.get("mode"),
                }
            )
            lead["conversation"] = conv
            # remark audit trail
            stamp = today.strftime("%Y-%m-%d")
            note = lead.get("remarks") or ""
            tag = f"Email {step} {stamp}"
            if tag not in note:
                lead["remarks"] = (note + f" | {tag}").strip(" |")

        results.append(
            {
                "lead": lead.get("company_name"),
                "email": lead.get("email"),
                "step": step,
                **send_result,
            }
        )

    persist_lead_tracking(leads)
    return results
