"""Multi-query Google Places discovery for likely direct shippers."""
from __future__ import annotations

from typing import Any

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
    max_per_query: int = 10,
    use_demo: bool = False,
) -> list[dict[str, Any]]:
    """
    Run several shipper-type searches and merge/dedupe.
    Does NOT invent emails. Website/phone come from Places.
    """
    if use_demo or not api_key:
        demo = demo_places_results(freight_type, state, zip_code)
        for d in demo:
            d["discovery_query"] = "demo"
            d["source"] = "demo"
        return demo

    terms = list(FREIGHT_QUERIES.get(freight_type, FREIGHT_QUERIES["Reefer"]))
    terms += EXTRA_QUERIES.get(freight_type, [])
    location_bits = [b for b in [county, state, zip_code] if b]
    location = " ".join(location_bits)

    seen: dict[str, dict] = {}
    errors: list[str] = []

    for term in terms:
        query = f"{term} in {location}" if location else term
        try:
            batch = search_places(
                api_key,
                freight_type=freight_type,
                state=state,
                county=county,
                zip_code=zip_code,
                custom_query=query,
                max_results=max_per_query,
            )
            for row in batch:
                key = (row.get("company_name") or "").lower().strip()
                phone = (row.get("phone") or "").strip()
                dedupe = key or phone or row.get("id") or ""
                if not dedupe:
                    continue
                if dedupe not in seen:
                    row["discovery_query"] = query
                    row["source"] = "google_places"
                    seen[dedupe] = row
        except Exception as e:
            errors.append(f"{term}: {e}")

    results = list(seen.values())
    if errors and not results:
        raise RuntimeError("; ".join(errors[:3]))
    return results
