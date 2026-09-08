"""
FMCSA carrier discovery — official public data only (no SAFER HTML scrape).

1) Company Census via data.transportation.gov Socrata (az4n-8mr2) — statewide
   pulls of hundreds/thousands by phy_state (e.g. VA).
2) Optional QCMobile webKey for single MC/DOT lookup.
3) Small demo list for UAT when offline.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional

import requests

CENSUS_URL = "https://data.transportation.gov/resource/az4n-8mr2.json"


def _secrets_web_key() -> str:
    try:
        import streamlit as st

        return str(st.secrets.get("fmcsa_web_key", "") or "").strip()
    except Exception:
        return ""


def demo_new_carriers(state: str = "IL", days: int = 30) -> list[dict]:
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
                "lane_or_region": f"{st}",
                "source": "fmcsa_demo",
                "notes": f"Demo sample ({days}d window) — use Census pull for real lists.",
            }
        )
    return out


def pull_census_carriers(
    state: str,
    *,
    limit: int = 1000,
    max_power_units: Optional[int] = 10,
    active_only: bool = True,
    require_mc: bool = True,
) -> tuple[list[dict], str]:
    """
    Pull carriers from FMCSA Company Census (official DOT open data).

    Returns (leads, note). Can return thousands for a busy state like VA.
    Emails are usually blank in census — phone + MC/DOT are the primary contacts.
    """
    st = (state or "").strip().upper()[:2]
    if len(st) != 2:
        raise ValueError("Enter a 2-letter state code (e.g. VA, IL, TX).")

    limit = max(1, min(int(limit or 1000), 5000))
    page_size = 1000
    rows: list[dict] = []
    offset = 0

    where_parts = [f"phy_state='{st}'"]
    if active_only:
        where_parts.append("status_code='A'")
    if require_mc:
        where_parts.append("docket1 IS NOT NULL AND docket1 != ''")

    where = " AND ".join(where_parts)
    # Fetch extra then filter power units in Python (Socrata text fields are awkward)
    fetch_cap = limit if max_power_units is None else min(limit * 3, 5000)

    while len(rows) < fetch_cap:
        batch_n = min(page_size, fetch_cap - len(rows))
        params = {
            "$where": where,
            "$limit": batch_n,
            "$offset": offset,
            "$order": "add_date DESC",
        }
        try:
            r = requests.get(CENSUS_URL, params=params, timeout=60)
            if r.status_code != 200:
                raise RuntimeError(f"FMCSA Census API {r.status_code}: {r.text[:300]}")
            batch = r.json()
        except requests.RequestException as e:
            raise RuntimeError(f"FMCSA Census request failed: {e}") from e

        if not batch:
            break
        for raw in batch:
            mapped = _map_census_row(raw)
            if max_power_units is not None:
                try:
                    pu = float(str(raw.get("power_units") or "999").replace(",", "") or "999")
                except Exception:
                    pu = 999.0
                if pu > float(max_power_units):
                    continue
            if mapped.get("company_name") or mapped.get("dot_number"):
                rows.append(mapped)
                if len(rows) >= limit:
                    break
        if len(rows) >= limit:
            break
        if len(batch) < batch_n:
            break
        offset += len(batch)

    note = (
        f"fmcsa_census · {st} · {len(rows)} row(s) from data.transportation.gov "
        f"(active={'yes' if active_only else 'no'}, "
        f"max_power_units={max_power_units if max_power_units is not None else 'any'}, "
        f"require_mc={require_mc}). Emails usually blank — add before outreach."
    )
    return rows[:limit], note


def search_new_carriers(
    state: str = "IL",
    days: int = 30,
    *,
    use_demo_if_needed: bool = True,
    web_key: Optional[str] = None,
    mc_list: Optional[list[str]] = None,
    limit: int = 1000,
    max_power_units: Optional[int] = 10,
    use_census: bool = True,
) -> tuple[list[dict], str]:
    """
    Preferred path: statewide Census pull.
    Optional: resolve MC list via QCMobile.
    Fallback: demo fixtures for UAT.
    """
    _ = days
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

    if use_census and (state or "").strip():
        try:
            rows, note = pull_census_carriers(
                state,
                limit=limit,
                max_power_units=max_power_units,
            )
            if rows:
                return rows, note
        except Exception as e:
            if not use_demo_if_needed:
                raise
            demo = demo_new_carriers(state=state, days=days)
            return demo, f"census_failed ({e}) · showing demo"

    if use_demo_if_needed:
        return (
            demo_new_carriers(state=state, days=days),
            "fmcsa_demo — turn on Census pull (default) with a 2-letter state for real lists.",
        )
    return [], "empty"


def lookup_carrier_by_mc(mc_number: str, web_key: Optional[str] = None) -> Optional[dict]:
    key = (web_key if web_key is not None else _secrets_web_key()).strip()
    if not key:
        return None
    mc = re_digits(mc_number)
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


def re_digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _map_census_row(row: dict[str, Any]) -> dict:
    name = (row.get("legal_name") or row.get("dba_name") or "").strip()
    docket = re_digits(row.get("docket1") or "")
    prefix = (row.get("docket1prefix") or "MC").upper()
    mc = f"{prefix}-{docket}" if docket else ""
    dot = re_digits(row.get("dot_number") or "")
    phone = str(row.get("phone") or "").strip()
    city = (row.get("phy_city") or "").strip()
    st = (row.get("phy_state") or "").strip().upper()[:2]
    z = str(row.get("phy_zip") or "").strip()[:5]
    power = row.get("power_units") or ""
    add = str(row.get("add_date") or "")[:10]
    return {
        "company_name": name,
        "contact_name": "",
        "email": "",
        "phone": phone,
        "state": st,
        "county": (row.get("phy_cnty") or "").strip(),
        "zip": z,
        "mc_number": mc,
        "dot_number": f"DOT-{dot}" if dot else "",
        "equipment_type": "",
        "authority_date": add,
        "lane_or_region": f"{city}, {st}".strip(", "),
        "source": "fmcsa_census",
        "notes": (
            f"Census power_units={power}; status={row.get('status_code')}; "
            f"city={city}"
        )[:400],
        "years_exp": "",
        "cdl_class": "",
    }


def _map_qc_row(row: dict[str, Any], source: str) -> dict:
    if not isinstance(row, dict):
        return {}
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
