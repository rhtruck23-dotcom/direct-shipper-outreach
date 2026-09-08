"""Multi-query Google Places discovery for likely direct shippers."""
from __future__ import annotations

from typing import Any

from .geo_hubs import hubs_for_state
from .places import FREIGHT_QUERIES, demo_places_results, search_places

# Extra shipper-oriented queries beyond the basic freight set
EXTRA_QUERIES = {
    "Reefer": [
        "produce packer",
        "fresh produce shipper",
        "food processing plant",
        "refrigerated warehouse",
        "grocery distribution center",
    ],
    "Dry Van": [
        "wholesale food distributor",
        "beverage warehouse",
        "CPG manufacturer",
        "paper wholesale distributor",
    ],
    "Box Truck": [
        "regional food distributor",
        "wholesale club supplier",
        "building supply warehouse",
    ],
}


def discover_candidates(
    api_key: str,
    freight_type: str = "Reefer",
    state: str = "",
    county: str = "",
    zip_code: str = "",
    max_per_query: int = 20,
    max_total: int = 200,
    use_demo: bool = False,
) -> list[dict[str, Any]]:
    """
    Run several shipper-type searches and merge/dedupe.

    Statewide (state set, zip empty): expands across metro hubs for that state.
    Zip/county set: focused local search (faster, fewer results).

    Does NOT invent emails. Website/phone come from Places.
    Realistic ceiling from Places is typically hundreds per state, not thousands
    of email-ready leads — enrichment fills emails after.
    """
    if use_demo or not api_key:
        demo = demo_places_results(freight_type, state, zip_code)
        for d in demo:
            d["discovery_query"] = "demo"
            d["source"] = "demo"
        return demo

    terms = list(FREIGHT_QUERIES.get(freight_type, FREIGHT_QUERIES["Reefer"]))
    terms += EXTRA_QUERIES.get(freight_type, [])

    # Build location targets
    locations: list[str] = []
    if zip_code.strip():
        locations = [" ".join(b for b in [county, state, zip_code] if b)]
    elif county.strip():
        locations = [f"{county} {state}".strip()]
    elif state.strip():
        locations = hubs_for_state(state)
        # also one whole-state pass
        locations = [f"{state} state"] + locations
    else:
        locations = [""]

    seen: dict[str, dict] = {}
    errors: list[str] = []
    max_total = max(20, min(int(max_total or 200), 800))
    max_per_query = max(5, min(int(max_per_query or 20), 60))

    for location in locations:
        for term in terms:
            if len(seen) >= max_total:
                break
            query = f"{term} in {location}" if location else term
            try:
                batch = search_places(
                    api_key,
                    freight_type=freight_type,
                    state=state,
                    county=county,
                    zip_code=zip_code,
                    custom_query=query,
                    max_results=min(max_per_query, max_total - len(seen)),
                    max_pages=3,
                )
                for row in batch:
                    key = (row.get("company_name") or "").lower().strip()
                    phone = (row.get("phone") or "").strip()
                    dedupe = key or phone or row.get("id") or ""
                    if not dedupe:
                        continue
                    # Prefer matching requested state when known
                    row_st = (row.get("state") or "").upper()[:2]
                    want = (state or "").upper()[:2]
                    if want and row_st and row_st != want:
                        continue
                    if dedupe not in seen:
                        row["discovery_query"] = query
                        row["source"] = "google_places"
                        seen[dedupe] = row
            except Exception as e:
                errors.append(f"{term}@{location}: {e}")
        if len(seen) >= max_total:
            break

    results = list(seen.values())[:max_total]
    if errors and not results:
        raise RuntimeError("; ".join(errors[:3]))
    return results
