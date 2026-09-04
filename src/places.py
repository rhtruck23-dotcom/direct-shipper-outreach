"""Google Places (New) Text Search — legal lead discovery."""
from __future__ import annotations

from typing import Any, Optional

FREIGHT_QUERIES = {
    "Reefer": [
        "cold storage warehouse",
        "produce distributor",
        "refrigerated food distributor",
        "dairy distributor",
        "meat processor",
        "frozen food distributor",
    ],
    "Dry Van": [
        "food distributor",
        "beverage distributor",
        "paper products distributor",
        "manufacturing warehouse",
        "wholesale distributor",
    ],
    "Box Truck": [
        "local food distributor",
        "wholesale grocery",
        "building materials supplier",
        "retail distribution center",
    ],
}


def build_search_query(
    freight_type: str,
    state: str = "",
    county: str = "",
    zip_code: str = "",
) -> str:
    terms = FREIGHT_QUERIES.get(freight_type, FREIGHT_QUERIES["Reefer"])
    primary = terms[0]
    location_bits = [b for b in [county, state, zip_code] if b]
    location = " ".join(location_bits)
    if location:
        return f"{primary} in {location}"
    return primary


def search_places(
    api_key: str,
    freight_type: str = "Reefer",
    state: str = "",
    county: str = "",
    zip_code: str = "",
    custom_query: str = "",
    max_results: int = 20,
) -> list[dict[str, Any]]:
    """
    Call Google Places API (New) Text Search.
    Returns normalized lead-shaped dicts (email usually empty — fill from website/phone).
    """
    if not api_key:
        raise ValueError(
            "No Google Places API key. Add it in Org Setup, or import a CSV instead."
        )

    import requests

    query = custom_query.strip() or build_search_query(
        freight_type, state, county, zip_code
    )
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,places.formattedAddress,places.nationalPhoneNumber,"
            "places.websiteUri,places.id,places.addressComponents"
        ),
    }
    body: dict[str, Any] = {"textQuery": query, "pageSize": min(max_results, 20)}
    resp = requests.post(url, headers=headers, json=body, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Places API error {resp.status_code}: {resp.text[:400]}")

    data = resp.json()
    places = data.get("places") or []
    results = []
    for p in places:
        addr = p.get("formattedAddress") or ""
        state_code, county_guess, zip_guess = _parse_address_bits(
            p.get("addressComponents") or [], addr
        )
        name = (p.get("displayName") or {}).get("text") or "Unknown"
        results.append(
            {
                "id": p.get("id") or "",
                "company_name": name,
                "contact_name": "",
                "email": "",
                "phone": p.get("nationalPhoneNumber") or "",
                "state": state_code or state,
                "county": county_guess or county,
                "zip": zip_guess or zip_code,
                "freight_type": freight_type,
                "lane_or_region": ", ".join(
                    x for x in [county_guess or county, state_code or state] if x
                ),
                "notes": f"Found via Google Places: {query}",
                "source": "google_places",
                "website": p.get("websiteUri") or "",
                "address": addr,
            }
        )
    return results


def _parse_address_bits(
    components: list[dict], formatted: str
) -> tuple[str, str, str]:
    state = county = zip_code = ""
    for c in components:
        types = c.get("types") or []
        short = c.get("shortText") or c.get("longText") or ""
        if "administrative_area_level_1" in types:
            state = short
        elif "administrative_area_level_2" in types:
            county = (c.get("longText") or short).replace(" County", "")
        elif "postal_code" in types:
            zip_code = short.split("-")[0]
    if not state and formatted:
        # crude fallback: look for ", ST "
        parts = [p.strip() for p in formatted.split(",")]
        if len(parts) >= 2:
            last = parts[-1].replace("USA", "").replace("US", "").strip()
            toks = last.split()
            if toks and len(toks[0]) == 2:
                state = toks[0]
            if len(toks) >= 2 and toks[1][:5].isdigit():
                zip_code = toks[1][:5]
    return state, county, zip_code


def demo_places_results(
    freight_type: str = "Reefer",
    state: str = "IL",
    zip_code: str = "61455",
) -> list[dict[str, Any]]:
    """Offline sample results for UI demo / QA without an API key."""
    samples = [
        {
            "company_name": "Midwest Fresh Produce Co (SAMPLE)",
            "phone": "(309) 555-0101",
            "website": "https://example.com",
            "address": f"100 Market St, Sample City, {state} {zip_code or '61455'}",
        },
        {
            "company_name": "Prairie Cold Storage (SAMPLE)",
            "phone": "(309) 555-0102",
            "website": "https://example.com",
            "address": f"200 Warehouse Rd, Sample City, {state} {zip_code or '61455'}",
        },
        {
            "company_name": "Heartland Dairy Distributors (SAMPLE)",
            "phone": "(309) 555-0103",
            "website": "https://example.com",
            "address": f"300 Dairy Ln, Sample City, {state} {zip_code or '61455'}",
        },
    ]
    out = []
    for i, s in enumerate(samples):
        out.append(
            {
                "id": f"demo-{i}",
                "company_name": s["company_name"],
                "contact_name": "",
                "email": "",
                "phone": s["phone"],
                "state": state,
                "county": "",
                "zip": zip_code or "61455",
                "freight_type": freight_type,
                "lane_or_region": f"{state}",
                "notes": "DEMO result — replace with real Places search or CSV import. Add email before outreach.",
                "source": "demo",
                "website": s["website"],
                "address": s["address"],
            }
        )
    return out
