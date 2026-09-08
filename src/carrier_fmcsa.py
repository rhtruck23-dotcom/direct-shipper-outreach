"""
FMCSA / SAFER-style carrier discovery — legal public data paths only.

- Optional QCMobile webKey (Secrets: fmcsa_web_key) for docket/DOT lookups
- Demo / UAT sample list when no key (always available for testing)
- No HTML scraping of SAFER website UI
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import requests


def _secrets_web_key() -> str:
    try:
        import streamlit as st

        return str(st.secrets.get("fmcsa_web_key", "") or "").strip()
    except Exception:
        return ""


def demo_new_carriers(state: str = "IL", days: int = 30) -> list[dict]:
    """Deterministic UAT fixtures — tagged so they never look like live FMCSA."""
    st = (state or "IL").upper()[:2]
    today = datetime.now().date()
    samples = [
        ("Midwest Haul Partners LLC", "MC-991001", "DOT-3910001", "reefer"),
        ("Prairie Owner Ops Inc", "MC-991002", "DOT-3910002", "dry van"),
        ("River Bend Logistics LLC", "MC-991003", "DOT-3910003", "flatbed"),
        ("Macomb Mile Runners", "MC-991004", "DOT-3910004", "box truck"),
        ("Heartland Lease-On LLC", "MC-991005", "DOT-3910005", "reefer"),
    ]
    out = []
    for i, (name, mc, dot, equip) in enumerate(samples):
        auth = (today - timedelta(days=min(days - 1, 3 + i * 2))).isoformat()
        out.append(
            {
                "company_name": name,
                "contact_name": "",
                "email": "",
                "phone": "",
                "state": st,
                "mc_number": mc,
                "dot_number": dot,
                "equipment_type": equip,
                "authority_date": auth,
                "lane_or_region": f"{st} / Midwest",
                "source": "fmcsa_demo",
                "notes": f"Demo new-authority sample within last {days} days (UAT).",
            }
        )
    return out


def lookup_carrier_by_mc(mc_number: str, web_key: Optional[str] = None) -> Optional[dict]:
    """QCMobile docket lookup. Returns one carrier dict or None."""
    key = (web_key if web_key is not None else _secrets_web_key()).strip()
    if not key:
        return None
    mc = re_mc(mc_number)
    if not mc:
        return None
    url = f"https://mobile.fmcsa.dot.gov/qc/services/carriers/docket-number/{mc}"
    try:
        r = requests.get(url, params={"webKey": key}, timeout=25)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None
    content = data.get("content") if isinstance(data, dict) else None
    if isinstance(content, list) and content:
        row = content[0]
    elif isinstance(content, dict):
        row = content
    else:
        row = data if isinstance(data, dict) else {}
    return _map_qc_row(row, source="fmcsa_qcmobile")


def lookup_carrier_by_dot(dot_number: str, web_key: Optional[str] = None) -> Optional[dict]:
    key = (web_key if web_key is not None else _secrets_web_key()).strip()
    if not key:
        return None
    dot = re_digits(dot_number)
    if not dot:
        return None
    url = f"https://mobile.fmcsa.dot.gov/qc/services/carriers/{dot}"
    try:
        r = requests.get(url, params={"webKey": key}, timeout=25)
        if r.status_code != 200:
            return None
        data = r.json()
    except Exception:
        return None
    content = data.get("content") if isinstance(data, dict) else data
    if isinstance(content, list) and content:
        row = content[0]
    elif isinstance(content, dict):
        row = content
    else:
        return None
    return _map_qc_row(row, source="fmcsa_qcmobile")


def search_new_carriers(
    state: str = "IL",
    days: int = 30,
    *,
    use_demo_if_needed: bool = True,
    web_key: Optional[str] = None,
    mc_list: Optional[list[str]] = None,
) -> tuple[list[dict], str]:
    """
    Pull candidate carriers for onboarding.

    Returns (leads, mode_note).
    Live path: resolve optional MC list via QCMobile.
    Always available: demo list for UAT when no key / empty results.
    """
    key = (web_key if web_key is not None else _secrets_web_key()).strip()
    found: list[dict] = []

    if key and mc_list:
        for mc in mc_list:
            row = lookup_carrier_by_mc(mc, web_key=key)
            if row:
                if state and row.get("state") and row["state"].upper() != state.upper():
                    continue
                found.append(row)

    if found:
        return found, "fmcsa_qcmobile"

    if use_demo_if_needed:
        return (
            demo_new_carriers(state=state, days=days),
            "fmcsa_demo — add Secrets fmcsa_web_key + MC list for live QCMobile lookups "
            "(no SAFER HTML scrape). CSV/Excel/PDF import always works for real lists.",
        )
    return [], "empty"


def re_mc(value: str) -> str:
    digits = re_digits(value)
    return digits


def re_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _map_qc_row(row: dict[str, Any], source: str) -> dict:
    if not isinstance(row, dict):
        return {}
    # QCMobile field names vary; accept common keys
    name = (
        row.get("legalName")
        or row.get("legal_name")
        or row.get("carrierName")
        or row.get("name")
        or ""
    )
    dba = row.get("dbaName") or row.get("dba_name") or ""
    company = name or dba
    mc = row.get("docketNumber") or row.get("mcNumber") or row.get("mc_number") or ""
    dot = row.get("dotNumber") or row.get("usdot") or row.get("dot_number") or ""
    st = row.get("phyState") or row.get("state") or row.get("phy_state") or ""
    phone = row.get("telephone") or row.get("phone") or ""
    return {
        "company_name": str(company).strip(),
        "contact_name": "",
        "email": "",
        "phone": str(phone).strip(),
        "state": str(st).strip().upper()[:2],
        "mc_number": f"MC-{re_digits(mc)}" if re_digits(mc) else "",
        "dot_number": f"DOT-{re_digits(dot)}" if re_digits(dot) else "",
        "equipment_type": "",
        "authority_date": str(row.get("allowToOperate") or row.get("addDate") or "")[:10],
        "source": source,
        "notes": "Pulled via FMCSA QCMobile public API",
    }
