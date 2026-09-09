"""
Validate paste-dump leads before save — format checks + public-web enrich + logistics vet.

Does NOT scrape LinkedIn / ThomasNet / Yellow Pages.
Only uses: email heuristics, optional public company website, rule/Gemini vetting.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from .enrich import enrich_lead
from .vetting import llm_vet_batch, rule_vet_lead

EMAIL_RE = re.compile(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", re.I)
DISPOSABLE_DOMAINS = {
    "mailinator.com",
    "guerrillamail.com",
    "tempmail.com",
    "10minutemail.com",
    "yopmail.com",
    "trashmail.com",
}


def _email_ok(email: str) -> tuple[bool, str]:
    e = (email or "").strip().lower()
    if not e:
        return False, "Missing email"
    if not EMAIL_RE.match(e):
        return False, "Invalid email format"
    domain = e.split("@", 1)[-1]
    if domain in DISPOSABLE_DOMAINS:
        return False, f"Disposable inbox ({domain})"
    if domain in {"example.com", "test.com", "email.com", "domain.com"}:
        return False, "Placeholder domain"
    return True, "OK"


def validate_paste_leads(
    leads: list[dict],
    company: Optional[dict] = None,
    *,
    enrich_websites: bool = True,
    use_llm: bool = True,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> list[dict]:
    """
    Return copies with validation_* + vet_* fields filled.
    ready_for_outreach=True only when email format OK and vet_status != reject.
    """
    out: list[dict] = []
    for i, raw in enumerate(leads):
        lead = dict(raw)
        if progress_cb:
            progress_cb(f"Validating {i + 1}/{len(leads)}: {lead.get('company_name') or lead.get('email')}")

        if enrich_websites and (lead.get("website") or "").strip():
            try:
                lead = enrich_lead(lead)
            except Exception:
                pass

        out.append(lead)

    # Vet in batch (Gemini if key, else rules)
    if use_llm:
        vetted = llm_vet_batch(out, company=company)
    else:
        vetted = [rule_vet_lead(l) for l in out]

    final: list[dict] = []
    for lead, email_lead in zip(vetted, out):
        merged = {**email_lead, **lead}
        ok, email_note = _email_ok(merged.get("email") or "")
        vet_status = (merged.get("vet_status") or "weak").lower()
        ready = ok and vet_status != "reject"

        if not ok or vet_status == "reject":
            merged["validation_status"] = "blocked"
        elif vet_status == "qualified":
            merged["validation_status"] = "ready"
        else:
            merged["validation_status"] = "review"

        note_parts: list[str] = []
        if email_note != "OK":
            note_parts.append(email_note)
        if merged.get("vet_reason"):
            note_parts.append(str(merged["vet_reason"]))
        merged["validation_email_ok"] = ok
        merged["validation_ready"] = ready
        merged["validation_notes"] = " · ".join(note_parts) if note_parts else "Looks usable"

        rem = merged.get("remarks") or ""
        tag = f"Vet:{merged.get('vet_score', '?')}/{merged.get('vet_status', '')}"
        if tag not in rem:
            merged["remarks"] = (rem + " | " + tag).strip(" |")
        final.append(merged)
    return final


def split_validated(leads: list[dict]) -> dict[str, list[dict]]:
    ready = [l for l in leads if l.get("validation_ready")]
    blocked = [l for l in leads if not l.get("validation_ready")]
    qualified = [l for l in ready if (l.get("vet_status") or "") == "qualified"]
    return {"ready": ready, "blocked": blocked, "qualified": qualified, "all": leads}
