"""
End-to-end: discover → enrich emails → LLM/rules vet → qualified list.
"""
from __future__ import annotations

from typing import Any, Optional

from .discovery import discover_candidates
from .enrich import enrich_lead
from .vetting import filter_vetted, llm_vet_batch


def find_and_vet_shippers(
    company: dict,
    freight_type: str = "Reefer",
    state: str = "",
    county: str = "",
    zip_code: str = "",
    min_score: int = 6,
    enrich_websites: bool = True,
    use_demo: bool = False,
    progress_cb=None,
) -> dict[str, Any]:
    """
    Returns {
      candidates, vetted, qualified, rejected_count, method_notes
    }
    """

    def prog(msg: str):
        if progress_cb:
            progress_cb(msg)

    api_key = (company.get("google_places_api_key") or "").strip()
    prog("Searching Google Business / Places for shipper-type companies…")
    candidates = discover_candidates(
        api_key,
        freight_type=freight_type,
        state=state,
        county=county,
        zip_code=zip_code,
        use_demo=use_demo or not api_key,
    )
    prog(f"Found {len(candidates)} raw candidates. Enriching public websites…")

    enriched = []
    for i, c in enumerate(candidates):
        if enrich_websites and not use_demo:
            prog(f"Checking website {i+1}/{len(candidates)}: {c.get('company_name')}")
            enriched.append(enrich_lead(c))
        else:
            enriched.append(dict(c))

    prog("Running logistics vetting (LLM if key present, else rules)…")
    vetted = llm_vet_batch(enriched, company=company)
    qualified = filter_vetted(vetted, min_score=min_score, include_maybe=True)
    rejected = [v for v in vetted if (v.get("vet_status") or "") == "reject"]

    # Stamp remarks for pipeline memory
    for q in qualified:
        score = q.get("vet_score")
        reason = q.get("vet_reason") or ""
        q["remarks"] = f"Vetted score {score}/10 — {reason}"[:500]
        note = q.get("notes") or ""
        q["notes"] = (note + f" | vet:{q.get('vet_method')}").strip(" |")

    return {
        "candidates": candidates,
        "vetted": vetted,
        "qualified": qualified,
        "rejected_count": len(rejected),
        "used_demo": bool(use_demo or not api_key),
        "has_places_key": bool(api_key),
        "has_gemini": bool(
            (company.get("gemini_api_key") or "").strip()
        ),
    }
