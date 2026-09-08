"""
End-to-end Find & Vet — wires Claude handoff discover_leads into our pipeline.
"""
from __future__ import annotations

from typing import Any

from .lead_discovery_agent import discover_leads, paca_manual_search_instructions
from .vetting import filter_vetted


# re-export for UI
__all__ = [
    "find_and_vet_shippers",
    "paca_manual_search_instructions",
]


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
    Returns candidates / vetted / qualified using Places + CSE + Gemini.
    enrich_websites is handled inside discover_leads.
    """
    config = {
        "google_places_api_key": (company.get("google_places_api_key") or "").strip(),
        "google_cse_api_key": (company.get("google_cse_api_key") or "").strip(),
        "google_cse_id": (company.get("google_cse_id") or "").strip(),
        "gemini_api_key": (company.get("gemini_api_key") or "").strip(),
        "use_demo": use_demo,
    }
    # county currently folded into location via zip/state in agent
    _ = county
    _ = enrich_websites

    equipment = company.get("equipment") or "53' Reefer"
    leads = discover_leads(
        state=state,
        zip_code=zip_code,
        freight_type=freight_type,
        equipment=equipment,
        config=config,
        max_per_source=15,
        progress_cb=progress_cb,
    )

    # filter_vetted uses vet_score 1-10
    qualified = filter_vetted(leads, min_score=min_score, include_maybe=True)
    rejected = [v for v in leads if (v.get("vet_status") or "") == "reject"]

    return {
        "candidates": leads,
        "vetted": leads,
        "qualified": qualified,
        "rejected_count": len(rejected),
        "used_demo": bool(use_demo or not config["google_places_api_key"]),
        "has_places_key": bool(config["google_places_api_key"]),
        "has_gemini": bool(config["gemini_api_key"]),
        "has_cse": bool(config["google_cse_api_key"] and config["google_cse_id"]),
        "paca_hint": paca_manual_search_instructions(zip_code or state or "your state"),
    }
