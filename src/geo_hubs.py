"""Major metro hubs for statewide Google Places expansion."""
from __future__ import annotations

# Used when user enters a state with no zip — search each hub × freight terms.
STATE_HUBS: dict[str, list[str]] = {
    "VA": [
        "Richmond VA",
        "Norfolk VA",
        "Virginia Beach VA",
        "Arlington VA",
        "Alexandria VA",
        "Roanoke VA",
        "Chesapeake VA",
        "Newport News VA",
        "Hampton VA",
        "Lynchburg VA",
        "Charlottesville VA",
        "Harrisonburg VA",
        "Danville VA",
        "Fredericksburg VA",
        "Winchester VA",
    ],
    "IL": [
        "Chicago IL",
        "Springfield IL",
        "Peoria IL",
        "Rockford IL",
        "Aurora IL",
        "Naperville IL",
        "Joliet IL",
        "Champaign IL",
        "Bloomington IL",
        "Decatur IL",
        "Macomb IL",
        "Quincy IL",
    ],
    "TX": [
        "Houston TX",
        "Dallas TX",
        "Austin TX",
        "San Antonio TX",
        "Fort Worth TX",
        "El Paso TX",
        "Lubbock TX",
    ],
    "CA": [
        "Los Angeles CA",
        "San Francisco CA",
        "San Diego CA",
        "Sacramento CA",
        "Fresno CA",
        "San Jose CA",
        "Oakland CA",
    ],
    "FL": [
        "Miami FL",
        "Orlando FL",
        "Tampa FL",
        "Jacksonville FL",
        "Fort Lauderdale FL",
    ],
    "PA": [
        "Philadelphia PA",
        "Pittsburgh PA",
        "Harrisburg PA",
        "Allentown PA",
        "Scranton PA",
    ],
    "OH": [
        "Columbus OH",
        "Cleveland OH",
        "Cincinnati OH",
        "Toledo OH",
        "Dayton OH",
    ],
    "NC": [
        "Charlotte NC",
        "Raleigh NC",
        "Greensboro NC",
        "Durham NC",
        "Winston-Salem NC",
    ],
    "GA": [
        "Atlanta GA",
        "Savannah GA",
        "Augusta GA",
        "Macon GA",
        "Columbus GA",
    ],
    "NY": [
        "New York NY",
        "Buffalo NY",
        "Rochester NY",
        "Albany NY",
        "Syracuse NY",
    ],
}


def hubs_for_state(state: str) -> list[str]:
    st = (state or "").strip().upper()[:2]
    if not st:
        return []
    return list(STATE_HUBS.get(st) or [f"{st}"])
